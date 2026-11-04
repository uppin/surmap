//! The fleet log (numbering, refusals, files), the shared command fixture, the drones' homes on
//! their nests, the active drone, and what a recording writes for the viewed drone.

use bevy::math::{Quat, Vec3};

use super::autopilot::{state_at, Phase, STEP_S};
use super::log::{FleetCommand, OnComplete, Refusal, RefusalReason, Route, Stamped};
use super::*;
use crate::flight::SurveyLoop;
use crate::record::frame_line;
use crate::scene_manifest::{Element, SceneManifest};
use crate::wire::rig_pose_enu;
use crate::world::Nest;

const SW_D1: &str = "nest-sw-d1";
const NE_D1: &str = "nest-ne-d1";
/// The two ground nests of the fleet golden (`tests/fixtures/sim_scenario/fleet-nests.json`).
const SW: Home = Home { pad_enu: [-40.0, -20.0, 0.0], yaw_deg: 45.0 };
const NE: Home = Home { pad_enu: [40.0, 110.0, 0.0], yaw_deg: 225.0 };
/// Half the side of a nest's 2.4 m pad (`NEST_PAD_M`).
const PAD_HALF_M: f32 = 1.2;

fn fixture(name: &str) -> String {
    let path = format!("{}/../../tests/fixtures/{name}", env!("CARGO_MANIFEST_DIR"));
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

// ---- builders -------------------------------------------------------------------------------

fn two_drones() -> Vec<(String, Home)> {
    vec![(SW_D1.into(), SW), (NE_D1.into(), NE)]
}

fn route(waypoints: &[[f32; 3]]) -> Route {
    Route { waypoints: waypoints.to_vec(), speed_m_s: 5.0, on_complete: OnComplete::Return }
}

fn launch(drone: &str, route: Route) -> FleetCommand {
    FleetCommand::Launch { drone: drone.into(), route }
}

fn a_survey_launch(drone: &str) -> FleetCommand {
    launch(drone, route(&[[-20.0, 0.0, 12.0], [-20.0, 60.0, 15.0]]))
}

/// Straight up to 6 m over the pad, then home: the drone is landing a few seconds later.
fn a_hop(drone: &str) -> FleetCommand {
    launch(drone, route(&[[-40.0, -20.0, 6.0]]))
}

fn detour(drone: &str, waypoints: &[[f32; 3]]) -> FleetCommand {
    FleetCommand::Detour { drone: drone.into(), waypoints: waypoints.to_vec() }
}

fn set_active(drone: &str) -> FleetCommand {
    FleetCommand::SetActive { drone: drone.into() }
}

/// A log of `commands` for the two drones; every one must be accepted.
fn a_log(commands: Vec<(f32, FleetCommand)>) -> FleetLog {
    let mut log = FleetLog::new(two_drones());
    for (at_s, command) in commands {
        log.push(at_s, command.clone()).unwrap_or_else(|refusal| panic!("{command:?} refused: {refusal:?}"));
    }
    log
}

fn a_stamped_line(seq: u64, at_s: f32, command: FleetCommand) -> String {
    serde_json::to_string(&Stamped { seq, at_s, command }).expect("json")
}

fn nest(id: &str, pad_enu: [f32; 3], yaw_deg: f32, drones: &[&str]) -> Nest {
    Nest { id: id.into(), pad_enu, yaw_deg, drone_ids: drones.iter().map(|d| (*d).to_owned()).collect() }
}

/// The nests of a parsed manifest, as the world builds them.
fn nests_of(manifest: &SceneManifest) -> Nests {
    Nests(
        manifest
            .elements
            .iter()
            .filter_map(|e| match e {
                Element::DroneNest(n) => Some(Nest { id: n.id.clone(), pad_enu: n.position_enu, yaw_deg: n.yaw_deg, drone_ids: n.drone_ids() }),
                _ => None,
            })
            .collect(),
    )
}

// ---- drivers and matchers -------------------------------------------------------------------

/// Why the log refuses `command` at `at_s`.
fn refusal_of(log: &mut FleetLog, at_s: f32, command: FleetCommand) -> RefusalReason {
    log.push(at_s, command).expect_err("the command is refused").reason
}

/// The first step at which drone `id` is in `phase`.
fn first_moment_in(phase: Phase, home: Home, id: &str, log: &FleetLog) -> f32 {
    (0..2400).map(|i| i as f32 * STEP_S).find(|t| state_at(home, id, log, *t).phase == phase).expect("the drone reaches the phase")
}

/// Each drone with the id of the nest whose pad it docks on: within the pad, at deck height,
/// facing the nest's heading.
fn docked_on<'a>(homes: &'a [(String, Home)], nests: &'a Nests) -> Vec<(&'a str, &'a str)> {
    let on = |home: &Home, nest: &Nest| {
        let [dx, dy, dz] = [0, 1, 2].map(|i| home.pad_enu[i] - nest.pad_enu[i]);
        dx.abs() <= PAD_HALF_M && dy.abs() <= PAD_HALF_M && dz.abs() < 1e-3 && home.yaw_deg == nest.yaw_deg
    };
    homes
        .iter()
        .map(|(id, home)| (id.as_str(), nests.0.iter().find(|n| on(home, n)).map_or("no nest", |n| n.id.as_str())))
        .collect()
}

