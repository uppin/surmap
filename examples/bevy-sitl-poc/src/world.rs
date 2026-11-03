//! The disaster block, built at runtime from `assets/scene.json`: an
//! interpreter of the manifest's elements and models. No position, count
//! or colour of the scene lives in code; only the element kinds do.
//!
//! The manifest is an asset: on wasm Bevy fetches it (and every texture
//! and model it names) over HTTP from `assets/`, natively it reads the
//! file. New content is a file drop plus a manifest edit; the WASM is
//! not rebuilt for it.

use bevy::asset::io::Reader;
use bevy::asset::{AssetLoader, LoadContext};
use bevy::camera::primitives::Aabb;
use bevy::prelude::*;
use bevy::scene::SceneInstanceReady;
use bevy_feronia::extension;
use bevy_feronia::prelude::*;
use bevy_rapier3d::prelude::*;

use std::collections::BTreeMap;

use crate::scene_manifest::{
    BoxElement, Building, ColliderKind, CollapsedBuilding, Element, Environment, ManifestError, ModelInstance, PbrTextureSet,
    Person, SceneManifest,
};
use crate::rig::{ProfileAsset, RigSource};
use crate::shots::RunMode;
use crate::sky::SkySource;
use crate::textures::{load_texture_set, tiled_material, TextureSetHandles};
use crate::wire::GroundTruthObject;

pub const MANIFEST_PATH: &str = "scene.json";

#[derive(Asset, TypePath, Debug)]
pub struct ManifestAsset(pub SceneManifest);

#[derive(Default, TypePath)]
pub struct ManifestLoader;

impl AssetLoader for ManifestLoader {
    type Asset = ManifestAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _settings: &(),
        _context: &mut LoadContext<'_>,
    ) -> Result<ManifestAsset, std::io::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
        SceneManifest::from_json(&text)
            .map(ManifestAsset)
            .map_err(|e: ManifestError| std::io::Error::other(format!("{e:?}")))
    }

    fn extensions(&self) -> &[&str] {
        &["json"]
    }
}

/// The manifest handle, then the built world.
#[derive(Resource)]
pub struct SceneState {
    pub manifest: Handle<ManifestAsset>,
    pub built: bool,
    /// Why the scene cannot be built as declared, if it cannot.
    pub failed: Option<String>,
    /// Every handle the scene waits on before it counts as ready.
    pub pending: Vec<UntypedHandle>,
}

/// Ground-truth boxes (ENU) of the objects a region query may target.
#[derive(Resource, Default)]
pub struct GroundTruth(pub Vec<GroundTruthObject>);

/// A spawned model whose collider and ground-truth box need its meshes.
#[derive(Component)]
pub struct PendingModel {
    instance: ModelInstance,
}

pub fn start_loading(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(SceneState { manifest: assets.load(MANIFEST_PATH), built: false, failed: None, pending: Vec::new() });
    commands.init_resource::<GroundTruth>();
}

/// ENU metres → Bevy (x right/east, y up, -z north).
pub fn enu(x: f32, y: f32, z: f32) -> Vec3 {
    Vec3::new(x, z, -y)
}

/// splitmix64: a tiny deterministic generator (no dependency).
pub struct Seeded(u64);

impl Seeded {
    pub fn new(seed: u64) -> Self {
        Self(seed.wrapping_add(0x9E37_79B9_7F4A_7C15))
    }
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    /// Uniform in [lo, hi).
    pub fn range(&mut self, lo: f32, hi: f32) -> f32 {
        let unit = (self.next_u64() >> 40) as f32 / (1u64 << 24) as f32;
        lo + (hi - lo) * unit
    }
    pub fn sign(&mut self) -> f32 {
        if self.next_u64() & 1 == 0 { 1.0 } else { -1.0 }
    }
}

/// The manifest's materials, with their maps loading.
pub struct Library {
    defs: BTreeMap<String, (PbrTextureSet, Option<TextureSetHandles>)>,
}

impl Library {
    fn load(manifest: &SceneManifest, assets: &AssetServer, pending: &mut Vec<UntypedHandle>) -> Self {
        let mut defs = BTreeMap::new();
        for (key, def) in &manifest.materials {
            let handles = def.base_color.as_ref().map(|_| load_texture_set(assets, def));
            if let Some(h) = &handles {
                pending.extend(h.base_color.iter().chain(&h.normal).chain(&h.arm).chain(&h.roughness).map(|x| x.clone().untyped()));
            }
            defs.insert(key.clone(), (def.clone(), handles));
        }
        Self { defs }
    }

