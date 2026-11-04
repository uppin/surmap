use std::f32::consts::{FRAC_PI_2, PI, TAU};

use bevy::math::Vec2;

use super::*;
use crate::behaviour::{Goal, Tree, World, TICK_HZ};
use crate::wind::WindModel;

const DT: f32 = 1.0 / TICK_HZ;

const A_CAR: &str = r#"{"glb": "models/car.glb", "length_m": 4.2, "width_m": 1.8, "height_m": 1.5,
    "wheel_nodes": ["wheel"], "wheel_radius_m": 0.32,
    "max_speed_m_s": 15.0, "accel_m_s2": 3.0, "brake_m_s2": 6.0, "turn_rate_deg_s": 45.0}"#;

const A_TRAIN: &str = r#"{"glb": "models/loco.glb", "length_m": 16.0, "width_m": 3.0, "height_m": 4.0,
    "max_speed_m_s": 30.0, "accel_m_s2": 0.5, "brake_m_s2": 1.0, "turn_rate_deg_s": 6.0,
    "carriage_glb": "models/wagon.glb", "carriage_spacing_m": 14.0}"#;

fn a_car() -> VehicleDef {
    VehicleDef::from_json(A_CAR).expect("a valid car")
}

fn a_train() -> VehicleDef {
    VehicleDef::from_json(A_TRAIN).expect("a valid train")
}

fn heading_for(goal: Vec2, speed_m_s: f32, stop: bool) -> Goal {
    Goal { point: goal, speed_m_s, stop }
}

fn wrap(angle: f32) -> f32 {
    (angle + PI).rem_euclid(TAU) - PI
}

/// Drives `body` for `seconds` in a calm, empty world, returning its drive after every tick.
fn drive_for(body: &mut VehicleBody, def: &VehicleDef, seconds: f32) -> Vec<Drive> {
    let calm = WindModel { from_deg: 0.0, speed_m_s: 0.0, gust_m_s: 0.0 };
    let ticks = (seconds * TICK_HZ).round() as u32;
    (0..ticks)
        .map(|n| {
            let world = World { t_s: n as f32 * DT, fires: &[], burning_areas: &[], wind: &calm, objects: &[] };
            body.tick(def, &world, DT);
            body.drive.clone()
        })
        .collect()
}

fn a_tree(json: &str) -> Tree {
    serde_json::from_str(json).expect("a valid tree")
}

#[test]
fn a_class_file_is_named_after_its_class() {
    assert_eq!(VehicleClass::Bus.file(), "vehicle/bus.vehicle.json");
}

#[test]
fn a_vehicle_is_tracked_as_its_class() {
    assert_eq!(VehicleClass::Train.kind(), "train");
}

#[test]
fn a_class_file_declares_its_look_and_limits() {
    let car = a_car();

    assert_eq!((car.max_speed_m_s, car.accel_m_s2, car.brake_m_s2, car.turn_rate_deg_s), (15.0, 3.0, 6.0, 45.0));
}

#[test]
fn a_class_that_cannot_accelerate_is_refused() {
    let stuck = A_CAR.replace("\"accel_m_s2\": 3.0", "\"accel_m_s2\": 0.0");

    assert!(VehicleDef::from_json(&stuck).unwrap_err().contains("accel_m_s2"));
}

#[test]
fn named_wheels_without_a_radius_are_refused() {
    let wheels = A_CAR.replace("\"wheel_radius_m\": 0.32,", "");

    assert!(VehicleDef::from_json(&wheels).unwrap_err().contains("wheel_radius_m"));
}

#[test]
fn a_carriage_without_a_spacing_is_refused() {
    let wagons = A_TRAIN.replace(", \"carriage_spacing_m\": 14.0", "");

    assert!(VehicleDef::from_json(&wagons).unwrap_err().contains("carriage_spacing_m"));
}

#[test]
fn every_shipped_class_file_is_valid() {
    for class in ["car", "bus", "truck", "train"] {
        let path = format!("{}/assets/vehicle/{class}.vehicle.json", env!("CARGO_MANIFEST_DIR"));
        let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"));

        VehicleDef::from_json(&text).unwrap_or_else(|e| panic!("{path}: {e}"));
    }
}

#[test]
fn a_vehicle_from_rest_gains_speed_no_faster_than_its_acceleration() {
    let car = a_car();
    let mut drive = Drive::new(Vec2::ZERO, 0.0);

    for _ in 0..10 {
        drive.step(&car, Some(heading_for(Vec2::new(500.0, 0.0), 15.0, true)), DT);
    }

    assert!(drive.speed_m_s > 0.0 && drive.speed_m_s <= car.accel_m_s2 * 1.0 + 1e-3, "{}", drive.speed_m_s);
}

#[test]
fn a_vehicle_never_drives_faster_than_its_class_allows() {
    let car = a_car();
    let mut drive = Drive::new(Vec2::ZERO, 0.0);

    let fastest = (0..300)
        .map(|_| {
            drive.step(&car, Some(heading_for(Vec2::new(5_000.0, 0.0), 40.0, true)), DT);
            drive.speed_m_s
        })
        .fold(0.0_f32, f32::max);

    assert!((fastest - car.max_speed_m_s).abs() < 1e-3, "{fastest}");
}

