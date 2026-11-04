//! A building's walls, floor by floor: punched windows with a recess, frame, pane and the glow
//! plane behind them, or a curtain wall of glass between spandrel bands and mullions. Each floor
//! keeps its parts in separate meshes so fire can break its panes, light its glow and char its wall
//! without touching its neighbours.

use bevy::prelude::*;

use super::look::{BuildingLook, FireLook};
use super::meshes::{faces, metres, Face, MeshBuilder};
use crate::building_style::{Glazing, GlazingKind};

/// A window (or a curtain-wall bay) flames can come out of: its outside middle, local space.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Opening {
    pub at: Vec3,
    pub width_m: f32,
}

/// One floor's meshes by material, and where its flames come from.
#[derive(Default)]
pub struct FloorMeshes {
    /// The wall (the facade material; a curtain wall's spandrel bands).
    pub wall: MeshBuilder,
    /// Window frames, mullions and rails.
    pub frame: MeshBuilder,
    /// The panes: hidden once the floor burns.
    pub pane: MeshBuilder,
    /// The emissive glow behind the panes.
    pub glow: MeshBuilder,
    /// Soot fading up the wall above the windows.
    pub soot: MeshBuilder,
    pub openings: Vec<Opening>,
}

/// What a floor is drawn with: the glazing, and the window ratio of this floor.
pub struct FloorPlan<'a> {
    pub glazing: &'a Glazing,
    pub window_ratio: Option<f32>,
}

/// Sizes of a building's walls.
#[derive(Clone, Copy)]
pub struct Shell {
    /// East, up, south (m).
    pub size: Vec3,
    pub floors: u32,
}

impl Shell {
    pub fn floor_m(&self) -> f32 {
        self.size.y / self.floors as f32
    }
}

/// How far a pane stands from its frame's front, so the two never z-fight.
const PANE_OFFSET_M: f32 = 0.005;
/// Soot and flames sit this far in front of the wall.
const PROUD_M: f32 = 0.01;
const FLAME_OUT_M: f32 = 0.25;
/// Margins a window leaves around itself in its cell and floor, m.
const PIER_M: f32 = 0.5;
const SILL_HEAD_M: f32 = 0.5;
/// Share of the free height that lies under the sill.
const SILL_SHARE: f32 = 0.4;
/// The glow plane is wider than the window by this much on each side.
const GLOW_MARGIN_M: f32 = 0.2;

fn window_size(glazing: &Glazing, ratio: f32, cell_w: f32, floor_m: f32) -> (f32, f32) {
    let pane = glazing.pane_m.unwrap_or([1.0, 1.0]);
    let aspect = pane[0] / pane[1];
    let area = ratio * cell_w * floor_m;
    let w = (area * aspect).sqrt().min(cell_w - PIER_M);
    let h = (area / w).min(floor_m - SILL_HEAD_M);
    let w = (area / h).min(cell_w - PIER_M);
    (w, h)
}

fn plain(face: &Face, t: [f32; 2], depth: f32, wall: &mut MeshBuilder) {
    let half = face.width / 2.0;
    wall.quad(
        face.rect([-half, half], t, depth),
        metres([-half, half], t),
        face.normal,
    );
}

