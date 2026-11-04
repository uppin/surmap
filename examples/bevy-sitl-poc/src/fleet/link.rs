//! `fleet/v1`: the JSON text frames between a page opened with `?fleet=1` and the station.
//!
//! The station sends `command` frames; the page answers each with `applied` or `refused`, opens
//! with `hello` and sends `telemetry` every `TELEMETRY_PERIOD_S`. Frames are compact JSON with the
//! `type` tag first, byte-identical to the goldens in `tests/fixtures/fleet_link/` that the
//! station's `surmap.simulation.fleet.link` shares. Pure: the wasm socket is `link_wasm`.

use serde::{Deserialize, Serialize};

use super::autopilot::{DroneState, Phase};
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
pub fn decode_station(_text: &str) -> Result<StationMessage, LinkError> {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// The page's first frame.
pub fn encode_hello(_scenario: &str, _sim_t_s: f32, _drones: &[String]) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Request `request` became log entry `seq` at simulation time `at_s`.
pub fn encode_applied(_request: u64, _seq: u64, _at_s: f32) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Request `request` was refused at `at_s`, for `reason`.
pub fn encode_refused(_request: u64, _at_s: f32, _reason: &str) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Every drone at `sim_t_s`, and the one whose eyes are shown.
pub fn encode_telemetry(_sim_t_s: f32, _active: Option<&str>, _drones: &[DroneTelemetry]) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// The word telemetry uses for `phase` (`"docked"`, `"climbing"`, …).
pub fn phase_name(_phase: Phase) -> &'static str {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Drone `id` in its autopilot `state`, as telemetry reports it.
pub fn drone_telemetry(_id: &str, _state: &DroneState) -> DroneTelemetry {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// The `refused` frame's reason for `command`, in words the station relays to the agent.
pub fn refusal_text(_command: &FleetCommand, _reason: &RefusalReason) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Whether a page URL's query (`location.search`) asks for the link: `fleet=1`.
pub fn fleet_enabled(_search: &str) -> bool {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// The link's URL on the page's own origin: `ws://` for an `http:` page, `wss://` for `https:`.
pub fn fleet_socket_url(_page_protocol: &str, _host: &str, _scenario: &str) -> String {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}