fn bevy_to_enu(position: Vec3) -> [f32; 3] {
    [position.x, -position.z, position.y]
}

fn distance(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

// ---- acceptance: refusals -------------------------------------------------------------------

#[test]
fn a_refused_command_leaves_the_flight_unchanged_and_names_the_reason() {
    let mut log = a_log(vec![(1.0, a_survey_launch(SW_D1))]);
    let before = log.clone();

    let refused = log.push(10.0, detour(SW_D1, &[[0.0, 30.0, 80.0]]));

    let expected = Refusal { seq: 2, at_s: 10.0, reason: RefusalReason::HeightOutOfRange(80.0) };
    assert_eq!((refused, log.refused()), (Err(expected.clone()), &[expected][..]));
    assert_eq!(state_at(SW, SW_D1, &log, 30.0), state_at(SW, SW_D1, &before, 30.0));
}

#[test]
fn a_command_for_a_drone_no_nest_houses_is_refused_naming_it() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, a_survey_launch("nest-x-d9"));

    assert_eq!(reason, RefusalReason::UnknownDrone("nest-x-d9".into()));
}

#[test]
fn launching_a_drone_already_in_the_air_is_refused() {
    let mut log = a_log(vec![(1.0, a_survey_launch(SW_D1))]);

    let reason = refusal_of(&mut log, 5.0, a_survey_launch(SW_D1));

    assert!(matches!(reason, RefusalReason::NotDocked(phase) if phase != Phase::Docked), "{reason:?}");
}

#[test]
fn rerouting_a_docked_drone_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, FleetCommand::SetRoute { drone: SW_D1.into(), route: route(&[[0.0, 0.0, 10.0]]) });

    assert_eq!(reason, RefusalReason::NotFlying(Phase::Docked));
}

#[test]
fn a_detour_for_a_landing_drone_is_refused() {
    let mut log = a_log(vec![(0.0, a_hop(SW_D1))]);
    let landing_at = first_moment_in(Phase::Landing, SW, SW_D1, &log) + 1.0;

    let reason = refusal_of(&mut log, landing_at, detour(SW_D1, &[[-30.0, -10.0, 10.0]]));

    assert_eq!(reason, RefusalReason::NotFlying(Phase::Landing));
}

#[test]
fn recalling_a_docked_drone_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, FleetCommand::Recall { drone: SW_D1.into() });

    assert_eq!(reason, RefusalReason::AlreadyDocked);
}

#[test]
fn a_route_without_waypoints_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, launch(SW_D1, route(&[])));

    assert_eq!(reason, RefusalReason::NoWaypoints);
}

#[test]
fn a_detour_without_waypoints_is_refused() {
    let mut log = a_log(vec![(1.0, a_survey_launch(SW_D1))]);

    let reason = refusal_of(&mut log, 20.0, detour(SW_D1, &[]));

    assert_eq!(reason, RefusalReason::NoWaypoints);
}