#[test]
fn a_vehicle_turns_no_faster_than_its_turn_rate() {
    let car = a_car();
    let mut drive = Drive::new(Vec2::ZERO, 0.0);
    let limit = car.turn_rate_deg_s.to_radians() * DT;

    let sharpest = (0..60)
        .map(|_| {
            let before = drive.heading_rad;
            drive.step(&car, Some(heading_for(Vec2::new(-50.0, 0.0), 10.0, true)), DT);
            wrap(drive.heading_rad - before).abs()
        })
        .fold(0.0_f32, f32::max);

    assert!(sharpest > 0.0 && sharpest <= limit + 1e-5, "{sharpest} > {limit}");
}

#[test]
fn a_vehicle_stops_on_its_goal_without_overshooting() {
    let car = a_car();
    let goal = Vec2::new(100.0, 0.0);
    let mut drive = Drive::new(Vec2::ZERO, 0.0);

    let furthest = (0..600)
        .map(|_| {
            drive.step(&car, Some(heading_for(goal, 15.0, true)), DT);
            drive.position.x
        })
        .fold(f32::MIN, f32::max);

    assert!(drive.position.distance(goal) <= 0.25, "{:?}", drive.position);
    assert!(drive.speed_m_s.abs() < 1e-3 && furthest <= goal.x + 0.25, "{} {furthest}", drive.speed_m_s);
}

#[test]
fn a_vehicle_without_a_goal_brakes_to_a_stop() {
    let car = a_car();
    let mut drive = Drive::new(Vec2::ZERO, 0.0);
    drive.speed_m_s = 12.0;

    for _ in 0..30 {
        drive.step(&car, None, DT);
    }

    assert_eq!(drive.speed_m_s, 0.0);
}

#[test]
fn a_goal_behind_a_slow_turner_is_reached_rather_than_circled() {
    let bus = VehicleDef { turn_rate_deg_s: 20.0, max_speed_m_s: 12.0, ..a_car() };
    let goal = Vec2::new(-6.0, 4.0);
    let mut drive = Drive::new(Vec2::ZERO, 0.0);

    for _ in 0..1200 {
        drive.step(&bus, Some(heading_for(goal, 12.0, true)), DT);
    }

    assert!(drive.position.distance(goal) <= 0.25, "{:?}", drive.position);
}

#[test]
fn wheels_turn_one_revolution_per_circumference_rolled() {
    assert!((wheel_angle(TAU * 0.32, 0.32) - TAU).abs() < 1e-5);
}

#[test]
fn a_vehicle_follows_its_tree_to_the_end_of_its_path() {
    let car = a_car();
    let tree = a_tree(r#"{"node": "follow_path", "enu": [[60.0, 0.0], [60.0, 60.0]], "speed_m_s": 10.0}"#);
    let mut body = VehicleBody::new(Some(tree), Vec2::ZERO, 0.0);

    let drives = drive_for(&mut body, &car, 60.0);

    let last = drives.last().expect("ticks");
    assert!(last.position.distance(Vec2::new(60.0, 60.0)) <= 0.25, "{:?}", last.position);
    assert!(drives.iter().all(|d| d.speed_m_s <= car.max_speed_m_s + 1e-3));
}

#[test]
fn a_vehicle_drives_the_same_track_every_run() {
    let car = a_car();
    let tree = r#"{"node": "repeat", "child": {"node": "follow_path", "enu": [[40.0, 0.0], [40.0, 40.0], [0.0, 0.0]], "speed_m_s": 9.0}}"#;
    let mut first = VehicleBody::new(Some(a_tree(tree)), Vec2::ZERO, 0.0);
    let mut second = VehicleBody::new(Some(a_tree(tree)), Vec2::ZERO, 0.0);

    assert_eq!(drive_for(&mut first, &car, 45.0), drive_for(&mut second, &car, 45.0));
}

#[test]
fn a_parked_vehicle_stays_where_it_was_left() {
    let mut body = VehicleBody::new(None, Vec2::new(3.0, 4.0), FRAC_PI_2);

    let drives = drive_for(&mut body, &a_car(), 5.0);

    assert!(drives.iter().all(|d| d.position == Vec2::new(3.0, 4.0) && d.heading_rad == FRAC_PI_2));
}

#[test]
fn carriages_follow_the_locomotive_along_its_track_through_a_bend() {
    let train = a_train();
    let tree = a_tree(r#"{"node": "follow_path", "enu": [[0.0, 200.0], [200.0, 200.0]], "speed_m_s": 12.0}"#);
    let mut body = VehicleBody::new(Some(tree), Vec2::ZERO, FRAC_PI_2);
    let drives = drive_for(&mut body, &train, 50.0);
    let track: Vec<Vec2> = drives.iter().map(|d| d.position).collect();
    let loco = drives.last().expect("ticks");

    let carriages = loco.carriage_poses(3, 14.0);

    assert_eq!(carriages.len(), 3);
    for (k, (at, _)) in carriages.iter().enumerate() {
        let on_track = track.iter().map(|p| p.distance(*at)).fold(f32::MAX, f32::min);
        let behind = loco.position.distance(*at);
        assert!(on_track <= 0.6, "carriage {k} is {on_track} m off the track");
        assert!(behind <= 14.0 * (k as f32 + 1.0) + 1e-3, "carriage {k} is {behind} m behind");
    }
}