fn punched(
    face: &Face,
    floor: u32,
    shell: Shell,
    glazing: &Glazing,
    ratio: f32,
    look: &FireLook,
    out: &mut FloorMeshes,
) {
    let (recess, frame_m) = (
        glazing.recess_m.unwrap_or(0.0),
        glazing.frame_m.unwrap_or(0.0),
    );
    let floor_m = shell.floor_m();
    let t0 = floor as f32 * floor_m;
    let bays = ((face.width / glazing.bay_m.unwrap_or(3.0)).floor() as usize).max(1);
    let cell_w = face.width / bays as f32;
    let (w, h) = window_size(glazing, ratio, cell_w, floor_m);
    let sill = t0 + (floor_m - h) * SILL_SHARE;
    let (y0, y1) = (sill, sill + h);
    let half = face.width / 2.0;
    plain(face, [t0, y0], 0.0, &mut out.wall);
    plain(face, [y1, t0 + floor_m], 0.0, &mut out.wall);
    let mut pier_from = -half;
    for bay in 0..bays {
        let centre = -half + (bay as f32 + 0.5) * cell_w;
        let (x0, x1) = (centre - w / 2.0, centre + w / 2.0);
        out.wall.quad(
            face.rect([pier_from, x0], [y0, y1], 0.0),
            metres([pier_from, x0], [y0, y1]),
            face.normal,
        );
        pier_from = x1;
        // The reveal: four faces from the wall plane to the pane.
        let at = |s: f32, t: f32, depth: f32| face.point(s, t, depth);
        let side_uv = |t: [f32; 2]| {
            [
                Vec2::new(0.0, t[0]),
                Vec2::new(0.0, t[1]),
                Vec2::new(recess, t[1]),
                Vec2::new(recess, t[0]),
            ]
        };
        let top_uv = |s: [f32; 2]| {
            [
                Vec2::new(s[0], 0.0),
                Vec2::new(s[1], 0.0),
                Vec2::new(s[1], recess),
                Vec2::new(s[0], recess),
            ]
        };
        out.wall.quad(
            [
                at(x0, y0, 0.0),
                at(x0, y1, 0.0),
                at(x0, y1, recess),
                at(x0, y0, recess),
            ],
            side_uv([y0, y1]),
            face.u,
        );
        out.wall.quad(
            [
                at(x1, y0, 0.0),
                at(x1, y1, 0.0),
                at(x1, y1, recess),
                at(x1, y0, recess),
            ],
            side_uv([y0, y1]),
            -face.u,
        );
        out.wall.quad(
            [
                at(x0, y0, 0.0),
                at(x1, y0, 0.0),
                at(x1, y0, recess),
                at(x0, y0, recess),
            ],
            top_uv([x0, x1]),
            Vec3::Y,
        );
        out.wall.quad(
            [
                at(x0, y1, 0.0),
                at(x1, y1, 0.0),
                at(x1, y1, recess),
                at(x0, y1, recess),
            ],
            top_uv([x0, x1]),
            Vec3::NEG_Y,
        );
        let (px0, px1, py0, py1) = (x0 + frame_m, x1 - frame_m, y0 + frame_m, y1 - frame_m);
        let ring = [
            ([x0, x1], [y0, py0]),
            ([x0, x1], [py1, y1]),
            ([x0, px0], [py0, py1]),
            ([px1, x1], [py0, py1]),
        ];
        for (s, t) in ring {
            out.frame
                .quad(face.rect(s, t, recess), metres(s, t), face.normal);
        }
        out.pane.quad(
            face.rect([px0, px1], [py0, py1], recess + PANE_OFFSET_M),
            metres([px0, px1], [py0, py1]),
            face.normal,
        );
        let (gs, gt) = (
            [x0 - GLOW_MARGIN_M, x1 + GLOW_MARGIN_M],
            [y0 - GLOW_MARGIN_M, y1 + GLOW_MARGIN_M],
        );
        // One quad per window; its vertex colour is that window's glow scale (`fire_view`).
        out.glow.quad_coloured(
            face.rect(gs, gt, look.glow_inset_m),
            metres(gs, gt),
            face.normal,
            [[1.0; 4]; 4],
        );
        let soot_t = [y1, (y1 + look.soot.height_m).min(t0 + floor_m)];
        let [r, g, b] = look.soot.colour;
        let (dark, clear) = ([r, g, b, look.soot.alpha], [r, g, b, 0.0]);
        out.soot.quad_coloured(
            face.rect([x0, x1], soot_t, -PROUD_M),
            metres([x0, x1], soot_t),
            face.normal,
            [dark, dark, clear, clear],
        );
        out.openings.push(Opening {
            at: face.point(centre, (y0 + y1) / 2.0, -FLAME_OUT_M),
            width_m: w,
        });
    }
    out.wall.quad(
        face.rect([pier_from, half], [y0, y1], 0.0),
        metres([pier_from, half], [y0, y1]),
        face.normal,
    );
}

/// The front and the four sides of a box standing `depth` out of the wall: a mullion or a rail.
fn bar(face: &Face, s: [f32; 2], t: [f32; 2], depth: f32, out: &mut MeshBuilder) {
    let at = |s: f32, t: f32, depth: f32| face.point(s, t, depth);
    out.quad(face.rect(s, t, -depth), metres(s, t), face.normal);
    for (edge, facing) in [(s[0], -face.u), (s[1], face.u)] {
        let uv = [
            Vec2::new(0.0, t[0]),
            Vec2::new(0.0, t[1]),
            Vec2::new(depth, t[1]),
            Vec2::new(depth, t[0]),
        ];
        out.quad(
            [
                at(edge, t[0], 0.0),
                at(edge, t[1], 0.0),
                at(edge, t[1], -depth),
                at(edge, t[0], -depth),
            ],
            uv,
            facing,
        );
    }
    for (edge, facing) in [(t[0], Vec3::NEG_Y), (t[1], Vec3::Y)] {
        let uv = [
            Vec2::new(s[0], 0.0),
            Vec2::new(s[1], 0.0),
            Vec2::new(s[1], depth),
            Vec2::new(s[0], depth),
        ];
        out.quad(
            [
                at(s[0], edge, 0.0),
                at(s[1], edge, 0.0),
                at(s[1], edge, -depth),
                at(s[0], edge, -depth),
            ],
            uv,
            facing,
        );
    }
}

