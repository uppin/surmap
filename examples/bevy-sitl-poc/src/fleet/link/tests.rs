//! `fleet/v1` against the shared goldens, and the pure helpers the wasm link is built from.

use super::*;
use crate::fleet::autopilot::Home;
use crate::fleet::log::{FleetLog, OnComplete, Route};

const SW_D1: &str = "nest-sw-d1";

fn fixture(name: &str) -> String {
    let path = format!("{}/../../tests/fixtures/{name}", env!("CARGO_MANIFEST_DIR"));
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

/// A golden frame as sent: the file without its trailing newline.
fn golden(name: &str) -> String {
    fixture(&format!("fleet_link/{name}")).trim_end_matches('\n').to_owned()
}

fn a_cruising_drone() -> DroneState {
    DroneState {
        position_enu: [-20.0, 12.5, 15.0],
        velocity_enu: [0.0, 6.0, 0.0],
        yaw_deg: 90.0,
        phase: Phase::Cruising,
        target: Some([-20.0, 60.0, 18.0]),
        legs_left: 1,
    }
}

fn the_shared_launch() -> FleetCommand {
    FleetCommand::Launch {
        drone: SW_D1.into(),
        route: Route { waypoints: vec![[-20.0, 0.0, 15.0], [-20.0, 60.0, 18.0]], speed_m_s: 6.0, on_complete: OnComplete::Hover },
    }
}

fn the_golden_telemetry_drones() -> Vec<DroneTelemetry> {
    vec![
        DroneTelemetry { id: SW_D1.into(), phase: "cruising".into(), enu: [-20.0, 12.5, 15.0], yaw_deg: 90.0, speed_m_s: 6.0, targets_left: 2 },
        DroneTelemetry { id: "nest-sw-d2".into(), phase: "docked".into(), enu: [-40.0, -20.0, 0.0], yaw_deg: 45.0, speed_m_s: 0.0, targets_left: 0 },
    ]
}

// ---- the goldens ----------------------------------------------------------------------------

#[test]
fn the_command_golden_decodes_into_the_shared_launch() {
    // Given the station's command golden
    let frame = golden("command.json");

    // When the page decodes it
    let message = decode_station(&frame);

    // Then it is request 7 carrying the first command of the shared fixture
    assert_eq!(message, Ok(StationMessage::Command { request: 7, command: the_shared_launch() }));
}

#[test]
fn the_command_golden_reencodes_byte_identically() {
    // Given the decoded command golden
    let message = decode_station(&golden("command.json")).expect("the golden decodes");

    // When it is written again
    let frame = serde_json::to_string(&message).expect("serialises");

    // Then it is the golden, byte for byte
    assert_eq!(frame, golden("command.json"));
}

#[test]
fn the_hello_the_page_sends_is_the_golden() {
    // Given the earthquake-fleet scene's five drones
    let drones: Vec<String> =
        ["nest-sw-d1", "nest-sw-d2", "nest-ne-d1", "nest-ne-d2", "nest-roof-d1"].map(String::from).to_vec();

    // When the page says hello at the start of the simulation
    let frame = encode_hello("quake-fleet", 0.0, &drones);

    // Then it is the hello golden
    assert_eq!(frame, golden("hello.json"));
}

#[test]
fn the_applied_answer_is_the_golden() {
    // When request 7 is applied as log entry 3 at 41.25 s
    let frame = encode_applied(7, 3, 41.25);

    // Then the answer is the applied golden
    assert_eq!(frame, golden("applied.json"));
}

#[test]
fn the_refused_answer_is_the_golden() {
    // When request 7 is refused at 41.25 s
    let frame = encode_refused(7, 41.25, "nest-sw-d1 is docked: detour needs a drone in flight");

    // Then the answer is the refused golden
    assert_eq!(frame, golden("refused.json"));
}

#[test]
fn the_telemetry_frame_is_the_golden() {
    // When two drones are reported at 41.5 s with the first one active
    let frame = encode_telemetry(41.5, Some(SW_D1), &the_golden_telemetry_drones());

    // Then the frame is the telemetry golden
    assert_eq!(frame, golden("telemetry.json"));
}

// ---- decoding errors ------------------------------------------------------------------------

#[test]
fn a_station_frame_of_an_unknown_type_is_refused_by_its_type() {
    // When the page decodes a frame whose type fleet/v1 does not have
    let message = decode_station(r#"{"type":"self_destruct","request":1}"#);

    // Then the error names the type
    assert_eq!(message, Err(LinkError::UnknownType("self_destruct".into())));
}

#[test]
fn a_command_frame_without_a_fleet_command_is_malformed() {
    // When the page decodes a command frame whose command has no drone
    let message = decode_station(r#"{"type":"command","request":1,"command":{"type":"recall"}}"#);

    // Then it is malformed, not an unknown type
    assert!(matches!(message, Err(LinkError::Malformed(_))), "{message:?}");
}

#[test]
fn a_frame_that_is_not_json_is_malformed() {
    // When the page decodes text that is not JSON
    let message = decode_station("launch nest-sw-d1");

    // Then it is malformed
    assert!(matches!(message, Err(LinkError::Malformed(_))), "{message:?}");
}

// ---- what the page reports ------------------------------------------------------------------

#[test]
fn every_phase_has_its_telemetry_word() {
    // Given every autopilot phase
    let phases = [
        Phase::Docked,
        Phase::Climbing,
        Phase::Cruising,
        Phase::Detouring,
        Phase::Hovering,
        Phase::Returning,
        Phase::Landing,
    ];

    // When each is named for telemetry
    let names = phases.map(phase_name);

    // Then the names are the station's phase words
    assert_eq!(names, ["docked", "climbing", "cruising", "detouring", "hovering", "returning", "landing"]);
}

#[test]
fn a_cruising_drone_reports_its_pose_speed_and_targets_left() {
    // Given a drone cruising north at 6 m/s toward its target, one more waypoint after it
    let state = a_cruising_drone();

    // When it is reported
    let reported = drone_telemetry(SW_D1, &state);

    // Then telemetry carries its pose, speed and the two targets still to reach
    assert_eq!(reported, the_golden_telemetry_drones()[0]);
}

#[test]
fn a_detour_refused_on_the_pad_says_the_drone_must_be_flying() {
    // Given a detour for a docked drone
    let command = FleetCommand::Detour { drone: SW_D1.into(), waypoints: vec![[0.0, 35.0, 18.0]] };

    // When the refusal is put into words
    let reason = refusal_text(&command, &RefusalReason::NotFlying(Phase::Docked));

    // Then it is the refused golden's reason
    assert_eq!(reason, "nest-sw-d1 is docked: detour needs a drone in flight");
}

#[test]
fn a_launch_refused_in_flight_says_the_drone_must_be_docked() {
    // When a launch of a cruising drone is refused
    let reason = refusal_text(&the_shared_launch(), &RefusalReason::NotDocked(Phase::Cruising));

    // Then the reason names the phase and what launch needs
    assert_eq!(reason, "nest-sw-d1 is cruising: launch needs a docked drone");
}

#[test]
fn a_command_for_an_unknown_drone_says_the_scene_has_no_such_drone() {
    // When a recall of a drone no nest houses is refused
    let command = FleetCommand::Recall { drone: "nest-zz-d9".into() };
    let reason = refusal_text(&command, &RefusalReason::UnknownDrone("nest-zz-d9".into()));

    // Then the reason names the drone
    assert_eq!(reason, "nest-zz-d9 is not a drone of this scene");
}

// ---- the page URL ---------------------------------------------------------------------------

#[test]
fn only_fleet_1_in_the_page_query_opens_the_link() {
    // Given page queries with and without the flag
    let queries = ["?fleet=1", "?scenario=quake-fleet&fleet=1", "", "?fleet=0", "?scenario=quake-fleet", "?fleets=1"];

    // When each is read
    let enabled = queries.map(fleet_enabled);

    // Then only `fleet=1` links
    assert_eq!(enabled, [true, true, false, false, false, false]);
}

#[test]
fn an_https_page_links_over_wss_to_its_own_host() {
    // When an https page served from the station asks where to link
    let url = fleet_socket_url("https:", "station.local:8770", "quake-fleet");

    // Then it is the station's fleet route, encrypted, for its scenario
    assert_eq!(url, "wss://station.local:8770/sim/fleet?scenario=quake-fleet");
}

#[test]
fn an_http_page_links_over_ws() {
    // When a plain-http page asks where to link
    let url = fleet_socket_url("http:", "127.0.0.1:8770", "quake-fleet");

    // Then it is the plain WebSocket URL
    assert_eq!(url, "ws://127.0.0.1:8770/sim/fleet?scenario=quake-fleet");
}

// ---- the station's export -------------------------------------------------------------------

#[test]
fn the_station_export_is_a_valid_fleet_log() {
    // Given the station's export of a session whose second request the page refused (seq 2)
    let export = fixture("fleet_link/session.fleet.jsonl");
    let drones = vec![
        (SW_D1.to_owned(), Home { pad_enu: [-40.0, -20.0, 0.0], yaw_deg: 45.0 }),
        ("nest-ne-d1".to_owned(), Home { pad_enu: [40.0, 100.0, 0.0], yaw_deg: 225.0 }),
    ];

    // When the renderer reads it as a `--fleet-log`
    let log = FleetLog::from_jsonl(drones, &export).expect("the export parses");

    // Then both applied commands replay, keeping the page's seqs, and none is refused
    let seqs: Vec<u64> = log.entries().iter().map(|entry| entry.seq).collect();
    assert_eq!((seqs, log.refused().len()), (vec![1, 3], 0));
}
