//! Drone nests (`drone_nest` elements): docking pads the agent places, each housing one to four of
//! the simulation's own drones, and the rules that keep a pad where a drone could use it
//! (docs/simulation/bevy-simulation.md § *Drone nests*). The station applies the same rules, with
//! the same messages (`surmap.simulation.fleet_nests`).
//!
//! The pad is a `NEST_PAD_M` square, yawed about its centre. It may not overlap a building, a
//! collapsed building or a box with a collider unless it stands on that element's top (a rooftop
//! nest), nor a `water: true` surface; nest centres keep `NEST_SPACING_M` apart, and the drone ids
//! `<id>-d1 … <id>-dN` join the manifest's one id namespace.

use bevy::math::Vec2;
use serde::Deserialize;

use super::{Element, ManifestError, SceneManifest};

/// The pad's side, m.
pub const NEST_PAD_M: f32 = 2.4;
/// The least distance between two nest centres, m.
pub const NEST_SPACING_M: f32 = 6.0;
/// The most nests a scene holds.
pub const MAX_NESTS: usize = 8;
/// The most drones one nest houses.
pub const MAX_DRONES_PER_NEST: u32 = 4;
/// A pad centre lies within ±`NEST_BOUND_M` east and north of the origin.
pub const NEST_BOUND_M: f32 = 500.0;
/// A pad's deck is at most `NEST_MAX_UP_M` above the ground (and never below it).
pub const NEST_MAX_UP_M: f32 = 60.0;

/// A docking pad: `position_enu` is the pad's centre at deck level, `yaw_deg` its heading (docked
/// drones face it), `drones` how many it houses.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct DroneNest {
    pub id: String,
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    #[serde(default = "one_drone")]
    pub drones: u32,
}

fn one_drone() -> u32 {
    1
}

impl DroneNest {
    /// The nest's drone ids, `<id>-d1` … `<id>-dN`, in order.
    pub fn drone_ids(&self) -> Vec<String> {
        (1..=self.drones).map(|n| format!("{}-d{n}", self.id)).collect()
    }

    fn pad(&self) -> Footprint {
        let [x, y, _] = self.position_enu;
        Footprint { centre: Vec2::new(x, y), half: Vec2::splat(NEST_PAD_M / 2.0), yaw_rad: self.yaw_deg.to_radians() }
    }
}

/// A yawed rectangle on the ground plane: its centre, half-extents (east, north before yaw) and yaw.
struct Footprint {
    centre: Vec2,
    half: Vec2,
    yaw_rad: f32,
}

/// Overlaps shallower than this are touching, not overlapping, m.
const TOUCH_M: f32 = 1e-4;
/// A pad standing this close to an element's top (below it) still counts as standing on it, m.
const ROOF_TOLERANCE_M: f32 = 0.05;

impl Footprint {
    fn axes(&self) -> [Vec2; 2] {
        let (sin, cos) = self.yaw_rad.sin_cos();
        [Vec2::new(cos, sin), Vec2::new(-sin, cos)]
    }

    /// The footprint's half-width along `axis`.
    fn reach(&self, axis: Vec2) -> f32 {
        let [east, north] = self.axes();
        self.half.x * axis.dot(east).abs() + self.half.y * axis.dot(north).abs()
    }

    /// Separating-axis test: the two rectangles share area deeper than `TOUCH_M`.
    fn overlaps(&self, other: &Self) -> bool {
        let gap = other.centre - self.centre;
        self.axes()
            .into_iter()
            .chain(other.axes())
            .all(|axis| gap.dot(axis).abs() < self.reach(axis) + other.reach(axis) - TOUCH_M)
    }
}

/// A solid thing a pad may not stand inside: its id, footprint and top (m above the ground).
struct Solid<'a> {
    id: &'a str,
    footprint: Footprint,
    top_m: f32,
}

fn solids(elements: &[Element]) -> Vec<Solid<'_>> {
    elements
        .iter()
        .filter_map(|element| match element {
            Element::Building(b) => Some(Solid {
                id: &b.id,
                footprint: Footprint { centre: Vec2::new(b.position_enu[0], b.position_enu[1]), half: Vec2::new(b.size_m[0], b.size_m[1]) / 2.0, yaw_rad: b.yaw_deg.to_radians() },
                top_m: b.position_enu[2] + b.size_m[2],
            }),
            Element::CollapsedBuilding(c) => Some(Solid {
                id: &c.id,
                footprint: Footprint { centre: Vec2::new(c.position_enu[0], c.position_enu[1]), half: Vec2::from_array(c.footprint_m) / 2.0, yaw_rad: c.yaw_deg.to_radians() },
                top_m: c.position_enu[2] + c.slabs as f32 * c.slab_thickness_m,
            }),
            Element::Box(b) if b.collider && !b.water => Some(Solid {
                id: &b.id,
                footprint: Footprint { centre: Vec2::new(b.position_enu[0], b.position_enu[1]), half: Vec2::new(b.size_m[0], b.size_m[1]) / 2.0, yaw_rad: b.yaw_deg.to_radians() },
                top_m: b.position_enu[2] + b.size_m[2],
            }),
            _ => None,
        })
        .collect()
}