#[test]
fn a_route_faster_than_eight_metres_a_second_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, launch(SW_D1, Route { speed_m_s: 9.0, ..route(&[[0.0, 0.0, 10.0]]) }));

    assert_eq!(reason, RefusalReason::SpeedOutOfRange(9.0));
}

#[test]
fn a_route_slower_than_half_a_metre_a_second_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, launch(SW_D1, Route { speed_m_s: 0.2, ..route(&[[0.0, 0.0, 10.0]]) }));

    assert_eq!(reason, RefusalReason::SpeedOutOfRange(0.2));
}

#[test]
fn a_waypoint_lower_than_five_metres_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, launch(SW_D1, route(&[[0.0, 0.0, 12.0], [0.0, 20.0, 3.0]])));

    assert_eq!(reason, RefusalReason::HeightOutOfRange(3.0));
}

#[test]
fn a_waypoint_higher_than_sixty_metres_is_refused() {
    let mut log = a_log(vec![]);

    let reason = refusal_of(&mut log, 1.0, launch(SW_D1, route(&[[0.0, 0.0, 75.0]])));

    assert_eq!(reason, RefusalReason::HeightOutOfRange(75.0));
}

// ---- unit: the log --------------------------------------------------------------------------

#[test]
fn accepted_commands_are_numbered_from_one_in_the_order_they_arrive() {
    let mut log = a_log(vec![]);

    let seqs = [log.push(1.0, a_survey_launch(SW_D1)), log.push(2.0, a_survey_launch(NE_D1)), log.push(3.0, set_active(NE_D1))];

    assert_eq!(seqs, [Ok(1), Ok(2), Ok(3)]);
}

#[test]
fn a_drones_commands_are_listed_without_the_other_drones() {
    let log = a_log(vec![(1.0, a_survey_launch(SW_D1)), (2.0, a_survey_launch(NE_D1)), (9.0, detour(SW_D1, &[[-30.0, 10.0, 12.0]]))]);

    let seqs: Vec<u64> = log.for_drone(SW_D1).iter().map(|s| s.seq).collect();

    assert_eq!(seqs, vec![1, 3]);
}

#[test]
fn a_log_file_keeps_its_own_sequence_numbers() {
    let text = [a_stamped_line(7, 1.0, a_survey_launch(SW_D1)), a_stamped_line(12, 4.0, set_active(SW_D1))].join("\n");

    let log = FleetLog::from_jsonl(two_drones(), &text).expect("a valid log");

    assert_eq!(log.entries().iter().map(|s| s.seq).collect::<Vec<_>>(), vec![7, 12]);
}

#[test]
fn a_log_file_line_stamped_before_the_line_above_it_is_refused() {
    let text = [a_stamped_line(1, 5.0, a_survey_launch(SW_D1)), a_stamped_line(2, 3.0, a_survey_launch(NE_D1))].join("\n");

    let log = FleetLog::from_jsonl(two_drones(), &text).expect("a readable log");

    assert_eq!(log.refused(), &[Refusal { seq: 2, at_s: 3.0, reason: RefusalReason::OutOfOrder { previous_at_s: 5.0 } }]);
}

#[test]
fn a_log_file_line_that_is_not_a_stamped_command_is_an_error() {
    let text = format!("{}\n{{\"seq\": 2, \"at_s\": 3.0, \"command\": {{\"type\": \"barrel_roll\"}}}}", a_stamped_line(1, 1.0, a_survey_launch(SW_D1)));

    let read = FleetLog::from_jsonl(two_drones(), &text);

    assert!(read.is_err(), "{read:?}");
}

// ---- acceptance: the shared fixtures ---------------------------------------------------------

