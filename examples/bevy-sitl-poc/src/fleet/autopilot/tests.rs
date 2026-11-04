//! The autopilot as pure functions sampled over time: take-off, legs, detours, re-routing,
//! recall and landing, the limits, two drones at once, and the live autopilot equal to the replay.

use std::collections::VecDeque;

use super::*;
use crate::fleet::log::{FleetCommand, Route};

const SW_D1: &str = "nest-sw-d1";
const NE_D1: &str = "nest-ne-d1";
/// The two ground nests of the fleet golden (`tests/fixtures/sim_scenario/fleet-nests.json`).
const SW: Home = Home { pad_enu: [-40.0, -20.0, 0.0], yaw_deg: 45.0 };
const NE: Home = Home { pad_enu: [40.0, 110.0, 0.0], yaw_deg: 225.0 };
/// The golden's roof nest, on `building-6`'s 16.5 m roof.
const ROOF: Home = Home { pad_enu: [78.55, 22.0, 16.5], yaw_deg: 90.0 };
const ROOF_D1: &str = "nest-roof-d1";

/// Slack for float rounding when a limit is compared per step.
const EPS: f32 = 1e-3;

// ---- builders -------------------------------------------------------------------------------

fn the_fleet() -> Vec<(String, Home)> {
    vec![(SW_D1.into(), SW), (NE_D1.into(), NE), (ROOF_D1.into(), ROOF)]
}

/// A five-metres-a-second route over `waypoints` that ends by flying home.
fn route(waypoints: &[[f32; 3]]) -> Route {
    Route { waypoints: waypoints.to_vec(), speed_m_s: 5.0, on_complete: OnComplete::Return }
}

/// As `route`, ending in a hover over the last waypoint.
fn route_ending_in_hover(waypoints: &[[f32; 3]]) -> Route {
    Route { on_complete: OnComplete::Hover, ..route(waypoints) }
}

fn launch(drone: &str, route: Route) -> FleetCommand {
    FleetCommand::Launch { drone: drone.into(), route }
}

fn set_route(drone: &str, route: Route) -> FleetCommand {
    FleetCommand::SetRoute { drone: drone.into(), route }
}

fn detour(drone: &str, waypoints: &[[f32; 3]]) -> FleetCommand {
    FleetCommand::Detour { drone: drone.into(), waypoints: waypoints.to_vec() }
}

fn recall(drone: &str) -> FleetCommand {
    FleetCommand::Recall { drone: drone.into() }
}

/// A log of `commands` for the fleet; every one must be accepted.
fn a_log(commands: Vec<(f32, FleetCommand)>) -> FleetLog {
    let mut log = FleetLog::new(the_fleet());
    for (at_s, command) in commands {
        log.push(at_s, command.clone()).unwrap_or_else(|refusal| panic!("{command:?} refused: {refusal:?}"));
    }
    log
}

/// `tests/fixtures/fleet/survey-sortie.fleet.jsonl`, for the golden's two ground drones.
fn the_survey_sortie() -> FleetLog {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/fleet/survey-sortie.fleet.jsonl");
    let text = std::fs::read_to_string(path).expect("the sortie fixture");
    FleetLog::from_jsonl(vec![(SW_D1.into(), SW), (NE_D1.into(), NE)], &text).expect("the sortie parses")
}

fn cruising_at(position_enu: [f32; 3], velocity_enu: [f32; 3]) -> DroneState {
    DroneState { position_enu, velocity_enu, yaw_deg: 0.0, phase: Phase::Cruising, target: None, legs_left: 0 }
}

fn in_phase(phase: Phase, position_enu: [f32; 3], velocity_enu: [f32; 3]) -> DroneState {
    DroneState { phase, ..cruising_at(position_enu, velocity_enu) }
}

fn a_plan(home: Home, route: &[[f32; 3]]) -> Plan {
    Plan { home, route: route.iter().copied().collect(), detour: VecDeque::new(), speed_m_s: 8.0, on_complete: OnComplete::Hover }
}

