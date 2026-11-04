//! Models from the manifest, once their GLB scenes have spawned: a collider from the meshes' own
//! bounds (box or trimesh) and, for ground-truth instances, their ENU box.

use bevy::camera::primitives::Aabb;
use bevy::prelude::*;
use bevy::scene::SceneInstanceReady;
use bevy_rapier3d::prelude::*;

use super::{GroundTruth, PendingModel};
use crate::scene_manifest::ColliderKind;
use crate::wire::GroundTruthObject;

/// The scene of a model has spawned; its bounds exist one frame later.
#[derive(Component)]
pub struct ModelSpawned;

pub(super) fn on_model_ready(ready: On<SceneInstanceReady>, mut commands: Commands) {
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
    looks: Query<&MeshMaterial3d<StandardMaterial>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    for (root, pending, transform) in &models {
        let parts: Vec<Entity> = children.iter_descendants(root).filter(|e| mesh_parts.contains(*e)).collect();
        if parts.is_empty() || parts.iter().any(|e| mesh_parts.get(*e).is_ok_and(|(_, aabb, _)| aabb.is_none())) {
            continue;
        }
        if !pending.instance.normal_maps {
            drop_normal_maps(&parts, &looks, &mut materials);
        }
        resolve_model(&mut commands, root, pending, transform, &parts, &mesh_parts, &meshes, &mut truth);
    }
}

/// The manifest dropped this model's normal maps (`normal_maps: false`): clear them on every
/// material its meshes wear.
fn drop_normal_maps(parts: &[Entity], looks: &Query<&MeshMaterial3d<StandardMaterial>>, materials: &mut Assets<StandardMaterial>) {
    for look in parts.iter().filter_map(|part| looks.get(*part).ok()) {
        if let Some(material) = materials.get_mut(&look.0) {
            material.normal_map_texture = None;
        }
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