#[test]
fn every_command_in_the_shared_fixture_parses() {
    let text = fixture("fleet/commands.json");

    let commands: Vec<FleetCommand> = serde_json::from_str(&text).expect("every command parses");

    assert_eq!(
        commands,
        vec![
            launch(SW_D1, Route { waypoints: vec![[-20.0, 0.0, 15.0], [-20.0, 60.0, 18.0]], speed_m_s: 6.0, on_complete: OnComplete::Hover }),
            FleetCommand::SetRoute { drone: SW_D1.into(), route: Route { waypoints: vec![[10.0, 40.0, 20.0]], speed_m_s: 5.0, on_complete: OnComplete::Return } },
            detour(SW_D1, &[[0.0, 35.0, 18.0], [5.0, 45.0, 18.0]]),
            FleetCommand::Recall { drone: SW_D1.into() },
            set_active(NE_D1),
        ]
    );
}

#[test]
fn the_survey_sortie_replays_on_the_fleet_golden_without_a_refusal() {
    let golden = SceneManifest::from_json(&fixture("sim_scenario/fleet-nests.json")).expect("the golden parses");
    let homes = homes(&nests_of(&golden));

    let sortie = FleetLog::from_jsonl(homes, &fixture("fleet/survey-sortie.fleet.jsonl")).expect("the sortie parses");

    assert_eq!((sortie.entries().len(), sortie.refused()), (7, &[][..]));
}

// ---- unit: homes and the active drone -------------------------------------------------------

#[test]
fn every_drone_of_a_nest_docks_on_that_nests_pad_facing_its_heading() {
    let nests = Nests(vec![
        nest("nest-sw", [-40.0, -20.0, 0.0], 45.0, &["nest-sw-d1", "nest-sw-d2"]),
        nest("nest-roof", [78.55, 22.0, 16.5], 90.0, &["nest-roof-d1"]),
    ]);

    let homes = homes(&nests);

    assert_eq!(docked_on(&homes, &nests), vec![("nest-sw-d1", "nest-sw"), ("nest-sw-d2", "nest-sw"), ("nest-roof-d1", "nest-roof")]);
}

#[test]
fn the_first_drone_is_viewed_until_another_is_made_active() {
    let fleet = Fleet::new(a_log(vec![(1.0, a_survey_launch(SW_D1)), (2.0, a_survey_launch(NE_D1)), (12.0, set_active(NE_D1)), (40.0, set_active(SW_D1))]));

    let viewed = [fleet.active_at(5.0), fleet.active_at(12.5), fleet.active_at(45.0)];

    assert_eq!(viewed, [Some(SW_D1), Some(NE_D1), Some(SW_D1)]);
}

// ---- acceptance: what a recording writes ----------------------------------------------------

#[test]
fn after_set_active_recorded_frames_carry_the_new_drones_id_and_pose() {
    let fleet = Fleet::new(a_log(vec![(1.0, a_survey_launch(SW_D1)), (2.0, launch(NE_D1, route(&[[30.0, 90.0, 15.0], [20.0, 40.0, 20.0]]))), (12.0, set_active(NE_D1))]));

    let viewed = viewed_pose(Some(&fleet), 20.0);
    let line: serde_json::Value = serde_json::from_str(&frame_line(
        200,
        20_000_000_000,
        "frames/left/20000000000.png",
        "frames/right/20000000000.png",
        None,
        rig_pose_enu(viewed.pose.position, Quat::from_rotation_y(viewed.pose.yaw_rad)),
        viewed.drone_id.as_deref(),
    ))
    .expect("json");

    let recorded_at = [0, 1, 2].map(|i| line["pose_enu"][i].as_f64().expect("pose") as f32);
    let ne_at = state_at(NE, NE_D1, &fleet.log, 20.0).position_enu;
    assert_eq!(line["drone_id"], NE_D1);
    assert!(distance(recorded_at, ne_at) < 1.0 && distance(bevy_to_enu(viewed.pose.position), ne_at) < 1.0, "recorded {recorded_at:?}, drone at {ne_at:?}");
}

#[test]
fn a_scene_without_nests_records_the_survey_loop_as_before() {
    let t_s = 37.5;

    let viewed = viewed_pose(None, t_s);

    assert_eq!(viewed, Viewed { drone_id: None, pose: SurveyLoop::disaster_block().pose_at(t_s) });
}
