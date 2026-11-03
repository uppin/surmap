//! Wind-swept pines and grass from the manifest's `vegetation` elements. Procedural meshes ported
//! from the FeroniaDemo (no external models); every number — palette, heights, wind damping, LOD
//! distance — comes from the species file (`species/<name>.species.json`).
//!
//! Pines are individual entities on Feronia's wind material (near and far LOD by visibility
//! range); grass is Feronia's GPU-instanced scatter on a hidden plane per stand, captured into a
//! visible instanced entity. Inside a fire's burnt area pines become charred trunks and grass
//! instances are dropped.

use std::f32::consts::TAU;
use std::sync::Arc;

use bevy::asset::RenderAssetUsages;
use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::{NoAutoAabb, VisibilityRange};
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use bevy::render::batching::NoAutomaticBatching;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use bevy_eidolon::components::InstanceData;
use bevy_eidolon::prelude::{GpuCullCompute, InstanceMaterialData, InstancedMeshMaterial};
use bevy_feronia::prelude::*;

use crate::fxdef::{Generator, SpeciesAsset, SpeciesDef, WindDamping};
use crate::record::SimTime;
use crate::scene_manifest::Vegetation;
use crate::wildfire::Wildfire;
use crate::world::{enu, Seeded};

/// The generated pine is this tall (m) at scale 1.
const PINE_MESH_HEIGHT_M: f32 = 15.0;
/// The generated grass clump is this tall (m) at scale 1.
const GRASS_MESH_HEIGHT_M: f32 = 0.67;
/// Fade band (m) between a LOD and the next.
const LOD_FADE_M: f32 = 4.0;
const GRASS_FADE_M: f32 = 15.0;

/// A stand waiting for its species file.
pub struct StandPlan {
    pub stand: Vegetation,
    pub species: Handle<SpeciesAsset>,
}

#[derive(Resource, Default)]
pub struct PendingStands(pub Vec<StandPlan>);

/// Queue a stand: its species file loads, then `grow_stands` plants it.
pub fn plan_stand(
    commands: &mut Commands,
    assets: &AssetServer,
    pending: &mut Vec<UntypedHandle>,
    plans: &mut PendingStands,
    stand: &Vegetation,
) {
    let species: Handle<SpeciesAsset> = assets.load(stand.species.clone());
    pending.push(species.clone().untyped());
    plans.0.push(StandPlan {
        stand: stand.clone(),
        species,
    });
    let _ = commands;
}

/// The materials and meshes one pine species needs.
struct PineKit {
    species: String,
    live: Handle<ExtendedWindAffectedMaterial>,
    charred: Handle<ExtendedWindAffectedMaterial>,
    meshes: [Handle<Mesh>; 2],
    trunks: [Handle<Mesh>; 2],
    damping: WindDamping,
    lod_distance_m: f32,
}

#[derive(Resource, Default)]
pub struct PineKits(Vec<PineKit>);

#[derive(Component)]
pub struct Pine {
    enu: Vec2,
    charred: bool,
    kit: usize,
}

/// One LOD of a pine: 0 detailed, 1 far.
#[derive(Component)]
pub struct PineLod(usize);

#[derive(Component)]
pub struct GrassStand {
    lod_distance_m: f32,
}

/// The visible instanced copy of a stand's scattered grass.
#[derive(Component)]
pub struct GrassField {
    all: Arc<Vec<InstanceData>>,
    origin: Vec3,
    shown: usize,
}

/// Dry grass until a fire reaches it; the stand is only ever scattered once.
#[derive(Component)]
pub struct Scattering;

fn srgb([r, g, b]: [f32; 3]) -> Color {
    Color::srgb(r, g, b)
}

fn palette_image(images: &mut Assets<Image>, colours: &[[f32; 3]]) -> Handle<Image> {
    let texel = |i: usize| {
        let [r, g, b] = colours[i.min(colours.len() - 1)];
        [r, g, b].map(|c| (c.clamp(0.0, 1.0) * 255.0).round() as u8)
    };
    let mut bytes = Vec::with_capacity(16);
    for i in 0..4 {
        let [r, g, b] = texel(i);
        bytes.extend([r, g, b, 255]);
    }
    let mut image = Image::new_fill(
        Extent3d {
            width: 4,
            height: 1,
            depth_or_array_layers: 1,
        },
        TextureDimension::D2,
        &bytes,
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::default(),
    );
    image.sampler = bevy::image::ImageSampler::nearest();
    images.add(image)
}

