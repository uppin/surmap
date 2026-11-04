//! The kinematic autopilot: where a fleet drone is at a simulation moment, replayed from its home
//! pad and the fleet log at a fixed step, so the answer never depends on the frame rate.
//!
//! No physics, wind, battery or obstacle avoidance: the route is flown as given, within the
//! limits below. It moves the simulation's own drones only; SurMap has no flight control.

use std::collections::VecDeque;

use super::log::{FleetLog, OnComplete};

/// The fixed integration step, from `t = 0`. A command takes effect at the first step at or after
/// its `at_s`.
pub const STEP_S: f32 = 0.05;
/// Route speed bounds (a route outside them is refused) and the horizontal speed limit.
pub const MAX_SPEED_M_S: f32 = 8.0;
pub const MIN_SPEED_M_S: f32 = 0.5;
/// Horizontal acceleration limit.
pub const MAX_ACCEL_M_S2: f32 = 2.5;
/// Vertical speed limit while climbing or cruising.
pub const MAX_CLIMB_M_S: f32 = 2.0;
/// Vertical speed limit while landing.
pub const MAX_DESCENT_M_S: f32 = 1.0;
/// Heading turn-rate limit.
pub const MAX_YAW_RATE_DEG_S: f32 = 60.0;
/// A target this close is reached and the next becomes current.
pub const REACH_M: f32 = 1.0;
/// Waypoint `up` bounds (ENU metres); a waypoint outside them is refused. A drone also climbs at
/// least `MIN_UP_M` above its own pad before it cruises.
pub const MIN_UP_M: f32 = 5.0;
pub const MAX_UP_M: f32 = 60.0;

/// A drone's pad: the deck centre in ENU and the heading it docks facing (degrees, ENU
/// counter-clockwise from east).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Home {
    pub pad_enu: [f32; 3],
    pub yaw_deg: f32,
}

/// What a drone is doing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Docked,
    Climbing,
    Cruising,
    Detouring,
    Hovering,
    Returning,
    Landing,
}

/// A drone's kinematic state at one step.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DroneState {
    pub position_enu: [f32; 3],
    pub velocity_enu: [f32; 3],
    /// Heading in degrees, ENU counter-clockwise from east (as `Home::yaw_deg`).
    pub yaw_deg: f32,
    pub phase: Phase,
    /// The point being flown to, if any.
    pub target: Option<[f32; 3]>,
    /// Route waypoints still to reach after `target`.
    pub legs_left: usize,
}

/// What a drone has been told to fly, as the log's commands leave it.
#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    pub home: Home,
    /// The route's remaining waypoints, the current one first.
    pub route: VecDeque<[f32; 3]>,
    /// Detour waypoints still to visit before the route resumes.
    pub detour: VecDeque<[f32; 3]>,
    pub speed_m_s: f32,
    pub on_complete: OnComplete,
}

/// Advances `state` by `dt` toward what `plan` says, within the limits; pops each target it
/// reaches.
pub fn step(_state: &mut DroneState, _plan: &mut Plan, _dt: f32) {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}

/// The state of drone `id`, docked on `home` at `t = 0`, after replaying `log` to `t_s`.
pub fn state_at(_home: Home, _id: &str, _log: &FleetLog, _t_s: f32) -> DroneState {
    // TODO(pr-2): implement
    todo!("pr-2: implement")
}

/// The live app's autopilot for one drone: it advances from where it last was instead of
/// replaying from `t = 0`, and equals `state_at` at every moment.
#[derive(Debug, Clone, PartialEq)]
pub struct Autopilot {
    id: String,
    state: DroneState,
    plan: Plan,
    t_s: f32,
    applied: usize,
}

impl Autopilot {
    /// Drone `id`, docked on `home` at `t = 0`.
    pub fn new(_id: &str, _home: Home) -> Self {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }

    /// The drone's id.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// Advances to `t_s` (not earlier than the last call), applying `log`'s new entries.
    pub fn advance(&mut self, _log: &FleetLog, _t_s: f32) -> DroneState {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }
}

#[cfg(test)]
mod tests;
