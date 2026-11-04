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
use bevy::ecs::system::SystemParam;
use bevy::prelude::*;
use bevy_feronia::extension;
use bevy_feronia::prelude::*;
use bevy_rapier3d::prelude::*;

use std::collections::BTreeMap;

use crate::actors::{self, bevy_yaw, Figure};
use crate::figure_anim::Pose;
use crate::building;
use crate::scene_manifest::{
    BoxElement, Building, CollapsedBuilding, DistrictDef, DroneNest, Element, Environment, ManifestError, ModelInstance,
    PbrTextureSet, Person, SceneManifest, Vehicle,
};
use crate::scene_manifest::NEST_PAD_M;
use crate::rig::{ProfileAsset, RigSource};
use crate::scene_manifest::{surface_at, surfaces, Surface};
use crate::shots::RunMode;
use crate::sky::SkySource;
use crate::textures::{load_texture_set, tiled_material, RoughnessPacking, TextureSetHandles};
use crate::vegetation::{plan_stand, PendingStands};
use crate::sea::{phase_of, sea_state, SeaState};
use crate::vehicle::scene::{Float, VehicleActor, VehicleClasses};
use crate::wildfire::Wildfire;
use crate::wire::GroundTruthObject;

mod models;

use models::on_model_ready;
pub use models::resolve_models;

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
    /// False while preset-styled buildings still wait for their preset files (`building.rs`).
    pub buildings_ready: bool,
}

/// Ground-truth boxes (ENU) of the objects a region query may target.
#[derive(Resource, Default)]
pub struct GroundTruth(pub Vec<GroundTruthObject>);

/// A pad's deck is this thick, m; its top is the nest's deck level.
const NEST_DECK_M: f32 = 0.05;
/// The dark rim around the deck, m wide.
const NEST_RIM_M: f32 = 0.1;
/// The "H" marking: bar thickness above the deck, bar width and the uprights' length, m.
const NEST_MARK_M: f32 = 0.01;
const NEST_MARK_WIDTH_M: f32 = 0.16;
const NEST_MARK_LENGTH_M: f32 = 1.2;

/// A drone nest's pad as built: its id, the pad's ENU centre at deck level, its heading and the
/// drones it houses (`DroneNest::drone_ids`). The drones dock from here.
#[derive(Debug, Clone, PartialEq)]
pub struct Nest {
    pub id: String,
    pub pad_enu: [f32; 3],
    pub yaw_deg: f32,
    pub drone_ids: Vec<String>,
}

/// Every nest of the scene, in manifest order.
#[derive(Resource, Debug, Default, Clone, PartialEq)]
pub struct Nests(pub Vec<Nest>);

/// The pad entity of the nest `id`.
#[derive(Component, Debug, Clone, PartialEq)]
pub struct NestPad {
    pub id: String,
}

/// A spawned model whose collider and ground-truth box need its meshes.
#[derive(Component)]
pub struct PendingModel {
    instance: ModelInstance,
}

pub fn start_loading(mut commands: Commands, assets: Res<AssetServer>, mode: Res<RunMode>) {
    let path = crate::shots::manifest_path(mode.scenario.as_deref());
    let classes = VehicleClasses::load(&assets);
    commands.insert_resource(SceneState { manifest: assets.load(path), built: false, failed: None, pending: classes.handles().collect(), buildings_ready: true });
    commands.insert_resource(classes);
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
    /// While it rains, these materials look wet: (keys, roughness factor, colour factor).
    wet: Option<(Vec<String>, f32, f32)>,
}

impl Library {
    fn load(manifest: &SceneManifest, assets: &AssetServer, packing: &RoughnessPacking, pending: &mut Vec<UntypedHandle>) -> Self {
        let mut defs = BTreeMap::new();
        for (key, def) in &manifest.materials {
            let handles = def.base_color.as_ref().map(|_| load_texture_set(assets, def, packing));
            if let Some(h) = &handles {
                pending.extend(h.base_color.iter().chain(&h.normal).chain(&h.arm).chain(&h.roughness).map(|x| x.clone().untyped()));
            }
            defs.insert(key.clone(), (def.clone(), handles));
        }
        let wet = manifest
            .weather
            .as_ref()
            .filter(|w| w.rain_mm_h > 0.0)
            .map(|w| (w.wet_materials.clone(), w.wet_roughness, w.wet_darkening));
        Self { defs, wet }
    }