    /// `key` tiled over `size_m` of surface, tinted, optionally re-scaled.
    fn material(&self, key: &str, size_m: Vec2, tint: Option<[f32; 3]>, uv_scale: Option<f32>) -> StandardMaterial {
        let (def, handles) = &self.defs[key];
        let tint = tint.map_or(Color::WHITE, |[r, g, b]| Color::srgb(r, g, b));
        tiled_material(def, handles.as_ref(), size_m, tint, uv_scale)
    }
}

pub fn build_world(
    mut commands: Commands,
    mut state: ResMut<SceneState>,
    manifests: Res<Assets<ManifestAsset>>,
    assets: Res<AssetServer>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut truth: ResMut<GroundTruth>,
    mode: Res<RunMode>,
) {
    if state.built {
        return;
    }
    let Some(ManifestAsset(manifest)) = manifests.get(&state.manifest) else { return };
    let library = Library::load(manifest, &assets, &mut state.pending);
    let camera = mode.camera.clone().unwrap_or_else(|| manifest.camera.clone());
    let profile: Handle<ProfileAsset> = assets.load(camera);
    state.pending.push(profile.clone().untyped());
    commands.insert_resource(RigSource(profile));
    spawn_sun_and_haze(&mut commands, &assets, &mut state.pending, &manifest.environment);
    let mut world = Builder { commands: &mut commands, meshes: &mut meshes, materials: &mut materials, library: &library, truth: &mut truth };
    for element in &manifest.elements {
        world.element(element);
    }
    for instance in &manifest.models {
        let scene = assets.load(GltfAssetLabel::Scene(0).from_asset(instance.glb.clone()));
        state.pending.push(scene.clone().untyped());
        commands
            .spawn((SceneRoot(scene), instance.bevy_transform(), PendingModel { instance: instance.clone() }))
            .observe(on_model_ready);
    }
    state.built = true;
}

/// ENU base position + yaw → the Bevy transform of a box of `size_m`
/// (east, north, up) centred over that base.
fn placed(position_enu: [f32; 3], yaw_deg: f32, height: f32) -> Transform {
    let [x, y, z] = position_enu;
    Transform::from_translation(enu(x, y, z + height / 2.0)).with_rotation(Quat::from_rotation_y(yaw_deg.to_radians()))
}

/// Bevy box dimensions for ENU (east, north, up).
fn bevy_size([east, north, up]: [f32; 3]) -> Vec3 {
    Vec3::new(east, up, north)
}

fn corners(transform: Transform, size: Vec3) -> impl Iterator<Item = Vec3> {
    (0..8).map(move |i| {
        let sign = Vec3::new(if i & 1 == 0 { -0.5 } else { 0.5 }, if i & 2 == 0 { -0.5 } else { 0.5 }, if i & 4 == 0 { -0.5 } else { 0.5 });
        transform.transform_point(sign * size)
    })
}

/// A Bevy-space box's ENU bounds as a ground-truth object.
fn truth_box(id: &str, kind: &str, lo: Vec3, hi: Vec3) -> GroundTruthObject {
    GroundTruthObject { id: id.to_owned(), kind: kind.to_owned(), min_enu: [lo.x, -hi.z, lo.y], max_enu: [hi.x, -lo.z, hi.y] }
}

struct Builder<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    meshes: &'a mut Assets<Mesh>,
    materials: &'a mut Assets<StandardMaterial>,
    library: &'a Library,
    truth: &'a mut GroundTruth,
}

