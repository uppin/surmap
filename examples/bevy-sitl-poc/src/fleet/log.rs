//! The fleet log: simulation-time-stamped commands that task the simulation's own drones.
//!
//! One JSON object per line (`*.fleet.jsonl`), in `at_s` order, ties by `seq`. The same shape is
//! what the station sends live. A command is checked against its drone's phase at `at_s`, replayed
//! from the log so far; a command that fails is kept as a `Refusal` and never applied.

use serde::{Deserialize, Serialize};

use super::autopilot::{phase_when, Home, Phase, MAX_SPEED_M_S, MAX_UP_M, MIN_SPEED_M_S, MIN_UP_M};

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
    /// or keeps it as a refusal. The live station link (the next PR in the stack) pushes through it.
    #[allow(dead_code)]
    pub fn push(&mut self, at_s: f32, command: FleetCommand) -> Result<u64, Refusal> {
        let seq = self.entries.iter().map(|e| e.seq).chain(self.refused.iter().map(|r| r.seq)).max().map_or(1, |last| last + 1);
        self.admit(seq, at_s, command)
    }

    /// The accepted commands for drone `id`, in order.
    #[allow(dead_code)]
    pub fn for_drone(&self, id: &str) -> Vec<&Stamped> {
        self.entries.iter().filter(|e| e.command.drone() == id).collect()
    }

    /// A log read from `*.fleet.jsonl` for `drones`: each line is checked as `push` would, keeping
    /// the file's `seq`; a line earlier than the one before it is refused. A line that is not a
    /// stamped command is an error.
    pub fn from_jsonl(drones: Vec<(String, Home)>, text: &str) -> Result<Self, String> {
        let mut log = Self::new(drones);
        for (index, line) in text.lines().enumerate().filter(|(_, line)| !line.trim().is_empty()) {
            let stamped: Stamped = serde_json::from_str(line).map_err(|e| format!("fleet log line {}: {e}", index + 1))?;
            // A refused line is kept in `refused()`; the rest of the file is still read.
            let _ = log.admit(stamped.seq, stamped.at_s, stamped.command);
        }
        Ok(log)
    }

    fn admit(&mut self, seq: u64, at_s: f32, command: FleetCommand) -> Result<u64, Refusal> {
        match self.check(at_s, &command) {
            Ok(()) => {
                self.entries.push(Stamped { seq, at_s, command });
                Ok(seq)
            }
            Err(reason) => {
                let refusal = Refusal { seq, at_s, reason };
                self.refused.push(refusal.clone());
                Err(refusal)
            }
        }
    }

    /// Why `command` cannot be applied at `at_s`, if it cannot.
    fn check(&self, at_s: f32, command: &FleetCommand) -> Result<(), RefusalReason> {
        let id = command.drone();
        let Some((_, home)) = self.drones.iter().find(|(drone, _)| drone == id) else {
            return Err(RefusalReason::UnknownDrone(id.to_owned()));
        };
        if let Some(last) = self.entries.last().filter(|last| !(at_s >= last.at_s)) {
            return Err(RefusalReason::OutOfOrder { previous_at_s: last.at_s });
        }
        let phase = phase_when(*home, id, self, at_s);
        match command {
            FleetCommand::Launch { .. } if phase != Phase::Docked => Err(RefusalReason::NotDocked(phase)),
            FleetCommand::Launch { route, .. } => check_route(route),
            FleetCommand::SetRoute { .. } | FleetCommand::Detour { .. } if matches!(phase, Phase::Docked | Phase::Landing) => Err(RefusalReason::NotFlying(phase)),
            FleetCommand::SetRoute { route, .. } => check_route(route),
            FleetCommand::Detour { waypoints, .. } => check_waypoints(waypoints),
            FleetCommand::Recall { .. } if phase == Phase::Docked => Err(RefusalReason::AlreadyDocked),
            FleetCommand::Recall { .. } | FleetCommand::SetActive { .. } => Ok(()),
        }
    }
}

fn check_route(route: &Route) -> Result<(), RefusalReason> {
    check_waypoints(&route.waypoints)?;
    if (MIN_SPEED_M_S..=MAX_SPEED_M_S).contains(&route.speed_m_s) { Ok(()) } else { Err(RefusalReason::SpeedOutOfRange(route.speed_m_s)) }
}

fn check_waypoints(waypoints: &[[f32; 3]]) -> Result<(), RefusalReason> {
    if waypoints.is_empty() {
        return Err(RefusalReason::NoWaypoints);
    }
    match waypoints.iter().map(|w| w[2]).find(|up| !(MIN_UP_M..=MAX_UP_M).contains(up)) {
        Some(up) => Err(RefusalReason::HeightOutOfRange(up)),
        None => Ok(()),
    }
}
