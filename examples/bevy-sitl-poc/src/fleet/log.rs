//! The fleet log: simulation-time-stamped commands that task the simulation's own drones.
//!
//! One JSON object per line (`*.fleet.jsonl`), in `at_s` order, ties by `seq`. The same shape is
//! what the station sends live. A command is checked against its drone's phase at `at_s`, replayed
//! from the log so far; a command that fails is kept as a `Refusal` and never applied.

use serde::{Deserialize, Serialize};

use super::autopilot::{Home, Phase};

/// The speed a route flies at when it names none.
pub const DEFAULT_SPEED_M_S: f32 = 5.0;

fn default_speed() -> f32 {
    DEFAULT_SPEED_M_S
}

/// One command to one drone. `drone` is a nest drone id (`<nest id>-d<n>`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum FleetCommand {
    /// Take off from the pad and fly `route`.
    Launch { drone: String, route: Route },
    /// Replace the remaining targets, from where the drone is.
    SetRoute { drone: String, route: Route },
    /// Visit `waypoints`, then resume the target that was current.
    Detour { drone: String, waypoints: Vec<[f32; 3]> },
    /// Fly back above the pad, land and dock.
    Recall { drone: String },
    /// Show this drone's eyes, and record its pose, from `at_s` on.
    SetActive { drone: String },
}

impl FleetCommand {
    /// The drone the command is for.
    pub fn drone(&self) -> &str {
        match self {
            Self::Launch { drone, .. }
            | Self::SetRoute { drone, .. }
            | Self::Detour { drone, .. }
            | Self::Recall { drone }
            | Self::SetActive { drone } => drone,
        }
    }
}

/// Waypoints in ENU metres, flown in order at `speed_m_s`, then `on_complete`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Route {
    pub waypoints: Vec<[f32; 3]>,
    #[serde(default = "default_speed")]
    pub speed_m_s: f32,
    #[serde(default)]
    pub on_complete: OnComplete,
}

/// What a drone does after its last waypoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OnComplete {
    /// Fly back above the pad, land and dock.
    #[default]
    Return,
    /// Hold position over the last waypoint.
    Hover,
}

/// An accepted command, numbered and stamped with the simulation time it takes effect.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Stamped {
    pub seq: u64,
    pub at_s: f32,
    pub command: FleetCommand,
}

/// A command the log would not apply, and why.
#[derive(Debug, Clone, PartialEq)]
pub struct Refusal {
    pub seq: u64,
    pub at_s: f32,
    pub reason: RefusalReason,
}

/// Why a command was refused.
#[derive(Debug, Clone, PartialEq)]
pub enum RefusalReason {
    /// No nest houses a drone of this id.
    UnknownDrone(String),
    /// `launch` while the drone is not `Docked`.
    NotDocked(Phase),
    /// `set_route` / `detour` while the drone is `Docked` or `Landing`.
    NotFlying(Phase),
    /// `recall` while the drone is `Docked`.
    AlreadyDocked,
    /// A route or detour with no waypoints.
    NoWaypoints,
    /// A route speed outside `MIN_SPEED_M_S..=MAX_SPEED_M_S`.
    SpeedOutOfRange(f32),
    /// A waypoint whose `up` is outside `MIN_UP_M..=MAX_UP_M`.
    HeightOutOfRange(f32),
    /// A log line stamped earlier than the line before it.
    OutOfOrder { previous_at_s: f32 },
}

/// The drones a log may task (each with its home pad), the commands it accepted and the ones it
/// refused.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct FleetLog {
    drones: Vec<(String, Home)>,
    entries: Vec<Stamped>,
    refused: Vec<Refusal>,
}

impl FleetLog {
    /// An empty log for `drones`, in the order the fleet lists them.
    pub fn new(drones: Vec<(String, Home)>) -> Self {
        Self { drones, entries: Vec::new(), refused: Vec::new() }
    }

    /// The drones this log may task, with their home pads.
    pub fn drones(&self) -> &[(String, Home)] {
        &self.drones
    }

    /// The accepted commands, in `at_s` order (ties by `seq`).
    pub fn entries(&self) -> &[Stamped] {
        &self.entries
    }

    /// The refused commands, in the order they arrived.
    pub fn refused(&self) -> &[Refusal] {
        &self.refused
    }

    /// Checks `command` against its drone's phase at `at_s` and appends it with the next `seq`,
    /// or keeps it as a refusal.
    pub fn push(&mut self, _at_s: f32, _command: FleetCommand) -> Result<u64, Refusal> {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }

    /// The accepted commands for drone `id`, in order.
    pub fn for_drone(&self, _id: &str) -> Vec<&Stamped> {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }

    /// A log read from `*.fleet.jsonl` for `drones`: each line is checked as `push` would, keeping
    /// the file's `seq`; a line earlier than the one before it is refused. A line that is not a
    /// stamped command is an error.
    pub fn from_jsonl(_drones: Vec<(String, Home)>, _text: &str) -> Result<Self, String> {
        // TODO(pr-2): implement
        todo!("pr-2: implement")
    }
}
