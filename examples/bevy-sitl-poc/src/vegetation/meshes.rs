//! Procedural pine and grass meshes, ported from the FeroniaDemo's `meshes.rs`: no external
//! models, so a stand is a JSON edit.

use std::f32::consts::TAU;

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;

/// The generated pine is this tall (m) at scale 1.
pub(super) const PINE_MESH_HEIGHT_M: f32 = 15.0;
/// The generated grass clump is this tall (m) at scale 1.
pub(super) const GRASS_MESH_HEIGHT_M: f32 = 0.67;

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