    /// `key` tiled over `size_m` of surface, tinted, optionally re-scaled.
    fn material(&self, key: &str, size_m: Vec2, tint: Option<[f32; 3]>, uv_scale: Option<f32>) -> StandardMaterial {
        let (def, handles) = &self.defs[key];
        let tint = tint.map_or(Color::WHITE, |[r, g, b]| Color::srgb(r, g, b));
        let mut material = tiled_material(def, handles.as_ref(), size_m, tint, uv_scale);
        if let Some((keys, roughness, darkening)) = &self.wet {
            if keys.iter().any(|k| k == key) {
                material.perceptual_roughness *= roughness;
                let c = material.base_color.to_linear();
                material.base_color = Color::LinearRgba(LinearRgba::new(c.red * darkening, c.green * darkening, c.blue * darkening, c.alpha));
            }
        }
        material
    }
}

/// What `build_world` reads: the loaded manifests, the asset server and the run mode.
#[derive(SystemParam)]
pub struct WorldInputs<'w> {
    manifests: Res<'w, Assets<ManifestAsset>>,
    assets: Res<'w, AssetServer>,
    mode: Res<'w, RunMode>,
    packing: Res<'w, RoughnessPacking>,
}

pub fn build_world(
    mut commands: Commands,
    mut state: ResMut<SceneState>,
    inputs: WorldInputs,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut truth: ResMut<GroundTruth>,
    mut stands: ResMut<PendingStands>,
) {
    let WorldInputs { manifests, assets, mode, packing } = inputs;
    if state.built {
        return;
    }
    let Some(ManifestAsset(manifest)) = manifests.get(&state.manifest) else { return };
    let library = Library::load(manifest, &assets, &packing, &mut state.pending);
    let camera = mode.camera.clone().unwrap_or_else(|| manifest.camera.clone());
    let profile: Handle<ProfileAsset> = assets.load(camera);
    state.pending.push(profile.clone().untyped());
    commands.insert_resource(RigSource(profile));
    let fog_visibility_m = manifest.weather.as_ref().and_then(|w| w.fog_visibility_m);
    spawn_sun_and_haze(&mut commands, &assets, &mut state.pending, &manifest.environment, fog_visibility_m);
    if let Some(floor) = &manifest.map_floor {
        // The real map as the floor: one untiled texture on a bbox-sized plane at
        // the ENU origin, just under the elements' bases so boxes never z-fight it.
        let (_, [east, north]) = floor.centre_and_size_enu();
        let texture: Handle<Image> = assets.load(floor.texture.clone());
        state.pending.push(texture.clone().untyped());
        let material = materials.add(StandardMaterial {
            base_color_texture: Some(texture),
            perceptual_roughness: 0.95,
            ..default()
        });
        let mesh = meshes.add(Rectangle::new(east as f32, north as f32));
        commands.spawn((
            Name::new("Map floor"),
            Mesh3d(mesh),
            MeshMaterial3d(material),
            Transform::from_translation(enu(0.0, 0.0, -0.02))
                .with_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2)),
        ));
    }
    commands.insert_resource(Wildfire::new(manifest.weather.as_ref(), &manifest.fires, &assets, &mut meshes, &mut state.pending));
    let gait: Handle<actors::FigureAsset> = assets.load("behaviour/person.figure.json");
    state.pending.push(gait.clone().untyped());
    commands.insert_resource(actors::FigureLook(gait));
    commands.insert_resource(actors::Behaviour::new(actors::wind_runner(manifest.weather.as_ref())));
    for element in &manifest.elements {
        if let Element::Vegetation(stand) = element {
            plan_stand(&assets, &mut state.pending, &mut stands, stand);
        }
    }
    if let Some(plan) = building::plan(manifest, &assets, &mut state.pending) {
        state.buildings_ready = false;
        commands.insert_resource(plan);
    }
    let waters = surfaces(&manifest.elements);
    let sea = sea_state(manifest.weather.as_ref().map_or(0.0, |weather| weather.wind.speed_m_s));
    let mut world = Builder {
        commands: &mut commands,
        meshes: &mut meshes,
        materials: &mut materials,
        library: &library,
        truth: &mut truth,
        districts: &manifest.districts,
        waters: &waters,
        sea,
        nests: Vec::new(),
    };
    for element in &manifest.elements {
        world.element(element);
    }
    let nests = world.nests;
    commands.insert_resource(Nests(nests));
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
    districts: &'a [DistrictDef],
    /// The water boxes vessels float on, and the sea the scene's wind raises over them.
    waters: &'a [Surface],
    sea: SeaState,
    /// The nests built so far, in manifest order.
    nests: Vec<Nest>,
}