impl Builder<'_, '_, '_> {
    fn element(&mut self, element: &Element) {
        match element {
            Element::Box(e) => self.box_element(e),
            Element::CollapsedBuilding(e) => self.collapsed(e),
            Element::Building(e) => self.building(e),
            Element::Person(e) => self.person(e),
        }
    }

    /// A textured box; the tile is its largest faces' extent.
    fn cuboid(&mut self, key: &str, size: Vec3, transform: Transform, tint: Option<[f32; 3]>, uv_scale: Option<f32>, collider: bool) -> Entity {
        let mesh = Mesh::from(Cuboid::from_size(size)).with_generated_tangents().expect("cuboid has UVs");
        let tile = Vec2::new(size.x.max(size.y), size.z.max(size.y));
        let material = self.library.material(key, tile, tint, uv_scale);
        let mut entity = self.commands.spawn((Mesh3d(self.meshes.add(mesh)), MeshMaterial3d(self.materials.add(material)), transform));
        if collider {
            entity.insert((RigidBody::Fixed, Collider::cuboid(size.x / 2.0, size.y / 2.0, size.z / 2.0)));
        }
        entity.id()
    }

    fn box_element(&mut self, e: &BoxElement) {
        let size = bevy_size(e.size_m);
        let transform = placed(e.position_enu, e.yaw_deg, e.size_m[2]);
        let entity = self.cuboid(&e.material, size, transform, e.tint, e.uv_scale, e.collider);
        if let Some(scatter) = &e.scatter {
            let chunk = self.materials.add(self.library.material(&scatter.material, Vec2::splat(0.5), None, None));
            let mesh = self.meshes.add(Mesh::from(Cuboid::new(0.5, 0.22, 0.34)).with_generated_tangents().expect("cuboid has UVs"));
            self.commands.entity(entity).insert((
                ScatterRoot::default(),
                children![(
                    extension::scatter_layer("Ground debris"),
                    DistributionDensity(scatter.density),
                    InstanceJitterStrength::default(),
                    InstanceScaleRange::default(),
                    InstanceRotationYawRange::default(),
                    WindAffected,
                    children![
                        (Name::new("Debris chunk"), MeshMaterial3d(chunk.clone()), Mesh3d(mesh.clone()), Transform::from_xyz(0., 0.12, 0.)),
                        (Name::new("Debris chunk"), LevelOfDetail(1), MeshMaterial3d(chunk), Mesh3d(mesh), Transform::from_xyz(0., 0.12, 0.)),
                    ]
                )],
            ));
        }
        if let Some(kind) = &e.ground_truth {
            let (lo, hi) = bounds(corners(transform, size));
            self.truth.0.push(truth_box(&e.id, kind, lo, hi));
        }
    }

    /// Spec §4.1: tilted, offset slabs and a rubble fan, from `seed`.
    fn collapsed(&mut self, e: &CollapsedBuilding) {
        let mut rng = Seeded::new(e.seed);
        let [w, d] = e.footprint_m;
        let site = placed(e.position_enu, e.yaw_deg, 0.0);
        let (sx, sz, about_x) = (rng.sign(), rng.sign(), rng.next_u64() & 1 == 0);
        let size = Vec3::new(w, e.slab_thickness_m, d);
        let mut points = Vec::new();
        for k in 0..e.slabs {
            let kf = k as f32;
            let tilt = (3.0 + 3.0 * kf).to_radians() * rng.sign();
            let rotation = if about_x { Quat::from_rotation_x(tilt) } else { Quat::from_rotation_z(tilt) };
            // Gaps of 0.15 m crushed to nothing at one end: the tilt does it.
            let centre = Vec3::new(sx * 0.4 * kf, e.slab_thickness_m / 2.0 + kf * (e.slab_thickness_m + 0.15), -sz * 0.3 * kf);
            let world = site * Transform::from_translation(centre).with_rotation(rotation);
            self.cuboid(&e.material, size, world, e.tint, None, true);
            points.extend(corners(world, size));
        }
        let side = rng.sign();
        for _ in 0..e.rubble {
            let angle = rng.range(0.0, std::f32::consts::PI);
            let radius = rng.range(0.3, e.rubble_radius_m);
            let along = rng.range(-0.4, 0.4) * w;
            let offset = Vec3::new(along + radius * angle.cos(), 0.0, side * (d / 2.0 + radius * angle.sin()));
            let chunk = Vec3::new(rng.range(0.2, 0.9), rng.range(0.2, 0.9), rng.range(0.2, 0.9));
            let rotation = Quat::from_euler(EulerRot::YXZ, rng.range(0.0, std::f32::consts::TAU), rng.range(-0.5, 0.5), rng.range(-0.5, 0.5));
            let local = Transform::from_translation(offset + Vec3::Y * chunk.y * 0.4).with_rotation(rotation);
            self.cuboid(&e.material, chunk, site * local, e.tint, None, true);
        }
        let (lo, hi) = bounds(points.into_iter());
        self.truth.0.push(truth_box(&e.id, "collapsed_building", lo, hi));
    }

    /// Spec §4.2 + V1 correction 4: a block with a window grid.
    fn building(&mut self, e: &Building) {
        let size = bevy_size(e.size_m);
        let transform = placed(e.position_enu, e.yaw_deg, e.size_m[2]);
        self.cuboid(&e.material, size, transform, e.tint, None, true);
        let Some(windows) = &e.windows else { return };
        let pane = self.meshes.add(Rectangle::new(windows.pane_m[0], windows.pane_m[1]));
        let glass = self.materials.add(self.library.material(&windows.material, Vec2::ONE, None, None));
        let half = size / 2.0;
        for (normal, along, width) in [(Vec3::X, Vec3::Z, size.z), (Vec3::NEG_X, Vec3::Z, size.z), (Vec3::Z, Vec3::X, size.x), (Vec3::NEG_Z, Vec3::X, size.x)] {
            let bays = (width / windows.bay_m).floor() as i32;
            let first = -(bays as f32 - 1.0) * windows.bay_m / 2.0;
            let depth = normal.abs().dot(half) + 0.02;
            let facing = Quat::from_rotation_arc(Vec3::Z, normal);
            let mut row = windows.first_row_m;
            while row + windows.pane_m[1] / 2.0 < size.y - 0.5 {
                for b in 0..bays {
                    let offset = first + b as f32 * windows.bay_m;
                    if offset.abs() + windows.pane_m[0] / 2.0 > width / 2.0 - 1.0 {
                        continue;
                    }
                    let local = Vec3::new(0.0, row - half.y, 0.0) + normal * depth + along * offset;
                    let pose = transform * Transform::from_translation(local).with_rotation(facing);
                    self.commands.spawn((Mesh3d(pane.clone()), MeshMaterial3d(glass.clone()), pose));
                }
                row += windows.floor_m;
            }
        }
    }

    fn person(&mut self, e: &Person) {
        let [x, y, z] = e.position_enu;
        let coat = self.materials.add(self.library.material(&e.coat, Vec2::ONE, None, None));
        let skin = self.materials.add(self.library.material(&e.skin, Vec2::ONE, None, None));
        self.commands.spawn((Mesh3d(self.meshes.add(Capsule3d::new(0.17, 1.05))), MeshMaterial3d(coat), Transform::from_translation(enu(x, y, z + 0.72))));
        self.commands.spawn((Mesh3d(self.meshes.add(Sphere::new(0.13))), MeshMaterial3d(skin), Transform::from_translation(enu(x, y, z + 1.62))));
    }
}