fn invalid(nest: &DroneNest, reason: String) -> ManifestError {
    ManifestError::Invalid(format!("nest {}: {reason}", nest.id))
}

impl SceneManifest {
    /// Every nest: an id of ASCII letters, digits and `-`; a pad inside the bounds, off every
    /// solid footprint below its top and off the water; `1..=MAX_DRONES_PER_NEST` drones; centres
    /// `NEST_SPACING_M` apart; at most `MAX_NESTS`; drone ids unique in the manifest.
    pub(super) fn validate_nests(&self) -> Result<(), ManifestError> {
        let nests: Vec<&DroneNest> = self
            .elements
            .iter()
            .filter_map(|e| match e {
                Element::DroneNest(nest) => Some(nest),
                _ => None,
            })
            .collect();
        if nests.is_empty() {
            // A scene without nests has nothing to check.
            return Ok(());
        }
        if nests.len() > MAX_NESTS {
            return Err(ManifestError::Invalid(format!("a scenario holds at most {MAX_NESTS} nests, got {}", nests.len())));
        }
        let solids = solids(&self.elements);
        let waters: Vec<(&str, Footprint)> = self
            .elements
            .iter()
            .filter_map(|e| match e {
                Element::Box(b) if b.water => Some((
                    b.id.as_str(),
                    Footprint { centre: Vec2::new(b.position_enu[0], b.position_enu[1]), half: Vec2::new(b.size_m[0], b.size_m[1]) / 2.0, yaw_rad: b.yaw_deg.to_radians() },
                )),
                _ => None,
            })
            .collect();
        for (i, nest) in nests.iter().enumerate() {
            validate_nest(nest, &solids, &waters)?;
            let [x, y, _] = nest.position_enu;
            for earlier in &nests[..i] {
                let distance = Vec2::new(x, y).distance(Vec2::new(earlier.position_enu[0], earlier.position_enu[1]));
                if distance < NEST_SPACING_M {
                    return Err(invalid(nest, format!("{distance:.1} m from nest {}, nests keep {NEST_SPACING_M} m apart", earlier.id)));
                }
            }
        }
        let mut taken: std::collections::BTreeSet<&str> = self
            .models
            .iter()
            .map(|m| m.id.as_str())
            .chain(self.elements.iter().map(Element::id))
            .chain(self.fires.iter().map(|f| f.id.as_str()))
            .chain(self.building_fires.iter().map(|f| f.id.as_str()))
            .collect();
        let drone_ids: Vec<String> = nests.iter().flat_map(|nest| nest.drone_ids()).collect();
        for id in &drone_ids {
            if !taken.insert(id) {
                return Err(ManifestError::DuplicateId(id.clone()));
            }
        }
        Ok(())
    }
}

/// One nest's own rules: its id and drone count, its place, and what is under its pad.
fn validate_nest(nest: &DroneNest, solids: &[Solid], waters: &[(&str, Footprint)]) -> Result<(), ManifestError> {
    if nest.id.is_empty() || !nest.id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return Err(invalid(nest, "id must be ASCII letters, digits and '-'".into()));
    }
    if !(1..=MAX_DRONES_PER_NEST).contains(&nest.drones) {
        return Err(invalid(nest, format!("drones must be 1 to {MAX_DRONES_PER_NEST}, got {}", nest.drones)));
    }
    let [x, y, up] = nest.position_enu;
    if x.abs() > NEST_BOUND_M || y.abs() > NEST_BOUND_M {
        return Err(invalid(nest, format!("pad centre ({x}, {y}) is outside ±{NEST_BOUND_M} m east and north")));
    }
    if !(0.0..=NEST_MAX_UP_M).contains(&up) {
        return Err(invalid(nest, format!("pad deck at {up} m must be between 0 and {NEST_MAX_UP_M} m up")));
    }
    let pad = nest.pad();
    if let Some((id, _)) = waters.iter().find(|(_, water)| pad.overlaps(water)) {
        return Err(invalid(nest, format!("pad overlaps water ({id})")));
    }
    if let Some(solid) = solids.iter().find(|s| up < s.top_m - ROOF_TOLERANCE_M && pad.overlaps(&s.footprint)) {
        return Err(invalid(nest, format!("pad overlaps {}, which rises to {} m; a rooftop nest stands on its top", solid.id, solid.top_m)));
    }
    Ok(())
}
