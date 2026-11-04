//! `fleet/v1`: the JSON text frames between a page opened with `?fleet=1` and the station.
//!
//! The station sends `command` frames; the page answers each with `applied` or `refused`, opens
//! with `hello` and sends `telemetry` every `TELEMETRY_PERIOD_S`. Frames are compact JSON with the
//! `type` tag first, byte-identical to the goldens in `tests/fixtures/fleet_link/` that the
//! station's `surmap.simulation.fleet.link` shares. Pure: the wasm socket is `link_wasm`.

use serde::{Deserialize, Serialize};

use super::autopilot::{DroneState, Phase, MAX_SPEED_M_S, MAX_UP_M, MIN_SPEED_M_S, MIN_UP_M};
use super::log::{FleetCommand, RefusalReason};

#[cfg(test)]
mod tests;

pub const PROTOCOL: &str = "fleet/v1";
/// The agent server's WebSocket route.
pub const FLEET_PATH: &str = "/sim/fleet";
/// How often the page reports every drone, s.
pub const TELEMETRY_PERIOD_S: f32 = 0.5;

/// What the station sends.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum StationMessage {
    /// Apply `command` now; answer `applied` / `refused` with the same `request`.
    Command { request: u64, command: FleetCommand },
}

/// What the page sends.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum LinkMessage {
    Hello { protocol: String, scenario: String, sim_t_s: f32, drones: Vec<String> },
    Applied { request: u64, seq: u64, at_s: f32 },
    Refused { request: u64, at_s: f32, reason: String },
    Telemetry { sim_t_s: f32, active: Option<String>, drones: Vec<DroneTelemetry> },
}

/// One drone in a `telemetry` frame.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DroneTelemetry {
    pub id: String,
    /// `phase_name` of the drone's `Phase`.
    pub phase: String,
    pub enu: [f32; 3],
    pub yaw_deg: f32,
    /// Horizontal and vertical together, m/s.
    pub speed_m_s: f32,
    /// The current target (if any) plus the route waypoints after it.
    pub targets_left: usize,
}

/// A station frame the page cannot apply.
#[derive(Debug, Clone, PartialEq)]
pub enum LinkError {
    /// A `type` this protocol does not have.
    UnknownType(String),
    /// Not JSON, or a known `type` with the wrong fields.
    Malformed(String),
}

/// The message a station frame carries.
pub fn decode_station(text: &str) -> Result<StationMessage, LinkError> {
    let frame: serde_json::Value = serde_json::from_str(text).map_err(|e| LinkError::Malformed(e.to_string()))?;
    match frame.get("type").and_then(serde_json::Value::as_str) {
        Some("command") => serde_json::from_value(frame).map_err(|e| LinkError::Malformed(e.to_string())),
        Some(other) => Err(LinkError::UnknownType(other.to_owned())),
        None => Err(LinkError::Malformed("a frame has a string `type`".into())),
    }
}

fn frame(message: &LinkMessage) -> String {
    serde_json::to_string(message).expect("a link message serializes")
}

/// The page's first frame.
pub fn encode_hello(scenario: &str, sim_t_s: f32, drones: &[String]) -> String {
    frame(&LinkMessage::Hello { protocol: PROTOCOL.to_owned(), scenario: scenario.to_owned(), sim_t_s, drones: drones.to_vec() })
}

/// Request `request` became log entry `seq` at simulation time `at_s`.
pub fn encode_applied(request: u64, seq: u64, at_s: f32) -> String {
    frame(&LinkMessage::Applied { request, seq, at_s })
}

/// Request `request` was refused at `at_s`, for `reason`.
pub fn encode_refused(request: u64, at_s: f32, reason: &str) -> String {
    frame(&LinkMessage::Refused { request, at_s, reason: reason.to_owned() })
}

/// Every drone at `sim_t_s`, and the one whose eyes are shown.
pub fn encode_telemetry(sim_t_s: f32, active: Option<&str>, drones: &[DroneTelemetry]) -> String {
    frame(&LinkMessage::Telemetry { sim_t_s, active: active.map(str::to_owned), drones: drones.to_vec() })
}

/// The word telemetry uses for `phase` (`"docked"`, `"climbing"`, …).
pub fn phase_name(phase: Phase) -> &'static str {
    match phase {
        Phase::Docked => "docked",
        Phase::Climbing => "climbing",
        Phase::Cruising => "cruising",
        Phase::Detouring => "detouring",
        Phase::Hovering => "hovering",
        Phase::Returning => "returning",
        Phase::Landing => "landing",
    }
}

/// Drone `id` in its autopilot `state`, as telemetry reports it.
pub fn drone_telemetry(id: &str, state: &DroneState) -> DroneTelemetry {
    let [vx, vy, vz] = state.velocity_enu;
    DroneTelemetry {
        id: id.to_owned(),
        phase: phase_name(state.phase).to_owned(),
        enu: state.position_enu,
        yaw_deg: state.yaw_deg,
        speed_m_s: (vx * vx + vy * vy + vz * vz).sqrt(),
        targets_left: usize::from(state.target.is_some()) + state.legs_left,
    }
}

/// The command's word in a refusal (`set_route`, `detour`, …).
fn command_word(command: &FleetCommand) -> &'static str {
    match command {
        FleetCommand::Launch { .. } => "launch",
        FleetCommand::SetRoute { .. } => "set_route",
        FleetCommand::Detour { .. } => "detour",
        FleetCommand::Recall { .. } => "recall",
        FleetCommand::SetActive { .. } => "set_active",
    }
}

/// The `refused` frame's reason for `command`, in words the station relays to the agent.
pub fn refusal_text(command: &FleetCommand, reason: &RefusalReason) -> String {
    let drone = command.drone();
    let word = command_word(command);
    match reason {
        RefusalReason::UnknownDrone(id) => format!("{id} is not a drone of this scene"),
        RefusalReason::NotDocked(phase) => format!("{drone} is {}: {word} needs a docked drone", phase_name(*phase)),
        RefusalReason::NotFlying(phase) => format!("{drone} is {}: {word} needs a drone in flight", phase_name(*phase)),
        RefusalReason::AlreadyDocked => format!("{drone} is docked: {word} needs a drone that has left its pad"),
        RefusalReason::NoWaypoints => format!("{drone}: {word} needs at least one waypoint"),
        RefusalReason::SpeedOutOfRange(speed) => format!("{drone}: speed {speed} m/s is outside {MIN_SPEED_M_S}-{MAX_SPEED_M_S} m/s"),
        RefusalReason::HeightOutOfRange(up) => format!("{drone}: waypoint height {up} m is outside {MIN_UP_M}-{MAX_UP_M} m"),
        RefusalReason::OutOfOrder { previous_at_s } => format!("{drone}: the log already holds a command at {previous_at_s} s"),
    }
}

/// Whether a page URL's query (`location.search`) asks for the link: `fleet=1`.
pub fn fleet_enabled(search: &str) -> bool {
    search.trim_start_matches('?').split('&').any(|pair| pair == "fleet=1")
}

/// The link's URL on the page's own origin: `ws://` for an `http:` page, `wss://` for `https:`.
pub fn fleet_socket_url(page_protocol: &str, host: &str, scenario: &str) -> String {
    let scheme = if page_protocol == "https:" { "wss" } else { "ws" };
    format!("{scheme}://{host}{FLEET_PATH}?scenario={scenario}")
}