// ---- drivers --------------------------------------------------------------------------------

/// The drone's state at every step from 0 to `until_s`, as the live autopilot flies it.
fn flight(home: Home, id: &str, log: &FleetLog, until_s: f32) -> Vec<DroneState> {
    let mut autopilot = Autopilot::new(id, home);
    (0..=(until_s / STEP_S).round() as usize).map(|i| autopilot.advance(log, i as f32 * STEP_S)).collect()
}

/// The states `step` gives over `seconds` from `state` under `plan`.
fn stepped(mut state: DroneState, mut plan: Plan, seconds: f32) -> Vec<DroneState> {
    (0..(seconds / STEP_S).round() as usize)
        .map(|_| {
            step(&mut state, &mut plan, STEP_S);
            state
        })
        .collect()
}

/// Irregular frame times up to about 40 s, as a live app's frames would fall.
fn frame_times() -> Vec<f32> {
    (0..200)
        .scan(0.0_f32, |t, i| {
            *t += 0.013 + (i % 7) as f32 * 0.061;
            Some(*t)
        })
        .collect()
}

// ---- matchers -------------------------------------------------------------------------------

fn distance(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

fn horizontal(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt()
}

fn speed(state: &DroneState) -> f32 {
    horizontal(state.velocity_enu, [0.0; 3])
}

fn wrapped_deg(angle: f32) -> f32 {
    (angle + 180.0).rem_euclid(360.0) - 180.0
}

/// `waypoints` in the order the flight first comes within `REACH_M` of each; unreached ones are
/// left out.
fn reached_in_order(flight: &[DroneState], waypoints: &[[f32; 3]]) -> Vec<[f32; 3]> {
    let mut reached: Vec<(usize, [f32; 3])> = waypoints
        .iter()
        .filter_map(|w| flight.iter().position(|s| distance(s.position_enu, *w) <= REACH_M).map(|i| (i, *w)))
        .collect();
    reached.sort_by_key(|(i, _)| *i);
    reached.into_iter().map(|(_, w)| w).collect()
}

/// How high the drone was when it first moved off its pad's column.
fn height_leaving_the_pad(flight: &[DroneState], home: Home) -> f32 {
    flight.iter().find(|s| horizontal(s.position_enu, home.pad_enu) > 0.1).expect("the drone leaves its pad").position_enu[2]
}

/// The largest distance moved in one step.
fn biggest_step_m(flight: &[DroneState]) -> f32 {
    flight.windows(2).map(|w| distance(w[0].position_enu, w[1].position_enu)).fold(0.0, f32::max)
}

/// The fastest the flight went, sped up, climbed or sank, and turned, per step.
#[derive(Debug)]
struct Extremes {
    speed_m_s: f32,
    speed_change_m_s2: f32,
    vertical_m_s: f32,
    turn_deg_s: f32,
}

impl Extremes {
    fn of(flight: &[DroneState]) -> Self {
        let per_step = |f: &dyn Fn(&DroneState, &DroneState) -> f32| flight.windows(2).map(|w| f(&w[0], &w[1])).fold(0.0, f32::max);
        Self {
            speed_m_s: per_step(&|a, b| horizontal(a.position_enu, b.position_enu) / STEP_S),
            speed_change_m_s2: per_step(&|a, b| (speed(b) - speed(a)).abs() / STEP_S),
            vertical_m_s: per_step(&|a, b| (b.position_enu[2] - a.position_enu[2]).abs() / STEP_S),
            turn_deg_s: per_step(&|a, b| wrapped_deg(b.yaw_deg - a.yaw_deg).abs() / STEP_S),
        }
    }

    fn within_the_limits(&self) -> bool {
        self.speed_m_s <= MAX_SPEED_M_S + EPS
            && self.speed_change_m_s2 <= MAX_ACCEL_M_S2 + EPS
            && self.vertical_m_s <= MAX_CLIMB_M_S + EPS
            && self.turn_deg_s <= MAX_YAW_RATE_DEG_S + EPS
    }
}

fn is_docked_on(state: &DroneState, home: Home) -> bool {
    state.phase == Phase::Docked && distance(state.position_enu, home.pad_enu) < 0.05
}

// ---- acceptance -----------------------------------------------------------------------------

#[test]
fn a_launched_drone_climbs_off_its_pad_then_reaches_each_waypoint_in_order() {
    let (first, second) = ([-20.0, 0.0, 12.0], [0.0, 20.0, 15.0]);
    let log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[first, second])))]);

    let flight = flight(SW, SW_D1, &log, 60.0);

    assert!(height_leaving_the_pad(&flight, SW) >= first[2] - REACH_M, "left the pad below its first waypoint");
    assert_eq!(reached_in_order(&flight, &[second, first]), vec![first, second]);
}

