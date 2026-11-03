//! The flat geometry of a fire on the ground: walking its front by arc length, and the
//! scorched disk and glowing rim meshes rebuilt from it.

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;

use crate::fxdef::GroundDef;
use crate::world::enu;

pub(super) fn empty_mesh() -> Mesh {
    let mut mesh = Mesh::new(
        PrimitiveTopology::TriangleList,
        RenderAssetUsages::default(),
    );
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, Vec::<[f32; 3]>::new());
    mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, Vec::<[f32; 3]>::new());
    mesh.insert_indices(Indices::U32(Vec::new()));
    mesh
}

/// The ENU point `fraction` (0..1) of the way round a closed polygon, by arc length.
pub fn along(points: &[Vec2], length: f32, fraction: f32) -> Vec2 {
    let mut remaining = fraction * length;
    for (a, b) in points.iter().zip(points.iter().cycle().skip(1)) {
        let edge = a.distance(*b);
        if remaining <= edge {
            return a.lerp(*b, if edge > 0.0 { remaining / edge } else { 0.0 });
        }
        remaining -= edge;
    }
    points[0]
}

pub(super) fn enu_at(p: Vec2) -> Vec3 {
    enu(p.x, p.y, 0.0)
}

pub(super) fn perimeter_length(points: &[Vec2]) -> f32 {
    points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .map(|(a, b)| a.distance(*b))
        .sum()
}

/// The scorched disk inside the front and the glowing rim `glow_width_m` wide just inside it,
/// as flat meshes `height_m` above the ground. ENU counter-clockwise is counter-clockwise from
/// above in Bevy, so both face up.
pub(super) fn scorch_meshes(front: &[Vec2], centroid: Vec2, ground: GroundDef) -> (Mesh, Mesh) {
    let inner: Vec<Vec2> = front
        .iter()
        .map(|p| {
            *p + (centroid - *p).normalize_or_zero()
                * ground.glow_width_m.min(p.distance(centroid) * 0.9)
        })
        .collect();
    let at = |p: Vec2| enu(p.x, p.y, ground.height_m).to_array();
    let mut disk = (Vec::new(), Vec::new());
    for (a, b) in inner.iter().zip(inner.iter().cycle().skip(1)) {
        let base = disk.0.len() as u32;
        disk.0.extend([at(centroid), at(*a), at(*b)]);
        disk.1.extend([base, base + 1, base + 2]);
    }
    let mut ring = (Vec::new(), Vec::new());
    for i in 0..front.len() {
        let j = (i + 1) % front.len();
        let base = ring.0.len() as u32;
        ring.0
            .extend([at(front[i]), at(front[j]), at(inner[j]), at(inner[i])]);
        ring.1
            .extend([base, base + 1, base + 3, base + 1, base + 2, base + 3]);
    }
    (flat_mesh(disk), flat_mesh(ring))
}

pub(super) fn flat_mesh((positions, indices): (Vec<[f32; 3]>, Vec<u32>)) -> Mesh {
    let normals = vec![[0.0, 1.0, 0.0]; positions.len()];
    Mesh::new(
        PrimitiveTopology::TriangleList,
        RenderAssetUsages::default(),
    )
    .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
    .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
    .with_inserted_indices(Indices::U32(indices))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn square() -> Vec<Vec2> {
        vec![
            Vec2::new(0.0, 0.0),
            Vec2::new(4.0, 0.0),
            Vec2::new(4.0, 4.0),
            Vec2::new(0.0, 4.0),
        ]
    }

    #[test]
    fn a_point_along_the_perimeter_walks_the_edges_by_arc_length() {
        let square = square();

        assert_eq!(along(&square, 16.0, 0.125), Vec2::new(2.0, 0.0));
        assert_eq!(along(&square, 16.0, 0.375), Vec2::new(4.0, 2.0));
    }

    #[test]
    fn the_scorched_disk_and_rim_face_up() {
        let ground = GroundDef {
            height_m: 0.02,
            colour: [0.0; 3],
            roughness: 1.0,
            glow_width_m: 0.5,
            glow_colour: [1.0; 3],
            glow_intensity: 1.0,
        };
        let front = [
            Vec2::new(2.0, 0.0),
            Vec2::new(0.0, 2.0),
            Vec2::new(-2.0, 0.0),
            Vec2::new(0.0, -2.0),
        ];

        let (disk, ring) = scorch_meshes(&front, Vec2::ZERO, ground);

        for mesh in [disk, ring] {
            let positions: Vec<Vec3> = mesh
                .attribute(Mesh::ATTRIBUTE_POSITION)
                .and_then(|a| a.as_float3())
                .expect("positions")
                .iter()
                .map(|p| Vec3::from(*p))
                .collect();
            let indices: Vec<u32> = mesh
                .indices()
                .expect("indexed")
                .iter()
                .map(|i| i as u32)
                .collect();
            assert!(indices.chunks(3).all(|t| {
                let (a, b, c) = (
                    positions[t[0] as usize],
                    positions[t[1] as usize],
                    positions[t[2] as usize],
                );
                (b - a).cross(c - a).y > 0.0
            }));
        }
    }
}
