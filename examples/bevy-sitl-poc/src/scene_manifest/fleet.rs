//! Drone nests (`drone_nest` elements): docking pads the agent places, each housing one to four of
//! the simulation's own drones, and the rules that keep a pad where a drone could use it
//! (docs/simulation/bevy-simulation.md § *Drone nests*). The station applies the same rules, with
//! the same messages (`surmap.simulation.fleet_nests`).
//!
//! The pad is a `NEST_PAD_M` square, yawed about its centre. It may not overlap a building, a
//! collapsed building or a box with a collider unless it stands on that element's top (a rooftop
//! nest), nor a `water: true` surface; nest centres keep `NEST_SPACING_M` apart, and the drone ids
//! `<id>-d1 … <id>-dN` join the manifest's one id namespace.

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
        // TODO(pr-1): implement
        todo!("pr-1: implement")
    }
}

impl SceneManifest {
    /// Every nest: an id of ASCII letters, digits and `-`; a pad inside the bounds, off every
    /// solid footprint below its top and off the water; `1..=MAX_DRONES_PER_NEST` drones; centres
    /// `NEST_SPACING_M` apart; at most `MAX_NESTS`; drone ids unique in the manifest.
    pub(super) fn validate_nests(&self) -> Result<(), ManifestError> {
        if !self.elements.iter().any(|e| matches!(e, Element::DroneNest(_))) {
            // A scene without nests has nothing to check.
            return Ok(());
        }
        // TODO(pr-1): implement
        todo!("pr-1: implement")
    }
}
