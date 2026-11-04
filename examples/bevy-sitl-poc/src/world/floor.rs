//! The map floor in the world: its textured plane, its collider and its credit.
//!
//! Split out of `world` for the file-length gate; `world` calls `spawn_map_floor`
//! and `is_hidden_by_floor` from here.

use bevy::prelude::*;
use bevy_rapier3d::prelude::*;

use super::enu;
use crate::scene_manifest::{Element, MapFloor};

/// The map floor's fixed collider in world space: its centre and half-extents
/// (x east, y up, z south). It is spawned unrotated — the floor plane's -90°
/// X rotation would stand a cuboid on edge as a wall — as a slab spanning the
/// floor whose top is at 0 m, the level the preset ground box's top used to be.
pub fn floor_collider(east_m: f32, north_m: f32) -> (Vec3, [f32; 3]) {
    (enu(0.0, 0.0, -0.02), [east_m / 2.0, 0.02, north_m / 2.0])
}
/// The credit line the scene shows while a map floor is down: the floor's own
/// attribution, or OpenStreetMap's when the manifest records none.
pub fn floor_attribution_text(floor: &crate::scene_manifest::MapFloor) -> String {
    floor
        .attribution
        .clone()
        .unwrap_or_else(|| "© OpenStreetMap contributors".to_owned())
}
/// A hand-edited manifest may still carry the preset `ground` box under a map
/// floor; its opaque top would hide the floor, so the renderer skips it when
/// a floor is present (the station removes it in `set_map_floor`).
pub fn is_hidden_by_floor(element: &Element, has_floor: bool) -> bool {
    has_floor
        && matches!(element, Element::Box(e) if e.ground || matches!(e.id.as_str(), "ground" | "block-ground" | "apron"))
}

/// Spawn the floor: one untiled textured plane at the ENU origin, a separate
/// unrotated fixed collider slab under it, and the credit line in the corner.
pub fn spawn_map_floor(
    commands: &mut Commands,
    assets: &AssetServer,
    materials: &mut Assets<StandardMaterial>,
    meshes: &mut Assets<Mesh>,
    pending: &mut Vec<UntypedHandle>,
    floor: &MapFloor,
) {
    let (_, [east, north]) = floor.centre_and_size_enu();
    let texture: Handle<Image> = assets.load(floor.texture.clone());
    pending.push(texture.clone().untyped());
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
        Transform::from_translation(super::enu(0.0, 0.0, -0.02))
            .with_rotation(Quat::from_rotation_x(-std::f32::consts::FRAC_PI_2)),
    ));
    // The floor is what the scene stands on now that the preset ground box is
    // gone. Its collider is a separate, unrotated entity: on the rotated plane
    // entity a cuboid would stand on edge as a wall through the origin.
    let (centre, half) = floor_collider(east as f32, north as f32);
    commands.spawn((
        Name::new("Map floor collider"),
        RigidBody::Fixed,
        Collider::cuboid(half[0], half[1], half[2]),
        Transform::from_translation(centre),
    ));
    commands.spawn((
        Text::new(floor_attribution_text(floor)),
        TextFont { font_size: 11.0, ..default() },
        TextColor(Color::WHITE),
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(12.0),
            bottom: Val::Px(12.0),
            ..default()
        },
    ));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene_manifest::BoxElement;

    #[test]
    fn the_floor_collider_is_a_world_space_slab_under_the_floor() {
        // Given a 130 x 111 m floor
        // When its collider is placed in the world
        let (centre, half) = floor_collider(130.0, 111.0);
        let (min, max) = (centre - Vec3::from(half), centre + Vec3::from(half));

        // Then in world space (x east, y up, z south) it is a slab: it spans the
        // floor east and north, and its top is at 0 m with 4 cm below it — not a
        // wall standing ±55 m tall through the origin
        assert_eq!((min.x, max.x), (-65.0, 65.0), "east span");
        assert_eq!((min.y, max.y), (-0.04, 0.0), "up span: a slab, not a wall");
        assert_eq!((min.z, max.z), (-55.5, 55.5), "north span");
    }
    #[test]
    fn the_preset_ground_is_skipped_only_when_a_floor_replaces_it() {
        // Given the preset ground box and an ordinary road box
        let ground = Element::Box(BoxElement {
            id: "ground".into(), material: "ground".into(), size_m: [200.0, 200.0, 0.2],
            position_enu: [0.0, 0.0, -0.2], yaw_deg: 0.0, tint: None, uv_scale: None,
            collider: true, scatter: None, ground_truth: None, water: false, ground: false,
        });
        let road = Element::Box(BoxElement {
            id: "road-1".into(), material: "ground".into(), size_m: [50.0, 8.0, 0.1],
            position_enu: [0.0, 0.0, -0.1], yaw_deg: 0.0, tint: None, uv_scale: None,
            collider: true, scatter: None, ground_truth: None, water: false, ground: false,
        });

        // Then only the preset ground is hidden by a floor
        assert!(is_hidden_by_floor(&ground, true));
        assert!(!is_hidden_by_floor(&ground, false));
        assert!(!is_hidden_by_floor(&road, true));
    }
}