impl Builder<'_, '_, '_> {
    fn element(&mut self, element: &Element) {
        match element {
            Element::Box(e) => self.box_element(e),
            Element::CollapsedBuilding(e) => self.collapsed(e),
            Element::Building(e) if !building::is_styled(e, self.districts) => self.building(e),
            Element::Building(_) => {}
            Element::Person(e) => self.person(e),
            Element::Vegetation(_) => {}
            Element::Vehicle(e) => self.vehicle(e),
            Element::DroneNest(e) => self.nest(e),
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

    /// A survivor: a figure whose root stands on the ground, carrying its behaviour tree (if any),
    /// with the capsule body and the head as its children.
    /// A vehicle's root at its start pose; its class glTF is attached once its class file loads.
    fn vehicle(&mut self, e: &Vehicle) {
        let [x, y, z] = e.position_enu;
        let turn = Quat::from_rotation_y(bevy_yaw(Vec2::from_angle(e.yaw_deg.to_radians())));
        let float = e.class.is_vessel().then(|| surface_at(self.waters, Vec2::new(x, y))).flatten().map(|water| Float {
            surface_top_m: water.top_z_m,
            sea: self.sea,
            phase: phase_of(&e.id),
        });
        self.commands
            .spawn((VehicleActor::new(e, float), Visibility::default(), Transform::from_translation(enu(x, y, z)).with_rotation(turn)));
    }

    /// A landing pad at the nest's centre, turned by its yaw: a `NEST_PAD_M` deck, a dark rim and
    /// an "H", tagged `NestPad`, with the nest added to `Nests`.
    fn nest(&mut self, e: &DroneNest) {
        let [x, y, z] = e.position_enu;
        let turn = Quat::from_rotation_y(bevy_yaw(Vec2::from_angle(e.yaw_deg.to_radians())));
        let paint = |materials: &mut Assets<StandardMaterial>, shade: f32| {
            materials.add(StandardMaterial { base_color: Color::srgb(shade, shade, shade), perceptual_roughness: 0.9, ..default() })
        };
        let (deck_paint, rim_paint, mark_paint) = (paint(self.materials, 0.30), paint(self.materials, 0.06), paint(self.materials, 0.92));
        let deck = Vec3::new(NEST_PAD_M, NEST_DECK_M, NEST_PAD_M);
        let rim = Vec3::new(NEST_PAD_M + 2.0 * NEST_RIM_M, NEST_DECK_M, NEST_PAD_M + 2.0 * NEST_RIM_M);
        let deck_mesh = self.meshes.add(Cuboid::from_size(deck));
        let rim_mesh = self.meshes.add(Cuboid::from_size(rim));
        // The "H": two uprights joined by a crossbar, lying on the deck, uprights along north.
        let bar = |east: f32, north: f32| Vec3::new(east, NEST_MARK_M, north);
        let marks = [
            (bar(NEST_MARK_WIDTH_M, NEST_MARK_LENGTH_M), Vec3::new(-NEST_MARK_LENGTH_M / 3.0, 0.0, 0.0)),
            (bar(NEST_MARK_WIDTH_M, NEST_MARK_LENGTH_M), Vec3::new(NEST_MARK_LENGTH_M / 3.0, 0.0, 0.0)),
            (bar(2.0 * NEST_MARK_LENGTH_M / 3.0, NEST_MARK_WIDTH_M), Vec3::ZERO),
        ];
        let mark_meshes: Vec<(Handle<Mesh>, Vec3)> = marks.iter().map(|(size, at)| (self.meshes.add(Cuboid::from_size(*size)), *at)).collect();
        self.commands
            .spawn((NestPad { id: e.id.clone() }, Name::new(format!("Nest {}", e.id)), Visibility::default(), Transform::from_translation(enu(x, y, z)).with_rotation(turn)))
            .with_children(|pad| {
                // The deck's top is the nest's deck level; the rim sits a hair lower so it reads as a border.
                pad.spawn((Mesh3d(deck_mesh), MeshMaterial3d(deck_paint), Transform::from_xyz(0.0, -NEST_DECK_M / 2.0, 0.0), RigidBody::Fixed, Collider::cuboid(deck.x / 2.0, deck.y / 2.0, deck.z / 2.0)));
                pad.spawn((Mesh3d(rim_mesh), MeshMaterial3d(rim_paint), Transform::from_xyz(0.0, -NEST_DECK_M / 2.0 - 0.01, 0.0)));
                for (mesh, at) in mark_meshes {
                    pad.spawn((Mesh3d(mesh), MeshMaterial3d(mark_paint.clone()), Transform::from_translation(at + Vec3::Y * NEST_MARK_M / 2.0)));
                }
            });
        self.nests.push(Nest { id: e.id.clone(), pad_enu: e.position_enu, yaw_deg: e.yaw_deg, drone_ids: e.drone_ids() });
    }

    fn person(&mut self, e: &Person) {
        let coat = self.materials.add(self.library.material(&e.coat, Vec2::ONE, None, None));
        let skin = self.materials.add(self.library.material(&e.skin, Vec2::ONE, None, None));
        let body = self.meshes.add(Capsule3d::new(0.17, 1.05));
        let head = self.meshes.add(Sphere::new(0.13));
        let tree = e.behaviour.clone();
        let mut figure = Figure::new(&e.id, e.position_enu, tree);
        if e.pose != Pose::Standing {
            figure = figure.posed(e.pose, e.yaw_deg);
        }
        let figure = figure.with_stature(e.height_m, e.glb.clone());
        let [x, y, z] = e.position_enu;
        self.commands
            .spawn((figure, actors::FigureCoat(coat.clone()), actors::FigureSkin(skin.clone()), Visibility::default(), Transform::from_translation(enu(x, y, z))))
            .with_children(|figure| {
                figure.spawn((Mesh3d(body), MeshMaterial3d(coat), Transform::from_translation(Vec3::Y * 0.72), actors::FallbackBody));
                figure.spawn((Mesh3d(head), MeshMaterial3d(skin), Transform::from_translation(Vec3::Y * 1.62), actors::FallbackBody));
            });
    }
}

fn bounds(points: impl Iterator<Item = Vec3>) -> (Vec3, Vec3) {
    points.fold((Vec3::splat(f32::MAX), Vec3::splat(f32::MIN)), |(lo, hi), p| (lo.min(p), hi.max(p)))
}

/// Spec §5 sun (elevation, azimuth clockwise from north) with cascaded
/// shadows, from the manifest's environment.
fn spawn_sun_and_haze(commands: &mut Commands, assets: &AssetServer, pending: &mut Vec<UntypedHandle>, environment: &Environment, fog_visibility_m: Option<f32>) {
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
    commands.insert_resource(CameraLook { fog_visibility_m: fog_visibility_m.unwrap_or(environment.fog_visibility_m), exposure_ev100: environment.exposure_ev100 });
}

/// The manifest's haze and exposure, applied to every camera.
#[derive(Resource)]
pub struct CameraLook {
    pub fog_visibility_m: f32,
    pub exposure_ev100: f32,
}

/// True once the manifest and everything it named have loaded.
pub fn scene_ready(state: &SceneState, assets: &AssetServer, models: usize) -> bool {
    state.built && state.buildings_ready && models == 0 && state.pending.iter().all(|h| assets.is_loaded_with_dependencies(h.id()))
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
