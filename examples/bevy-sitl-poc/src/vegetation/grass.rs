//! Feronia's GPU-instanced dry grass: each stand is scattered once on a hidden plane, then copied
//! into a visible instanced field that `burn_vegetation` thins as the fire passes.

use std::sync::Arc;

use bevy::camera::primitives::Aabb;
use bevy::camera::visibility::NoAutoAabb;
use bevy::prelude::*;
use bevy::render::batching::NoAutomaticBatching;
use bevy_eidolon::components::InstanceData;
use bevy_eidolon::prelude::{GpuCullCompute, InstanceMaterialData, InstancedMeshMaterial};
use bevy_feronia::prelude::*;

use super::meshes::{grass, GRASS_MESH_HEIGHT_M};
use super::srgb;
use crate::fxdef::SpeciesDef;
use crate::scene_manifest::Vegetation;
use crate::world::enu;

/// Fade band (m) at the far end of the grass LOD.
const GRASS_FADE_M: f32 = 15.0;

#[derive(Component)]
pub struct GrassStand {
    lod_distance_m: f32,
}

/// The visible instanced copy of a stand's scattered grass.
#[derive(Component)]
pub struct GrassField {
    pub(super) all: Arc<Vec<InstanceData>>,
    pub(super) origin: Vec3,
    pub(super) shown: usize,
}

/// Dry grass until a fire reaches it; the stand is only ever scattered once.
#[derive(Component)]
pub struct Scattering;

pub(super) fn sow_grass(
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