fn damped(mut wind: Wind, d: &WindDamping) -> Wind {
    wind.strength *= d.strength;
    wind.micro_strength *= d.micro_strength;
    wind.s_curve_strength *= d.s_curve_strength;
    wind.bop_strength *= d.bop_strength;
    wind.twist_strength *= d.twist_strength;
    wind
}

fn wind_material(
    palette: Handle<Image>,
    wind: &GlobalWind,
    damping: &WindDamping,
    noise: &WindTexture,
) -> ExtendedWindAffectedMaterial {
    bevy::pbr::ExtendedMaterial {
        base: StandardMaterial {
            base_color_texture: Some(palette),
            perceptual_roughness: 0.95,
            cull_mode: None,
            double_sided: true,
            ..default()
        },
        extension: WindAffectedExtension {
            current: damped(wind.current, damping),
            previous: damped(wind.previous, damping),
            aabb: Aabb::from_min_max(Vec3::new(-5.3, 0.0, -5.3), Vec3::new(5.3, 16.0, 5.3)),
            options: ScatterMaterialOptions {
                wind: WindOptions {
                    affected: true,
                    ..default()
                },
                ..default()
            },
            noise_texture: (**noise).clone(),
        },
    }
}

/// Plant every stand whose species has loaded.
#[allow(clippy::too_many_arguments)]
pub fn grow_stands(
    mut commands: Commands,
    mut plans: ResMut<PendingStands>,
    species: Res<Assets<SpeciesAsset>>,
    mut kits: ResMut<PineKits>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut images: ResMut<Assets<Image>>,
    mut wind_materials: ResMut<Assets<ExtendedWindAffectedMaterial>>,
    mut standard: ResMut<Assets<StandardMaterial>>,
    wind: Res<GlobalWind>,
    noise: Option<Res<WindTexture>>,
    mut scatter_state: ResMut<NextState<ScatterState>>,
) {
    let Some(noise) = noise else { return };
    let (ready, waiting): (Vec<_>, Vec<_>) = plans
        .0
        .drain(..)
        .partition(|p| species.get(&p.species).is_some());
    plans.0 = waiting;
    for plan in ready {
        let def = &species.get(&plan.species).expect("loaded").0;
        match def.generator {
            Generator::Pine => plant_pines(
                &mut commands,
                &plan.stand,
                def,
                &mut kits,
                &mut meshes,
                &mut images,
                &mut wind_materials,
                &wind,
                &noise,
            ),
            Generator::Grass => {
                sow_grass(&mut commands, &plan.stand, def, &mut meshes, &mut standard);
                // Feronia collects a root's assets only in its Setup → Collecting pass: run it again.
                scatter_state.set(ScatterState::Setup);
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn plant_pines(
    commands: &mut Commands,
    stand: &Vegetation,
    def: &SpeciesDef,
    kits: &mut PineKits,
    meshes: &mut Assets<Mesh>,
    images: &mut Assets<Image>,
    wind_materials: &mut Assets<ExtendedWindAffectedMaterial>,
    wind: &GlobalWind,
    noise: &WindTexture,
) {
    let kit = match kits.0.iter().position(|k| k.species == stand.species) {
        Some(index) => index,
        None => {
            let live = wind_materials.add(wind_material(
                palette_image(images, &def.palette),
                wind,
                &def.wind_damping,
                noise,
            ));
            let charred_palette = [def.burnt_palette[0]; 4];
            let charred = wind_materials.add(wind_material(
                palette_image(images, &charred_palette),
                wind,
                &def.wind_damping,
                noise,
            ));
            kits.0.push(PineKit {
                species: stand.species.clone(),
                live,
                charred,
                meshes: [meshes.add(pine(true, true)), meshes.add(pine(false, true))],
                trunks: [
                    meshes.add(pine(true, false)),
                    meshes.add(pine(false, false)),
                ],
                damping: def.wind_damping,
                lod_distance_m: def.lod_distance_m,
            });
            kits.0.len() - 1
        }
    };
    let [east, north] = stand.size_m;
    let count =
        (east * north / 100.0 * stand.density_per_100m2 * def.plants_per_unit).round() as u32;
    let mut rng = Seeded::new(stand.seed);
    for _ in 0..count {
        let x = stand.position_enu[0] + rng.range(-east / 2.0, east / 2.0);
        let y = stand.position_enu[1] + rng.range(-north / 2.0, north / 2.0);
        let height = rng.range(def.height_m[0], def.height_m[1]);
        let yaw = rng.range(0.0, TAU);
        let lod = kits.0[kit].lod_distance_m;
        let tree = commands
            .spawn((
                Pine {
                    enu: Vec2::new(x, y),
                    charred: false,
                    kit,
                },
                Transform::from_translation(enu(x, y, stand.position_enu[2]))
                    .with_rotation(Quat::from_rotation_y(yaw))
                    .with_scale(Vec3::splat(height / PINE_MESH_HEIGHT_M)),
                Visibility::default(),
            ))
            .id();
        for (index, range) in [
            (0, (0.0..0.0, lod..lod + LOD_FADE_M)),
            (1, (lod..lod + LOD_FADE_M, 1.0e6..1.0e6)),
        ] {
            let child = commands
                .spawn((
                    PineLod(index),
                    Mesh3d(kits.0[kit].meshes[index].clone()),
                    MeshMaterial3d(kits.0[kit].live.clone()),
                    Transform::default(),
                    VisibilityRange {
                        start_margin: range.0,
                        end_margin: range.1,
                        use_aabb: false,
                    },
                ))
                .id();
            commands.entity(tree).add_child(child);
        }
    }
}

fn sow_grass(
    commands: &mut Commands,
    stand: &Vegetation,
    def: &SpeciesDef,
    meshes: &mut Assets<Mesh>,
    standard: &mut Assets<StandardMaterial>,
) {
    let [east, north] = stand.size_m;
    let base = srgb(def.palette[0]);
    let tip = srgb(*def.palette.get(1).unwrap_or(&def.palette[0]));
    // Feronia's density is the side of the grid it scatters over the stand (density² instances).
    let clumps = east * north / 100.0 * stand.density_per_100m2 * def.plants_per_unit;
    let density = clumps.sqrt();
    commands.insert_resource(WorldSeed(stand.seed));
    commands.spawn((
        Name::new(format!("Grass {}", stand.id)),
        GrassStand {
            lod_distance_m: def.lod_distance_m,
        },
        Scattering,
        Mesh3d(meshes.add(Plane3d::default().mesh().size(east, north))),
        MeshMaterial3d(standard.add(StandardMaterial::default())),
        Transform::from_translation(enu(
            stand.position_enu[0],
            stand.position_enu[1],
            stand.position_enu[2],
        )),
        Visibility::Hidden,
        ScatterRoot::default(),
        LodConfig::none(),
        children![(
            bevy_feronia::instancing::scatter_layer("Dry grass"),
            DistributionDensity(density),
            InstanceJitter,
            InstanceRotationYaw,
            InstanceScaleRange {
                min: def.height_m[0] / GRASS_MESH_HEIGHT_M,
                max: def.height_m[1] / GRASS_MESH_HEIGHT_M
            },
            WindAffected,
            CurveNormals,
            StaticBend,
            DirectionalLights,
            bevy_eidolon::prelude::InstanceColor(base),
            InstanceColorGradient {
                top: tip,
                bottom: base,
                tint: 1.0,
                start: 0.25,
                end: 0.55
            },
            children![(
                Name::new("Dry grass clump"),
                Mesh3d(meshes.add(grass())),
                MeshMaterial3d(standard.add(StandardMaterial {
                    cull_mode: None,
                    double_sided: true,
                    ..default()
                }))
            )]
        )],
    ));
}

/// Ask Feronia to scatter each sown stand once.
pub fn scatter_stands(
    mut commands: Commands,
    stands: Query<Entity, (With<Scattering>, With<Aabb>)>,
) {
    for stand in &stands {
        commands.trigger(Scatter::<InstancedWindAffectedMaterial>::new(stand));
        commands.entity(stand).remove::<Scattering>();
    }
}

/// A stand's scattered instances live under its hidden root: copy them into a visible entity.
#[allow(clippy::type_complexity)]
pub fn show_grass(
    mut commands: Commands,
    scattered: Query<
        (
            Entity,
            &Mesh3d,
            &InstancedMeshMaterial<InstancedWindAffectedMaterial>,
            &InstanceMaterialData,
            &Aabb,
        ),
        (With<ScatteredInstance>, Added<InstanceMaterialData>),
    >,
    parents: Query<&ChildOf>,
    stands: Query<(&GrassStand, &GlobalTransform)>,
) {
    for (entity, mesh, material, data, bounds) in &scattered {
        let Some((stand, origin)) = std::iter::once(entity)
            .chain(parents.iter_ancestors(entity))
            .find_map(|e| stands.get(e).ok())
        else {
            continue;
        };
        info!("grass field: {} instances", data.instances.len());
        let mut shown = data.clone();
        shown.visibility_range = Vec4::new(
            0.0,
            0.0,
            stand.lod_distance_m,
            stand.lod_distance_m + GRASS_FADE_M,
        );
        commands.spawn((
            Name::new("Dry grass field"),
            GrassField {
                all: shown.instances.clone(),
                origin: origin.translation(),
                shown: shown.instances.len(),
            },
            Mesh3d(mesh.0.clone()),
            InstancedMeshMaterial(material.0.clone()),
            shown,
            *bounds,
            NoAutoAabb,
            NoAutomaticBatching,
            GpuCullCompute,
            Transform::from_translation(origin.translation()),
        ));
    }
}

/// Feronia's wind for each species, from the one scenario wind.
pub fn sync_vegetation_wind(
    wind: Res<GlobalWind>,
    kits: Res<PineKits>,
    mut materials: ResMut<Assets<ExtendedWindAffectedMaterial>>,
) {
    if !wind.is_changed() {
        return;
    }
    for kit in &kits.0 {
        for handle in [&kit.live, &kit.charred] {
            if let Some(material) = materials.get_mut(handle) {
                material.extension.current = damped(wind.current, &kit.damping);
                material.extension.previous = damped(wind.previous, &kit.damping);
            }
        }
    }
}

/// Seconds between burn checks.
const BURN_CHECK_S: f32 = 0.5;

/// Char the pines and drop the grass a fire's front has swept over.
#[allow(clippy::too_many_arguments)]
pub fn burn_vegetation(
    time: Res<Time>,
    sim: Res<SimTime>,
    fires: Option<Res<Wildfire>>,
    kits: Res<PineKits>,
    mut last_check: Local<f32>,
    mut pines: Query<(&mut Pine, &Children)>,
    mut lods: Query<(
        &PineLod,
        &mut Mesh3d,
        &mut MeshMaterial3d<ExtendedWindAffectedMaterial>,
    )>,
    mut fields: Query<(&mut GrassField, &mut InstanceMaterialData)>,
) {
    let Some(fires) = fires else { return };
    let now = sim.0.unwrap_or(time.elapsed_secs());
    // Newly planted vegetation is checked at once, whatever the clock.
    let fresh =
        pines.iter_mut().any(|(p, _)| p.is_added()) || fields.iter_mut().any(|(f, _)| f.is_added());
    if (now - *last_check).abs() < BURN_CHECK_S && *last_check <= now && !fresh {
        return;
    }
    *last_check = now;
    let mut charred = 0;
    for (mut pine, children) in &mut pines {
        if pine.charred || !fires.burnt(pine.enu, now) {
            continue;
        }
        pine.charred = true;
        charred += 1;
        let kit = &kits.0[pine.kit];
        for child in children.iter() {
            if let Ok((lod, mut mesh, mut material)) = lods.get_mut(child) {
                mesh.0 = kit.trunks[lod.0].clone();
                material.0 = kit.charred.clone();
            }
        }
    }
    if charred > 0 {
        info!("{charred} pines charred at t={now:.0} s");
    }
    for (mut field, mut data) in &mut fields {
        let kept: Vec<InstanceData> = field
            .all
            .iter()
            .filter(|i| {
                let world = field.origin + i.position;
                !fires.burnt(Vec2::new(world.x, -world.z), now)
            })
            .copied()
            .collect();
        if kept.len() != field.shown {
            field.shown = kept.len();
            data.instances = Arc::new(kept);
        }
    }
}

// ---- Procedural geometry (ported from the FeroniaDemo's meshes.rs) -------------------------

#[derive(Default)]
struct Geometry {
    positions: Vec<[f32; 3]>,
    normals: Vec<[f32; 3]>,
    uvs: Vec<[f32; 2]>,
    colors: Vec<[f32; 4]>,
}

const BARK: [f32; 4] = [0.16, 0.085, 0.038, 1.0];

impl Geometry {
    fn triangle(&mut self, points: [Vec3; 3], color: [f32; 4]) {
        let normal = (points[1] - points[0])
            .cross(points[2] - points[0])
            .normalize_or_zero();
        for (p, uv) in points.into_iter().zip([[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]]) {
            self.positions.push(p.to_array());
            self.normals.push(normal.to_array());
            self.uvs.push(uv);
            self.colors.push(color);
        }
    }

    fn finish(self) -> Mesh {
        // Eidolon's indirect instanced renderer requires an index buffer.
        let indices = Indices::U32((0..self.positions.len() as u32).collect());
        Mesh::new(
            PrimitiveTopology::TriangleList,
            RenderAssetUsages::default(),
        )
        .with_inserted_indices(indices)
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, self.positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, self.uvs)
        .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.colors)
    }

    fn cone(&mut self, bottom: f32, top: f32, radius: f32, tip_radius: f32, color: [f32; 4]) {
        for i in 0..10 {
            let a = i as f32 * TAU / 10.0;
            let b = (i + 1) as f32 * TAU / 10.0;
            let p = Vec3::new(a.cos() * radius, bottom, a.sin() * radius);
            let q = Vec3::new(b.cos() * radius, bottom, b.sin() * radius);
            let r = Vec3::new(a.cos() * tip_radius, top, a.sin() * tip_radius);
            let s = Vec3::new(b.cos() * tip_radius, top, b.sin() * tip_radius);
            self.triangle([p, r, q], color);
            if tip_radius > 0.0 {
                self.triangle([q, r, s], color);
            }
            self.triangle([Vec3::new(0.0, bottom, 0.0), p, q], color);
        }
    }

    fn stick(&mut self, start: Vec3, end: Vec3, radius: f32, tip_radius: f32) {
        let axis = (end - start).normalize();
        let side = axis.cross(Vec3::Y).normalize_or_zero();
        let up = axis.cross(side).normalize();
        for face in 0..5 {
            let a = face as f32 * TAU / 5.0;
            let b = (face + 1) as f32 * TAU / 5.0;
            let radial = |angle: f32| side * angle.cos() + up * angle.sin();
            let p = start + radial(a) * radius;
            let q = start + radial(b) * radius;
            let r = end + radial(a) * tip_radius;
            let s = end + radial(b) * tip_radius;
            self.triangle([p, q, r], BARK);
            self.triangle([q, s, r], BARK);
        }
    }
}

/// A pine of [`PINE_MESH_HEIGHT_M`]: tapered trunk, whorled branches and three-sided needles.
/// `needles: false` leaves the bare charred skeleton. UVs index a four-texel palette (bark first).
pub fn pine(detailed: bool, needles: bool) -> Mesh {
    let mut g = Geometry::default();
    g.cone(0.0, PINE_MESH_HEIGHT_M, 0.27, 0.025, BARK);
    let levels = if detailed { 7 } else { 5 };
    for level in 0..levels {
        let height = 5.2 + level as f32 * 9.0 / levels as f32;
        let length = 3.7 * (1.0 - (height - 5.2) / 12.0);
        for branch in 0..6 {
            let angle = branch as f32 * TAU / 6.0 + level as f32 * 2.39996;
            let forward = Vec3::new(angle.cos(), 0.0, angle.sin());
            let side = Vec3::new(-angle.sin(), 0.0, angle.cos());
            let root = Vec3::Y * height;
            let point = |t: f32| root + forward * length * t + Vec3::Y * (0.65 * t * t - 0.22 * t);
            let sections = if detailed { 4 } else { 2 };
            for segment in 0..sections {
                let t = segment as f32 / sections as f32;
                let u = (segment + 1) as f32 / sections as f32;
                g.stick(
                    point(t),
                    point(u),
                    0.065 * (1.0 - t) + 0.008,
                    0.065 * (1.0 - u) + 0.008,
                );
            }
            let twigs = if detailed { 3 } else { 2 };
            for twig in 0..twigs {
                let t = 0.25 + twig as f32 / twigs as f32 * 0.72;
                for sign in [-1.0, 1.0] {
                    let start = point(t);
                    let twig_dir =
                        (forward * 0.55 + side * sign * 0.82 + Vec3::Y * 0.28).normalize();
                    let twig_length = 0.85 * (1.0 - t * 0.5);
                    g.stick(start, start + twig_dir * twig_length, 0.015, 0.004);
                    if !needles {
                        continue;
                    }
                    let count = if detailed { 10 } else { 5 };
                    for needle in 0..count {
                        let u = needle as f32 / count as f32;
                        let anchor = start + twig_dir * twig_length * u;
                        for spoke in 0..3 {
                            let theta = spoke as f32 * TAU / 3.0 + needle as f32 * 1.7;
                            let radial = (side * theta.cos() + Vec3::Y * theta.sin()).normalize();
                            let direction = (radial * 0.85 + twig_dir * 0.55).normalize();
                            let length = 0.35 + 0.20 * (1.0 - u);
                            let width = if detailed { 0.014 } else { 0.028 };
                            let across = direction.cross(forward).normalize_or_zero() * width;
                            let tip = anchor + direction * length;
                            let freshness = ((needle + spoke) % 3) as f32;
                            let color = [
                                0.10 + 0.025 * freshness,
                                0.55 + 0.10 * freshness,
                                0.035,
                                1.0,
                            ];
                            let perpendicular = direction.cross(across).normalize_or_zero() * width;
                            let a = anchor + across;
                            let b = anchor - across * 0.5 + perpendicular * 0.8660254;
                            let c = anchor - across * 0.5 - perpendicular * 0.8660254;
                            g.triangle([a, b, tip], color);
                            g.triangle([b, c, tip], color);
                            g.triangle([c, a, tip], color);
                        }
                    }
                }
            }
        }
    }
    // Feronia's extended shader does not forward vertex colours: sample the matching palette
    // texel instead, keeping the wind-animated mesh.
    for (uv, color) in g.uvs.iter_mut().zip(&g.colors) {
        let swatch = if color[1] < 0.5 {
            0.0
        } else {
            1.0 + ((color[1] - 0.55) / 0.10).round()
        };
        *uv = [(swatch + 0.5) / 4.0, 0.5];
    }
    let mut mesh = g.finish();
    mesh.remove_attribute(Mesh::ATTRIBUTE_COLOR);
    mesh
}

/// A five-blade clump, [`GRASS_MESH_HEIGHT_M`] tall; Feronia reads height from inverted UV.y.
pub fn grass() -> Mesh {
    let mut g = Geometry::default();
    for blade in 0..5 {
        let angle = blade as f32 * 2.39996;
        let side = Vec3::new(angle.cos(), 0.0, angle.sin());
        let bend = Vec3::new(-angle.sin(), 0.0, angle.cos());
        let height = 0.43 + (blade % 3) as f32 * 0.12;
        let base = side * 0.09;
        for segment in 0..3 {
            let t = segment as f32 / 3.0;
            let u = (segment + 1) as f32 / 3.0;
            let center = |v: f32| base + Vec3::Y * height * v + bend * v * v * 0.18;
            let p = center(t) - side * 0.035 * (1.0 - t);
            let q = center(t) + side * 0.035 * (1.0 - t);
            let r = center(u) - side * 0.035 * (1.0 - u);
            let s = center(u) + side * 0.035 * (1.0 - u);
            g.triangle([p, q, r], [1.0; 4]);
            if segment < 2 {
                g.triangle([q, s, r], [1.0; 4]);
            }
        }
    }
    for (uv, position) in g.uvs.iter_mut().zip(&g.positions) {
        uv[1] = 1.0 - position[1] / GRASS_MESH_HEIGHT_M;
    }
    g.finish()
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::mesh::VertexAttributeValues;

    fn positions(mesh: &Mesh) -> Vec<[f32; 3]> {
        match mesh.attribute(Mesh::ATTRIBUTE_POSITION) {
            Some(VertexAttributeValues::Float32x3(p)) => p.clone(),
            _ => panic!("positions"),
        }
    }

    #[test]
    fn foliage_is_indexed_and_stands_on_the_ground() {
        for mesh in [
            pine(true, true),
            pine(false, true),
            pine(true, false),
            grass(),
        ] {
            let points = positions(&mesh);

            assert!(mesh.indices().is_some(), "Eidolon needs indices");
            assert!(points
                .iter()
                .all(|p| p[1] >= 0.0 && p.iter().all(|v| v.is_finite())));
            assert!(points.iter().any(|p| p[1] == 0.0));
        }
    }

    #[test]
    fn a_charred_pine_is_the_bare_skeleton_of_the_live_one() {
        assert!(pine(true, false).count_vertices() < pine(true, true).count_vertices());
    }
}