#[test]
fn no_drone_ever_exceeds_the_speed_climb_or_turn_limits() {
    let sortie = the_survey_sortie();

    let extremes = [Extremes::of(&flight(SW, SW_D1, &sortie, 200.0)), Extremes::of(&flight(NE, NE_D1, &sortie, 200.0))];

    assert!(extremes.iter().all(Extremes::within_the_limits), "{extremes:?}");
}

#[test]
fn a_new_route_mid_flight_turns_from_where_the_drone_is_without_a_jump() {
    let (abandoned, new) = ([20.0, 0.0, 12.0], [-40.0, 40.0, 12.0]);
    let log = a_log(vec![
        (1.0, launch(SW_D1, route_ending_in_hover(&[[-20.0, 0.0, 12.0], abandoned]))),
        (15.0, set_route(SW_D1, route_ending_in_hover(&[new]))),
    ]);

    let flight = flight(SW, SW_D1, &log, 45.0);

    assert!(biggest_step_m(&flight) <= MAX_SPEED_M_S * STEP_S + EPS, "jumped {} m in one step", biggest_step_m(&flight));
    assert_eq!(reached_in_order(&flight, &[abandoned, new]), vec![new]);
}

#[test]
fn a_detour_visits_its_waypoints_then_resumes_the_waypoint_that_was_next() {
    let (a, b, c) = ([-20.0, 0.0, 12.0], [-20.0, 100.0, 12.0], [0.0, 120.0, 12.0]);
    let (d1, d2) = ([-35.0, 30.0, 15.0], [-35.0, 50.0, 15.0]);
    let log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[a, b, c]))), (22.0, detour(SW_D1, &[d1, d2]))]);

    let flight = flight(SW, SW_D1, &log, 120.0);

    assert_eq!(reached_in_order(&flight, &[a, b, c, d1, d2]), vec![a, d1, d2, b, c]);
}

#[test]
fn a_recalled_drone_lands_back_on_its_own_pad_and_docks() {
    let log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[[-20.0, 0.0, 12.0], [-20.0, 100.0, 12.0]]))), (20.0, recall(SW_D1))]);

    let after_landing = state_at(SW, SW_D1, &log, 120.0);

    assert!(is_docked_on(&after_landing, SW), "{after_landing:?}");
}

#[test]
fn two_drones_fly_at_once_without_changing_each_others_path() {
    let sw_launch = (1.0, launch(SW_D1, route(&[[-20.0, 0.0, 12.0], [-20.0, 60.0, 15.0]])));
    let alone = a_log(vec![sw_launch.clone()]);
    let together = a_log(vec![sw_launch, (2.0, launch(NE_D1, route(&[[30.0, 90.0, 15.0], [20.0, 40.0, 20.0]]))), (9.0, detour(NE_D1, &[[35.0, 70.0, 18.0]]))]);

    let (sw_alone, sw_together) = (flight(SW, SW_D1, &alone, 60.0), flight(SW, SW_D1, &together, 60.0));

    assert_eq!(sw_together, sw_alone);
    let heights = [state_at(SW, SW_D1, &together, 20.0).position_enu[2], state_at(NE, NE_D1, &together, 20.0).position_enu[2]];
    assert!(heights.iter().all(|up| *up >= MIN_UP_M), "both drones airborne at 20 s: {heights:?}");
}