fn curtain(
    face: &Face,
    floor: u32,
    shell: Shell,
    glazing: &Glazing,
    look: &FireLook,
    out: &mut FloorMeshes,
) {
    let floor_m = shell.floor_m();
    let (t0, t1) = (floor as f32 * floor_m, (floor + 1) as f32 * floor_m);
    let spandrel = glazing.spandrel_m.unwrap_or(0.0).min(floor_m / 2.0);
    let [mullion_w, mullion_d] = glazing.mullion_m.unwrap_or([0.0; 2]);
    let bays = ((face.width / glazing.bay_m.unwrap_or(1.5)).round() as usize).max(1);
    let half = face.width / 2.0;
    plain(face, [t0, t0 + spandrel], 0.0, &mut out.wall);
    let glass_t = [t0 + spandrel, t1];
    out.pane.quad(
        face.rect([-half, half], glass_t, PANE_OFFSET_M),
        metres([-half, half], glass_t),
        face.normal,
    );
    out.glow.quad(
        face.rect([-half, half], glass_t, look.glow_inset_m),
        metres([-half, half], glass_t),
        face.normal,
    );
    let cell_w = face.width / bays as f32;
    for j in 0..=bays {
        let s = -half + j as f32 * cell_w;
        bar(
            face,
            [s - mullion_w / 2.0, s + mullion_w / 2.0],
            [t0, t1],
            mullion_d,
            &mut out.frame,
        );
    }
    bar(
        face,
        [-half, half],
        [t1 - mullion_w / 2.0, t1 + mullion_w / 2.0],
        mullion_d,
        &mut out.frame,
    );
    for j in 0..bays {
        let centre = -half + (j as f32 + 0.5) * cell_w;
        out.openings.push(Opening {
            at: face.point(centre, (glass_t[0] + t1) / 2.0, -FLAME_OUT_M),
            width_m: cell_w,
        });
    }
}

/// Every floor's meshes: `plans[f]` says how floor `f` is glazed.
pub fn build_floors(shell: Shell, plans: &[FloorPlan], look: &BuildingLook) -> Vec<FloorMeshes> {
    let walls = faces(shell.size);
    (0..shell.floors)
        .map(|floor| {
            let plan = &plans[floor as usize];
            let mut out = FloorMeshes::default();
            for face in &walls {
                match plan.glazing.kind {
                    GlazingKind::None => plain(
                        face,
                        [
                            floor as f32 * shell.floor_m(),
                            (floor + 1) as f32 * shell.floor_m(),
                        ],
                        0.0,
                        &mut out.wall,
                    ),
                    GlazingKind::Punched => {
                        let ratio = plan
                            .window_ratio
                            .or(plan.glazing.window_ratio)
                            .unwrap_or(0.3);
                        punched(
                            face,
                            floor,
                            shell,
                            plan.glazing,
                            ratio,
                            &look.fire,
                            &mut out,
                        );
                    }
                    GlazingKind::CurtainWall => {
                        curtain(face, floor, shell, plan.glazing, &look.fire, &mut out)
                    }
                }
            }
            out
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn punched_glazing() -> Glazing {
        serde_json::from_str(
            r#"{"kind": "punched", "window_ratio": 0.3, "pane_m": [1.4, 1.6], "bay_m": 3.0, "recess_m": 0.12, "frame_m": 0.06,
                "glass": {"color": [0.1, 0.1, 0.1]}, "frame": {"color": [0.2, 0.2, 0.2]}}"#,
        )
        .expect("glazing")
    }

    fn look() -> BuildingLook {
        let text = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/building/look.json"
        ))
        .expect("shipped");
        BuildingLook::from_json(&text).expect("look")
    }

    #[test]
    fn a_window_takes_its_ratio_of_the_cell_and_fits_it() {
        let glazing = punched_glazing();

        let (w, h) = window_size(&glazing, 0.3, 3.0, 3.2);

        assert!((w * h / (3.0 * 3.2) - 0.3).abs() < 0.01, "{w} x {h}");
        assert!(w <= 3.0 - PIER_M && h <= 3.2 - SILL_HEAD_M);
    }

    #[test]
    fn a_shopfront_window_is_squeezed_into_its_cell() {
        let glazing = punched_glazing();

        let (w, h) = window_size(&glazing, 0.8, 3.0, 3.6);

        assert!(w <= 2.5 && h <= 3.1, "{w} x {h}");
    }

    #[test]
    fn every_floor_gets_its_own_openings_panes_and_glow() {
        let glazing = punched_glazing();
        let shell = Shell {
            size: Vec3::new(12.0, 9.0, 9.0),
            floors: 3,
        };
        let plans: Vec<FloorPlan> = (0..3)
            .map(|_| FloorPlan {
                glazing: &glazing,
                window_ratio: None,
            })
            .collect();

        let floors = build_floors(shell, &plans, &look());

        assert_eq!(floors.len(), 3);
        assert!(floors
            .iter()
            .all(|f| !f.pane.is_empty() && !f.glow.is_empty() && !f.soot.is_empty()));
        assert_eq!(
            floors[1].openings.len(),
            2 * 4 + 2 * 3,
            "4 bays on the east-west walls, 3 on the others"
        );
    }
}
