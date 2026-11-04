//! Flat-shaded mesh building for walls, roofs and glazing: quads and triangles oriented to face a
//! given outward direction, with UVs in metres (so a material's `uv_scale` is repeats per metre)
//! and an optional per-vertex colour (soot fading out).

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;

const WHITE: [f32; 4] = [1.0; 4];

#[derive(Default)]
pub struct MeshBuilder {
    positions: Vec<[f32; 3]>,
    normals: Vec<[f32; 3]>,
    uvs: Vec<[f32; 2]>,
    colours: Vec<[f32; 4]>,
    indices: Vec<u32>,
    coloured: bool,
}

impl MeshBuilder {
    pub fn is_empty(&self) -> bool {
        self.indices.is_empty()
    }

    fn polygon(&mut self, corners: &[Vec3], uvs: &[Vec2], outward: Vec3, colours: &[[f32; 4]]) {
        let facing = (corners[1] - corners[0]).cross(corners[2] - corners[0]);
        let flip = facing.dot(outward) < 0.0;
        let normal = if flip { -facing } else { facing }.normalize_or_zero();
        let base = self.positions.len() as u32;
        for (i, corner) in corners.iter().enumerate() {
            self.positions.push(corner.to_array());
            self.normals.push(normal.to_array());
            self.uvs.push(uvs[i].to_array());
            self.colours.push(colours[i]);
        }
        let order: &[u32] = match (corners.len(), flip) {
            (3, false) => &[0, 1, 2],
            (3, true) => &[0, 2, 1],
            (_, false) => &[0, 1, 2, 0, 2, 3],
            (_, true) => &[0, 2, 1, 0, 3, 2],
        };
        self.indices.extend(order.iter().map(|i| base + i));
    }

    /// A quad seen counter-clockwise from the side `outward` points to.
    pub fn quad(&mut self, corners: [Vec3; 4], uvs: [Vec2; 4], outward: Vec3) {
        self.polygon(&corners, &uvs, outward, &[WHITE; 4]);
    }

    /// A quad with a colour at each corner.
    pub fn quad_coloured(
        &mut self,
        corners: [Vec3; 4],
        uvs: [Vec2; 4],
        outward: Vec3,
        colours: [[f32; 4]; 4],
    ) {
        self.coloured = true;
        self.polygon(&corners, &uvs, outward, &colours);
    }

    pub fn triangle(&mut self, corners: [Vec3; 3], uvs: [Vec2; 3], outward: Vec3) {
        self.polygon(&corners, &uvs, outward, &[WHITE; 3]);
    }

    pub fn build(self) -> Mesh {
        let mut mesh = Mesh::new(
            PrimitiveTopology::TriangleList,
            RenderAssetUsages::default(),
        );
        mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, self.positions);
        mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, self.normals);
        mesh.insert_attribute(Mesh::ATTRIBUTE_UV_0, self.uvs);
        if self.coloured {
            mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, self.colours);
        }
        mesh.insert_indices(Indices::U32(self.indices));
        // A mesh without a normal-mapped material still builds; one that cannot get tangents is
        // left without them.
        let _ = mesh.generate_tangents();
        mesh
    }
}

/// One wall of a building box, in the building's local frame (x east, y up, z south).
#[derive(Debug, Clone, Copy)]
pub struct Face {
    pub normal: Vec3,
    /// Along the wall, to the right seen from outside.
    pub u: Vec3,
    /// The wall's middle at ground level.
    pub centre: Vec3,
    pub width: f32,
}

impl Face {
    /// The point `s` along the wall, `t` up, and `depth` metres inside the wall plane.
    pub fn point(&self, s: f32, t: f32, depth: f32) -> Vec3 {
        self.centre + self.u * s + Vec3::Y * t - self.normal * depth
    }

    /// A rectangle on the wall: `s0..s1` along, `t0..t1` up, `depth` inside the plane.
    pub fn rect(&self, s: [f32; 2], t: [f32; 2], depth: f32) -> [Vec3; 4] {
        [
            self.point(s[0], t[0], depth),
            self.point(s[1], t[0], depth),
            self.point(s[1], t[1], depth),
            self.point(s[0], t[1], depth),
        ]
    }
}

/// The four walls of a box `size` (east, up, south).
pub fn faces(size: Vec3) -> [Face; 4] {
    let face = |normal: Vec3, extent: f32, width: f32| Face {
        normal,
        u: Vec3::Y.cross(normal),
        centre: normal * extent,
        width,
    };
    [
        face(Vec3::Z, size.z / 2.0, size.x),
        face(Vec3::X, size.x / 2.0, size.z),
        face(Vec3::NEG_Z, size.z / 2.0, size.x),
        face(Vec3::NEG_X, size.x / 2.0, size.z),
    ]
}

/// UVs of a rectangle whose metres are `(s, t)`.
pub fn metres(s: [f32; 2], t: [f32; 2]) -> [Vec2; 4] {
    [
        Vec2::new(s[0], t[0]),
        Vec2::new(s[1], t[0]),
        Vec2::new(s[1], t[1]),
        Vec2::new(s[0], t[1]),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_quad_faces_the_side_it_is_asked_to() {
        let mut builder = MeshBuilder::default();
        let flat = [Vec3::ZERO, Vec3::X, Vec3::new(1.0, 0.0, 1.0), Vec3::Z];

        builder.quad(flat, metres([0.0, 1.0], [0.0, 1.0]), Vec3::Y);
        builder.quad(flat, metres([0.0, 1.0], [0.0, 1.0]), Vec3::NEG_Y);

        assert_eq!(builder.normals[0], [0.0, 1.0, 0.0]);
        assert_eq!(builder.normals[4], [0.0, -1.0, 0.0]);
    }

    #[test]
    fn a_wall_faces_away_from_the_building_and_runs_right_seen_from_outside() {
        let walls = faces(Vec3::new(10.0, 6.0, 8.0));

        let south = walls[0];

        assert_eq!(south.normal, Vec3::Z);
        assert_eq!(south.u, Vec3::X);
        assert_eq!(south.point(2.0, 3.0, 0.5), Vec3::new(2.0, 3.0, 3.5));
    }
}