#[test]
fn the_same_log_and_moment_give_the_same_pose() {
    let sortie = the_survey_sortie();

    let (first, again) = (state_at(SW, SW_D1, &sortie, 23.4), state_at(SW, SW_D1, &sortie, 23.4));

    assert_eq!(first, again);
}

#[test]
fn the_incremental_autopilot_matches_the_replayed_one() {
    let sortie = the_survey_sortie();
    let mut live = Autopilot::new(NE_D1, NE);

    let advanced: Vec<DroneState> = frame_times().into_iter().map(|t| live.advance(&sortie, t)).collect();

    let replayed: Vec<DroneState> = frame_times().into_iter().map(|t| state_at(NE, NE_D1, &sortie, t)).collect();
    assert_eq!(advanced, replayed);
}

// ---- unit: phases ---------------------------------------------------------------------------

#[test]
fn a_drone_waits_on_its_pad_facing_the_nests_heading_until_it_is_launched() {
    let log = a_log(vec![(10.0, launch(SW_D1, route(&[[-20.0, 0.0, 12.0]])))]);

    let before = state_at(SW, SW_D1, &log, 9.9);

    assert_eq!(before, DroneState { position_enu: SW.pad_enu, velocity_enu: [0.0; 3], yaw_deg: 45.0, phase: Phase::Docked, target: None, legs_left: 0 });
}

#[test]
fn a_launch_takes_effect_at_the_first_step_at_or_after_its_moment() {
    let (early, late) = (a_log(vec![(1.01, launch(SW_D1, route(&[[-20.0, 0.0, 12.0]])))]), a_log(vec![(1.04, launch(SW_D1, route(&[[-20.0, 0.0, 12.0]])))]));

    let (from_early, from_late) = (state_at(SW, SW_D1, &early, 5.0), state_at(SW, SW_D1, &late, 5.0));

    assert_eq!(from_early, from_late, "both launches take effect at the 1.05 s step");
}

#[test]
fn a_drone_on_a_roof_nest_climbs_five_metres_above_its_pad_before_it_cruises() {
    let log = a_log(vec![(1.0, launch(ROOF_D1, route(&[[60.0, 22.0, 18.0]])))]);

    let flight = flight(ROOF, ROOF_D1, &log, 30.0);

    assert!(height_leaving_the_pad(&flight, ROOF) >= ROOF.pad_enu[2] + MIN_UP_M - 0.1, "left the roof too low");
}

#[test]
fn a_route_that_ends_in_hover_holds_over_its_last_waypoint() {
    let last = [-20.0, 20.0, 12.0];
    let log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[[-20.0, 0.0, 12.0], last])))]);

    let later = state_at(SW, SW_D1, &log, 60.0);

    assert_eq!((later.phase, distance(later.position_enu, last) <= REACH_M, speed(&later)), (Phase::Hovering, true, 0.0));
}

#[test]
fn a_route_that_ends_in_return_flies_home_and_docks() {
    let log = a_log(vec![(1.0, launch(SW_D1, route(&[[-20.0, 0.0, 12.0], [-20.0, 20.0, 12.0]])))]);

    let later = state_at(SW, SW_D1, &log, 120.0);

    assert!(is_docked_on(&later, SW), "{later:?}");
}

#[test]
fn a_drone_flying_north_turns_to_face_north() {
    let log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[[-40.0, 200.0, 12.0]])))]);

    let cruising = state_at(SW, SW_D1, &log, 30.0);

    assert!(wrapped_deg(cruising.yaw_deg - 90.0).abs() < 1.0, "yaw {}", cruising.yaw_deg);
}

