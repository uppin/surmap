//! The simulation's own drones, docked on the scene's nests and flown by the kinematic autopilot
//! from the fleet log. One drone at a time is "viewed": its eyes are the stereo feed and its pose
//! is what a recording writes. A scene without nests keeps the legacy `Drone` and the survey loop.

pub mod autopilot;
pub mod log;

#[cfg(test)]
mod tests;

use bevy::prelude::*;

use crate::flight::FlightPose;
use crate::wildfire::SimClock;
use crate::world::Nests;
use crate::Drone;

use autopilot::{Autopilot, Home};
use log::FleetLog;

/// A fleet drone's body, by its nest drone id.
#[derive(Component, Debug, Clone, PartialEq)]
pub struct FleetDrone {
    pub id: String,
}

/// The drone whose eyes are shown; `None` without a fleet.
#[derive(Resource, Debug, Clone, Default, PartialEq)]
pub struct ActiveDrone(pub Option<String>);

/// The scene's fleet: its log and one autopilot per drone, in nest order.
#[derive(Resource, Debug, Clone)]
pub struct Fleet {
    pub log: FleetLog,
    pub autopilots: Vec<Autopilot>,
}

impl Fleet {
    /// One autopilot per drone of `log`, each docked on its home.
    pub fn new(_log: FleetLog) -> Self {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }

    /// The drone viewed at `t_s`: the first drone, switched by each `set_active` at its `at_s`.
    pub fn active_at(&self, _t_s: f32) -> Option<&str> {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }
}

/// Every drone of every nest with its home on the nest's pad, nest by nest in scene order.
pub fn homes(_nests: &Nests) -> Vec<(String, Home)> {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}

/// What the eyes follow and a recording writes at `t_s`.
#[derive(Debug, Clone, PartialEq)]
pub struct Viewed {
    /// The active fleet drone; `None` for the legacy drone.
    pub drone_id: Option<String>,
    /// The rig pose, in Bevy coordinates.
    pub pose: FlightPose,
}

/// The viewed rig pose at `t_s`, purely from time: the active fleet drone's autopilot pose, else
/// the survey loop's.
pub fn viewed_pose(_fleet: Option<&Fleet>, _t_s: f32) -> Viewed {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}

/// After the world is built: one kinematic body (frame and four rotors) per `Nests` drone id,
/// docked on its pad and tagged `FleetDrone`; the legacy `Drone` is despawned when the scene has
/// nests. Not registered until it is implemented.
pub(crate) fn spawn_fleet(
    _commands: Commands,
    _nests: Option<Res<Nests>>,
    _legacy: Query<Entity, With<Drone>>,
    _spawned: Query<(), With<FleetDrone>>,
) {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}

/// Poses every fleet drone from its autopilot at `SimClock::now()`. Not registered until it is
/// implemented.
pub fn fly_fleet(_clock: SimClock, _fleet: Option<ResMut<Fleet>>, _drones: Query<(&FleetDrone, &mut Transform)>) {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}
