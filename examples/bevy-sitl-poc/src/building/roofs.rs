//! Roof shapes: a flat roof with its parapet, and gabled, hipped and pyramidal roofs with eaves.
//! The roof surface takes the roof material; the parapet and the gable ends take the facade's.

use bevy::prelude::*;

use super::look::{BuildingLook, FlatRoof, PitchedRoof};
use super::meshes::MeshBuilder;
use crate::building_style::RoofShape;

pub struct RoofMeshes {
    /// The roof surface (roof material).
    pub roof: MeshBuilder,
    /// Parapet or gable ends (facade material).
    pub trim: MeshBuilder,
    /// Height of the highest point above the wall tops, m.
    pub rise_m: f32,
}

fn top_down(p: Vec3) -> Vec2 {
    Vec2::new(p.x, p.z)
}

fn flat(size: Vec3, parapet: FlatRoof) -> RoofMeshes {
    let (a, b, h) = (size.x / 2.0, size.z / 2.0, size.y);
    let mut roof = MeshBuilder::default();
    let corner = |x: f32, z: f32, y: f32| Vec3::new(x, y, z);
    let plane = [
        corner(-a, -b, h),
        corner(a, -b, h),
        corner(a, b, h),
        corner(-a, b, h),
    ];
    roof.quad(plane, plane.map(top_down), Vec3::Y);
    let mut trim = MeshBuilder::default();
    if parapet.parapet_m > 0.0 {
        let top = h + parapet.parapet_m;
        let (ia, ib) = (
            a - parapet.parapet_thickness_m,
            b - parapet.parapet_thickness_m,
        );
        // Outer and inner faces of the four walls of the ring, and the cap.
        for (outer, inner) in [((a, b), (ia, ib))] {
            let rings = [(outer.0, outer.1, 1.0), (inner.0, inner.1, -1.0)];
            for (ra, rb, side) in rings {
                let walls = [
                    (
                        [
                            corner(-ra, rb, h),
                            corner(ra, rb, h),
                            corner(ra, rb, top),
                            corner(-ra, rb, top),
                        ],
                        Vec3::Z * side,
                    ),
                    (
                        [
                            corner(-ra, -rb, h),
                            corner(ra, -rb, h),
                            corner(ra, -rb, top),
                            corner(-ra, -rb, top),
                        ],
                        Vec3::NEG_Z * side,
                    ),
                    (
                        [
                            corner(ra, -rb, h),
                            corner(ra, rb, h),
                            corner(ra, rb, top),
                            corner(ra, -rb, top),
                        ],
                        Vec3::X * side,
                    ),
                    (
                        [
                            corner(-ra, -rb, h),
                            corner(-ra, rb, h),
                            corner(-ra, rb, top),
                            corner(-ra, -rb, top),
                        ],
                        Vec3::NEG_X * side,
                    ),
                ];
                for (quad, facing) in walls {
                    let uv = quad.map(|p| Vec2::new(p.x + p.z, p.y));
                    trim.quad(quad, uv, facing);
                }
            }
            let caps = [
                [
                    corner(-a, b, top),
                    corner(a, b, top),
                    corner(ia, ib, top),
                    corner(-ia, ib, top),
                ],
                [
                    corner(-a, -b, top),
                    corner(a, -b, top),
                    corner(ia, -ib, top),
                    corner(-ia, -ib, top),
                ],
                [
                    corner(a, -b, top),
                    corner(a, b, top),
                    corner(ia, ib, top),
                    corner(ia, -ib, top),
                ],
                [
                    corner(-a, -b, top),
                    corner(-a, b, top),
                    corner(-ia, ib, top),
                    corner(-ia, -ib, top),
                ],
            ];
            for quad in caps {
                trim.quad(quad, quad.map(top_down), Vec3::Y);
            }
        }
    }
    RoofMeshes {
        roof,
        trim,
        rise_m: parapet.parapet_m,
    }
}

/// A point of a pitched roof in its ridge frame: `r` along the ridge, `c` across it, height `y`,
/// mapped back to the building's axes (`along_x`: the ridge runs east-west).
fn at(along_x: bool, r: f32, c: f32, y: f32) -> Vec3 {
    if along_x {
        Vec3::new(r, y, c)
    } else {
        Vec3::new(c, y, r)
    }
}