#[test]
fn a_command_pushed_while_flying_applies_from_its_moment_as_if_it_had_been_logged() {
    let mut log = a_log(vec![(1.0, launch(SW_D1, route_ending_in_hover(&[[-20.0, 0.0, 12.0], [-20.0, 100.0, 12.0]])))]);
    let mut live = Autopilot::new(SW_D1, SW);
    live.advance(&log, 18.0);
    log.push(20.0, detour(SW_D1, &[[-35.0, 30.0, 15.0]])).expect("a detour in flight is accepted");

    let at_forty = live.advance(&log, 40.0);

    assert_eq!(at_forty, state_at(SW, SW_D1, &log, 40.0));
}

#[test]
fn an_autopilot_asked_for_an_earlier_moment_replays_to_it() {
    let sortie = the_survey_sortie();
    let mut live = Autopilot::new(SW_D1, SW);
    live.advance(&sortie, 30.0);

    let rewound = live.advance(&sortie, 12.0);

    assert_eq!(rewound, state_at(SW, SW_D1, &sortie, 12.0));
}

// ---- unit: one step -------------------------------------------------------------------------

#[test]
fn one_step_never_changes_the_horizontal_speed_by_more_than_the_acceleration_limit() {
    let (state, plan) = (cruising_at([0.0, 0.0, 10.0], [0.0; 3]), a_plan(SW, &[[100.0, 0.0, 10.0]]));

    let after = stepped(state, plan, STEP_S);

    assert!(speed(&after[0]) > 0.0 && speed(&after[0]) <= MAX_ACCEL_M_S2 * STEP_S + EPS, "{:?}", after[0]);
}

#[test]
fn one_climbing_step_rises_no_more_than_the_climb_limit() {
    let (state, plan) = (in_phase(Phase::Climbing, [0.0, 0.0, 0.0], [0.0; 3]), a_plan(Home { pad_enu: [0.0; 3], yaw_deg: 0.0 }, &[[0.0, 30.0, 20.0]]));

    let after = stepped(state, plan, STEP_S);

    assert!(after[0].position_enu[2] > 0.0 && after[0].position_enu[2] <= MAX_CLIMB_M_S * STEP_S + EPS, "{:?}", after[0]);
}

#[test]
fn a_waypoint_within_a_metre_is_reached_and_the_next_becomes_current() {
    let mut state = DroneState { target: Some([0.5, 0.0, 10.0]), legs_left: 1, ..cruising_at([0.0, 0.0, 10.0], [5.0, 0.0, 0.0]) };
    let mut plan = a_plan(SW, &[[0.5, 0.0, 10.0], [50.0, 0.0, 10.0]]);

    step(&mut state, &mut plan, STEP_S);

    assert_eq!((state.target, state.legs_left, plan.route.len()), (Some([50.0, 0.0, 10.0]), 0, 1));
}

#[test]
fn a_hovering_drone_slows_to_a_stop_within_the_acceleration_limit() {
    let state = in_phase(Phase::Hovering, [0.0, 0.0, 10.0], [6.0, 0.0, 0.0]);

    let slowing = stepped(state, a_plan(SW, &[]), 4.0);

    let speeds: Vec<f32> = slowing.iter().map(speed).collect();
    assert!(Extremes::of(&slowing).speed_change_m_s2 <= MAX_ACCEL_M_S2 + EPS && speeds.last() == Some(&0.0), "{speeds:?}");
}

#[test]
fn a_landing_drone_sinks_no_faster_than_a_metre_a_second_and_docks_on_its_pad() {
    let home = Home { pad_enu: [5.0, 5.0, 0.0], yaw_deg: 0.0 };
    let state = in_phase(Phase::Landing, [5.0, 5.0, 6.0], [0.0; 3]);

    let landing = stepped(state, a_plan(home, &[]), 10.0);

    let sinking = landing.windows(2).map(|w| (w[0].position_enu[2] - w[1].position_enu[2]) / STEP_S).fold(0.0, f32::max);
    assert!(sinking <= MAX_DESCENT_M_S + EPS && is_docked_on(landing.last().expect("steps"), home), "sank at {sinking} m/s, ended {:?}", landing.last());
}