fn bounds(points: impl Iterator<Item = Vec3>) -> (Vec3, Vec3) {
    points.fold((Vec3::splat(f32::MAX), Vec3::splat(f32::MIN)), |(lo, hi), p| (lo.min(p), hi.max(p)))
}

/// Spec §5 sun (elevation, azimuth clockwise from north) with cascaded
/// shadows, from the manifest's environment.
fn spawn_sun_and_haze(commands: &mut Commands, assets: &AssetServer, pending: &mut Vec<UntypedHandle>, environment: &Environment) {
    let (el, az) = (environment.sun_elevation_deg.to_radians(), environment.sun_azimuth_deg.to_radians());
    let towards_sun = enu(az.sin() * el.cos(), az.cos() * el.cos(), el.sin());
    commands.spawn((
        DirectionalLight { illuminance: environment.sun_illuminance_lux, shadows_enabled: true, ..default() },
        bevy::light::CascadeShadowConfigBuilder {
            num_cascades: 4,
            first_cascade_far_bound: 10.0,
            maximum_distance: 180.0,
            overlap_proportion: 0.2,
            ..default()
        }
        .build(),
        Transform::from_translation(towards_sun).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    if let Some(hdri) = &environment.hdri {
        // The sky module re-aims this sun at the HDRI's own sun.
        let equirect: Handle<Image> = assets.load(hdri.clone());
        pending.push(equirect.clone().untyped());
        commands.insert_resource(SkySource { equirect, brightness: environment.sky_brightness, baked: false });
    }
    commands.insert_resource(CameraLook { fog_visibility_m: environment.fog_visibility_m, exposure_ev100: environment.exposure_ev100 });
}

/// The manifest's haze and exposure, applied to every camera.
#[derive(Resource)]
pub struct CameraLook {
    pub fog_visibility_m: f32,
    pub exposure_ev100: f32,
}

/// The scene of a model has spawned; its bounds exist one frame later.
#[derive(Component)]
pub struct ModelSpawned;

fn on_model_ready(ready: On<SceneInstanceReady>, mut commands: Commands) {
    commands.entity(ready.entity).insert(ModelSpawned);
}

/// Once a model's meshes have bounds: its collider (spec §6) and, for
/// ground-truth instances, its ENU box — from the meshes' own bounds.
pub fn resolve_models(
    mut commands: Commands,
    models: Query<(Entity, &PendingModel, &Transform), With<ModelSpawned>>,
    children: Query<&Children>,
    mesh_parts: Query<(&Mesh3d, Option<&Aabb>, &GlobalTransform)>,
    meshes: Res<Assets<Mesh>>,
    mut truth: ResMut<GroundTruth>,
) {
    for (root, pending, transform) in &models {
        let parts: Vec<Entity> = children.iter_descendants(root).filter(|e| mesh_parts.contains(*e)).collect();
        if parts.is_empty() || parts.iter().any(|e| mesh_parts.get(*e).is_ok_and(|(_, aabb, _)| aabb.is_none())) {
            continue;
        }
        resolve_model(&mut commands, root, pending, transform, &parts, &mesh_parts, &meshes, &mut truth);
    }
}

#[allow(clippy::too_many_arguments)]
fn resolve_model(
    commands: &mut Commands,
    root: Entity,
    pending: &PendingModel,
    transform: &Transform,
    parts: &[Entity],
    mesh_parts: &Query<(&Mesh3d, Option<&Aabb>, &GlobalTransform)>,
    meshes: &Assets<Mesh>,
    truth: &mut GroundTruth,
) {
    let to_local = transform.compute_affine().inverse();
    let mut lo = Vec3::splat(f32::MAX);
    let mut hi = Vec3::splat(f32::MIN);
    let mut world_lo = Vec3::splat(f32::MAX);
    let mut world_hi = Vec3::splat(f32::MIN);
    let mut trimeshes = Vec::new();
    for &part in parts {
        let Ok((mesh, Some(aabb), global)) = mesh_parts.get(part) else { continue };
        let (centre, half) = (Vec3::from(aabb.center), Vec3::from(aabb.half_extents));
        for sx in [-1.0, 1.0] {
            for sy in [-1.0, 1.0] {
                for sz in [-1.0, 1.0] {
                    let corner = global.transform_point(centre + half * Vec3::new(sx, sy, sz));
                    world_lo = world_lo.min(corner);
                    world_hi = world_hi.max(corner);
                    let local = to_local.transform_point3(corner);
                    lo = lo.min(local);
                    hi = hi.max(local);
                }
            }
        }
        if pending.instance.collider == ColliderKind::Trimesh {
            if let Some(m) = meshes.get(&mesh.0) {
                trimeshes.push((part, m.clone()));
            }
        }
    }
    match pending.instance.collider {
        ColliderKind::Box if lo.x <= hi.x => {
            let child = commands
                .spawn((Collider::cuboid((hi.x - lo.x) / 2.0, (hi.y - lo.y) / 2.0, (hi.z - lo.z) / 2.0), Transform::from_translation((lo + hi) / 2.0)))
                .id();
            commands.entity(root).insert(RigidBody::Fixed).add_child(child);
        }
        ColliderKind::Trimesh => {
            commands.entity(root).insert(RigidBody::Fixed);
            for (part, mesh) in trimeshes {
                if let Some(collider) = Collider::from_bevy_mesh(&mesh, &ComputedColliderShape::TriMesh(TriMeshFlags::default())) {
                    commands.entity(part).insert(collider);
                }
            }
        }
        _ => {}
    }
    if pending.instance.ground_truth && world_lo.x <= world_hi.x {
        truth.0.push(GroundTruthObject {
            id: pending.instance.id.clone(),
            kind: pending.instance.kind.clone(),
            min_enu: [world_lo.x, -world_hi.z, world_lo.y],
            max_enu: [world_hi.x, -world_lo.z, world_hi.y],
        });
    }
    commands.entity(root).remove::<(PendingModel, ModelSpawned)>();
}

/// True once the manifest and everything it named have loaded.
pub fn scene_ready(state: &SceneState, assets: &AssetServer, models: usize) -> bool {
    state.built && models == 0 && state.pending.iter().all(|h| assets.is_loaded_with_dependencies(h.id()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_seeded_generator_repeats_for_a_seed() {
        let (mut a, mut b) = (Seeded::new(3), Seeded::new(3));

        assert_eq!((a.next_u64(), a.range(0.0, 1.0)), (b.next_u64(), b.range(0.0, 1.0)));
    }

    #[test]
    fn a_range_stays_inside_its_bounds() {
        let mut rng = Seeded::new(7);

        assert!((0..1000).map(|_| rng.range(0.2, 0.9)).all(|v| (0.2..0.9).contains(&v)));
    }

    #[test]
    fn enu_north_is_bevy_minus_z() {
        assert_eq!(enu(1.0, 2.0, 3.0), Vec3::new(1.0, 3.0, -2.0));
    }
}
