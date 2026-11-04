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
use bevy::camera::visibility::VisibilityRange;
use bevy::ecs::system::SystemParam;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use bevy_eidolon::components::InstanceData;
use bevy_eidolon::prelude::InstanceMaterialData;
use bevy_feronia::prelude::*;

use crate::fxdef::{Generator, SpeciesAsset, SpeciesDef, WindDamping};
use crate::scene_manifest::Vegetation;
use crate::wildfire::{SimClock, Wildfire};
use crate::world::{enu, Seeded};

mod grass;
mod meshes;

#[cfg(test)]
pub use grass::grass_instances;
pub use grass::{scatter_stands, show_grass};
use grass::{sow_grass, GrassField};
use meshes::{pine, PINE_MESH_HEIGHT_M};

/// Fade band (m) between a LOD and the next.
const LOD_FADE_M: f32 = 4.0;

/// A stand waiting for its species file.
pub struct StandPlan {
    pub stand: Vegetation,
    pub species: Handle<SpeciesAsset>,
}

#[derive(Resource, Default)]
pub struct PendingStands(pub Vec<StandPlan>);

/// Queue a stand: its species file loads, then `grow_stands` plants it.
pub fn plan_stand(
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

/// What planting needs: the pine kits, the asset stores plants are built into, and the wind.
#[derive(SystemParam)]
pub struct Nursery<'w> {
    kits: ResMut<'w, PineKits>,
    meshes: ResMut<'w, Assets<Mesh>>,
    images: ResMut<'w, Assets<Image>>,
    wind_materials: ResMut<'w, Assets<ExtendedWindAffectedMaterial>>,
    standard: ResMut<'w, Assets<StandardMaterial>>,
    wind: Res<'w, GlobalWind>,
}

/// Plant every stand whose species has loaded.
pub fn grow_stands(
    mut commands: Commands,
    mut plans: ResMut<PendingStands>,
    species: Res<Assets<SpeciesAsset>>,
    mut nursery: Nursery,
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
            Generator::Pine => plant_pines(&mut commands, &plan.stand, def, &mut nursery, &noise),
            Generator::Grass => {
                sow_grass(
                    &mut commands,
                    &plan.stand,
                    def,
                    &mut nursery.meshes,
                    &mut nursery.standard,
                );
                // Feronia collects a root's assets only in its Setup → Collecting pass: run it again.
                scatter_state.set(ScatterState::Setup);
            }
        }
    }
}

fn plant_pines(
    commands: &mut Commands,
    stand: &Vegetation,
    def: &SpeciesDef,
    nursery: &mut Nursery,
    noise: &WindTexture,
) {
    let Nursery {
        kits,
        meshes,
        images,
        wind_materials,
        wind,
        ..
    } = nursery;
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
pub fn burn_vegetation(
    clock: SimClock,
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
    let now = clock.now();
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