fn pitched(size: Vec3, shape: RoofShape, roof: PitchedRoof) -> RoofMeshes {
    let along_x = size.x >= size.z;
    let (a, b) = if along_x {
        (size.x / 2.0, size.z / 2.0)
    } else {
        (size.z / 2.0, size.x / 2.0)
    };
    let (h, e) = (size.y, roof.eave_m);
    let slope = roof.pitch_deg.to_radians().tan();
    let rise = b * slope;
    let (ridge_y, eave_y) = (h + rise, h - e * slope);
    let ridge_half = if shape == RoofShape::Gabled {
        a + e
    } else if shape == RoofShape::Hipped {
        (a - b).max(0.0)
    } else {
        0.0
    };
    let p = |r: f32, c: f32, y: f32| at(along_x, r, c, y);
    let mut surface = MeshBuilder::default();
    let mut trim = MeshBuilder::default();
    // The two long sides: eave line at c = ±(b + e), ridge line at c = 0.
    for side in [1.0_f32, -1.0] {
        let quad = [
            p(-(a + e), side * (b + e), eave_y),
            p(a + e, side * (b + e), eave_y),
            p(ridge_half, 0.0, ridge_y),
            p(-ridge_half, 0.0, ridge_y),
        ];
        let hint = Vec3::Y + p(0.0, side, 0.0);
        surface.quad(quad, quad.map(top_down), hint);
    }
    if shape == RoofShape::Gabled {
        for end in [1.0_f32, -1.0] {
            let triangle = [
                p(end * a, -b, h),
                p(end * a, b, h),
                p(end * a, 0.0, ridge_y),
            ];
            trim.triangle(
                triangle,
                triangle.map(|v| Vec2::new(v.x + v.z, v.y)),
                p(end, 0.0, 0.0),
            );
        }
    } else {
        for end in [1.0_f32, -1.0] {
            let triangle = [
                p(end * (a + e), -(b + e), eave_y),
                p(end * (a + e), b + e, eave_y),
                p(end * ridge_half, 0.0, ridge_y),
            ];
            surface.triangle(triangle, triangle.map(top_down), Vec3::Y + p(end, 0.0, 0.0));
        }
    }
    RoofMeshes {
        roof: surface,
        trim,
        rise_m: rise,
    }
}

/// The roof of a building box `size` (east, up, south).
pub fn build_roof(shape: RoofShape, size: Vec3, look: &BuildingLook) -> RoofMeshes {
    match look.roof_shapes.pitched(shape) {
        None => flat(size, look.roof_shapes.flat),
        Some(roof) => pitched(size, shape, roof),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn look() -> BuildingLook {
        let text = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/building/look.json"
        ))
        .expect("shipped");
        BuildingLook::from_json(&text).expect("look")
    }

    #[test]
    fn a_flat_roof_rises_by_its_parapet_and_has_no_gable_ends() {
        let roof = build_roof(RoofShape::Flat, Vec3::new(10.0, 12.0, 8.0), &look());

        assert_eq!(roof.rise_m, 0.6);
        assert!(!roof.trim.is_empty());
    }

    #[test]
    fn a_gabled_roof_rises_by_half_its_short_span_times_the_pitch() {
        let roof = build_roof(RoofShape::Gabled, Vec3::new(12.0, 6.0, 8.0), &look());

        assert!((roof.rise_m - 4.0 * 35.0_f32.to_radians().tan()).abs() < 1e-4);
        assert!(!roof.trim.is_empty(), "gable ends");
    }

    #[test]
    fn hipped_and_pyramidal_roofs_have_no_gable_ends() {
        let hipped = build_roof(RoofShape::Hipped, Vec3::new(12.0, 6.0, 8.0), &look());
        let pyramid = build_roof(RoofShape::Pyramidal, Vec3::new(8.0, 6.0, 8.0), &look());

        assert!(hipped.trim.is_empty() && pyramid.trim.is_empty());
        assert!(!hipped.roof.is_empty() && !pyramid.roof.is_empty());
    }
}
