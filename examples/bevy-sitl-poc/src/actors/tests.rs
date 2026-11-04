//! Facing and turning, the bob, the figure JSON, the tracks line, and a figure walking its tree.

use std::f32::consts::{FRAC_PI_2, FRAC_PI_4};

use bevy::math::Vec3;

use super::*;

fn gait() -> FigureDef {
    FigureDef {
        yaw_ease_s: 0.3,
        bob_m: 0.03,
        steps_per_s: 2.0,
        reference_speed_m_s: 1.4,
        visor: None,
        model: None,
        body_m: [0.6, 0.6, 1.8],
        rig: None,
        pose_rigs: Default::default(),
    }
}

#[test]
fn a_turn_eases_to_its_heading_over_its_duration_and_then_holds() {
    let turn = Turn {
        from: 0.0,
        to: FRAC_PI_2,
        started_s: 1.0,
    };

    assert!(yaw_at(turn, 1.0, 0.3).abs() < 1e-6);
    assert!((yaw_at(turn, 1.15, 0.3) - FRAC_PI_4).abs() < 1e-5);
    assert!((yaw_at(turn, 1.3, 0.3) - FRAC_PI_2).abs() < 1e-6);
    assert!((yaw_at(turn, 9.0, 0.3) - FRAC_PI_2).abs() < 1e-6);
}

#[test]
fn a_turn_takes_the_short_way_round_the_circle() {
    let turn = Turn {
        from: 3.0,
        to: -3.0,
        started_s: 0.0,
    };

    let midway = yaw_at(turn, 0.15, 0.3);
    let end = yaw_at(turn, 1.0, 0.3);

    assert!(midway.cos() < -0.9, "through π, not through 0: {midway}");
    assert!((end.cos() - (-3.0f32).cos()).abs() < 1e-5);
    assert!((end.sin() - (-3.0f32).sin()).abs() < 1e-5);
}

#[test]
fn a_figure_faces_its_heading_in_bevy_space() {
    for (heading, forward) in [
        (Vec2::X, Vec3::X),
        (Vec2::Y, Vec3::NEG_Z),
        (Vec2::NEG_X, Vec3::NEG_X),
    ] {
        let facing = Quat::from_rotation_y(bevy_yaw(heading)) * Vec3::NEG_Z;

        assert!(
            facing.abs_diff_eq(forward, 1e-5),
            "{heading:?} faces {facing:?}"
        );
    }
}

#[test]
fn a_walker_bobs_once_per_step_at_its_step_rate() {
    let at = |t| bob(&gait(), 1.4, 0.0, t);

    assert!((at(0.25) - 0.03).abs() < 1e-6, "a step's peak");
    assert!(at(0.5).abs() < 1e-6, "back on the ground between steps");
    assert!((at(0.75) - 0.03).abs() < 1e-6);
}

#[test]
fn a_faster_walker_steps_in_proportion_to_its_speed() {
    let peak_at_double_speed = bob(&gait(), 2.8, 0.0, 0.125);

    assert!((peak_at_double_speed - 0.03).abs() < 1e-6);
}

#[test]
fn a_standing_figure_does_not_bob() {
    assert_eq!(bob(&gait(), 0.0, 0.0, 0.3), 0.0);
}

#[test]
fn each_figure_steps_on_its_own_phase_and_the_same_one_every_time() {
    let phase = phase_of("evacuee-1");

    assert_eq!(phase, phase_of("evacuee-1"));
    assert_ne!(phase, phase_of("evacuee-2"));
    assert!((0.0..TAU).contains(&phase), "{phase}");
}

#[test]
fn the_figure_numbers_come_from_json_and_nonsense_is_refused_by_name() {
    let def = FigureDef::from_json(
        r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4}"#,
    )
    .expect("valid");
    let missing = FigureDef::from_json(r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2}"#)
        .unwrap_err();
    let stuck = FigureDef::from_json(
        r#"{"yaw_ease_s": 0, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4}"#,
    )
    .unwrap_err();

    assert_eq!(def, gait());
    assert!(missing.contains("reference_speed_m_s"), "{missing}");
    assert!(stuck.contains("yaw_ease_s"), "{stuck}");
}

#[test]
fn the_track_line_carries_the_frame_time_the_wind_and_each_moving_body_by_id_with_its_kind_and_heading() {
    let line = track_line(
        1_000_000_000,
        Vec2::new(6.0, 0.5),
        &[
            Body {
                id: "evacuee-2".to_owned(),
                enu: Vec3::new(12.0, 61.0, 0.0),
                action: Some("flee_from_fire".to_owned()),
                kind: "person".to_owned(),
                yaw_deg: 90.0,
                pose: None,
            },
            Body {
                id: "evacuee-1".to_owned(),
                enu: Vec3::new(1.0, 2.0, 0.0),
                action: None,
                kind: "bus".to_owned(),
                yaw_deg: -45.0,
                pose: None,
            },
        ],
    );

    let parsed: serde_json::Value = serde_json::from_str(&line).expect("json");
    assert_eq!(
        parsed,
        serde_json::json!({
            "t_ns": 1_000_000_000u64,
            "wind_enu": [6.0, 0.5],
            "objects": [
                {"id": "evacuee-1", "enu": [1.0, 2.0, 0.0], "action": null, "kind": "bus", "yaw_deg": -45.0},
                {"id": "evacuee-2", "enu": [12.0, 61.0, 0.0], "action": "flee_from_fire", "kind": "person", "yaw_deg": 90.0}
            ]
        })
    );
}

#[test]
fn a_figure_turns_to_face_the_way_it_walks() {
    let walk: Tree = serde_json::from_str(r#"{"node": "move_to", "enu": [10, 0], "speed_m_s": 2}"#)
        .expect("tree");
    let mut figure = Figure::new("evacuee-1", [0.0, 0.0, 0.0], Some(walk));
    let world = World {
        t_s: 0.0,
        fires: &[],
        burning_areas: &[],
        wind: &WindModel {
            from_deg: 0.0,
            speed_m_s: 0.0,
            gust_m_s: 0.0,
        },
        objects: &[],
    };

    figure.step(&world, 0.3);

    assert!(
        (figure.turn.to - bevy_yaw(Vec2::X)).abs() < 1e-5,
        "{:?}",
        figure.turn
    );
}

#[test]
fn a_walking_figure_is_tracked_as_a_person_facing_the_way_it_walks() {
    let north: Tree = serde_json::from_str(r#"{"node": "move_to", "enu": [0, 10], "speed_m_s": 2}"#).expect("tree");
    let mut figure = Figure::new("evacuee-1", [0.0, 0.0, 0.0], Some(north));
    let calm = WindModel { from_deg: 0.0, speed_m_s: 0.0, gust_m_s: 0.0 };
    let world = World { t_s: 0.0, fires: &[], burning_areas: &[], wind: &calm, objects: &[] };

    figure.step(&world, 0.3);

    let body = figure.body().expect("a moving body");
    assert_eq!((body.kind.as_str(), body.yaw_deg.round()), ("person", 90.0));
}

#[test]
fn a_posed_persons_track_carries_the_pose() {
    let line = track_line(
        0,
        Vec2::ZERO,
        &[Body {
            id: "survivor-1".to_owned(),
            enu: Vec3::new(-15.0, 31.0, 0.0),
            action: None,
            kind: "person".to_owned(),
            yaw_deg: 30.0,
            pose: Some("lying".to_owned()),
        }],
    );

    let parsed: serde_json::Value = serde_json::from_str(&line).expect("json");
    assert_eq!(parsed["objects"][0]["pose"], "lying");
}

#[test]
fn a_lying_survivor_without_a_tree_is_tracked_lying_where_they_lie() {
    let survivor = Figure::new("survivor-1", [-15.0, 31.0, 0.0], None).posed(crate::figure_anim::Pose::Lying, 30.0);

    let body = survivor.body().expect("a posed person is tracked");

    assert_eq!((body.pose.as_deref(), body.yaw_deg, body.enu), (Some("lying"), 30.0, Vec3::new(-15.0, 31.0, 0.0)));
}

/// The primary wave rig and a sitting rig, as the shipped figure names them (test fixtures).
const WAVE_RIG: &str = r#""rig": {"glb": "models/person/wave.glb",
    "clips": {"idle": "Idle", "walk": "Walk", "run": "Run", "wave": "Wave", "lie": "Death"},
    "walk_ground_m_s": 1.1, "run_ground_m_s": 2.5, "run_above_m_s": 1.8, "blend_s": 0.3, "standing_height_m": 1.8}"#;
const SIT_RIG: &str = r#""glb": "models/person/sit.glb",
    "clips": {"idle": "Idle", "walk": "Walk", "run": "Run", "sit": "SitIdle"},
    "walk_ground_m_s": 3.8, "run_ground_m_s": 10.3, "run_above_m_s": 7.0, "blend_s": 0.3, "standing_height_m": 5.2"#;

fn figure_with(rig: &str, pose_rigs: &str) -> String {
    format!(
        r#"{{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4, {rig}, "pose_rigs": {{{pose_rigs}}}}}"#
    )
}

fn sitting_figure() -> FigureDef {
    FigureDef::from_json(&figure_with(WAVE_RIG, &format!(r#""sitting": {{{SIT_RIG}}}"#))).expect("valid figure")
}

fn shipped_figure() -> FigureDef {
    let text = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/assets/behaviour/person.figure.json")).expect("figure file");
    FigureDef::from_json(&text).expect("valid figure")
}

/// The asset lock's entry for a rig file, or `Null` when the file is not pinned.
fn lock_entry(glb: &str) -> serde_json::Value {
    let text = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/assets/assets.lock.json")).expect("asset lock");
    let lock: serde_json::Value = serde_json::from_str(&text).expect("json");
    lock["assets"]
        .as_array()
        .and_then(|assets| assets.iter().find(|asset| asset["path"] == glb).cloned())
        .unwrap_or(serde_json::Value::Null)
}

#[test]
fn the_shipped_figure_has_a_clip_for_every_pose_in_a_pinned_file() {
    let figure = shipped_figure();

    for pose in [Pose::Standing, Pose::Lying, Pose::Sitting, Pose::Waving] {
        let rig = figure.rig_for(pose, None, None).expect("every pose has a rig");
        let clip = rig.clip_for(pose).expect("every pose names a clip");
        let animations = lock_entry(&rig.glb)["animations"].clone();
        assert!(
            animations.as_array().is_some_and(|names| names.iter().any(|name| name == clip)),
            "{pose:?}: {clip:?} is not an animation of the pinned {}",
            rig.glb
        );
    }
}

#[test]
fn every_rig_file_of_the_shipped_figure_is_a_pinned_cc0_model() {
    let figure = shipped_figure();

    for pose in [Pose::Standing, Pose::Sitting] {
        let glb = figure.rig_for(pose, None, None).expect("a rig").glb;
        let pin = lock_entry(&glb);
        assert_eq!(pin["license"], "CC0-1.0", "{glb}");
        assert_eq!(pin["sha256"].as_str().map(str::len), Some(64), "{glb}");
    }
}

#[test]
fn a_sitting_person_is_drawn_on_the_rig_that_names_sitting() {
    let rig = sitting_figure().rig_for(Pose::Sitting, None, None).expect("a rig");

    assert_eq!(rig.glb, "models/person/sit.glb");
}

#[test]
fn a_standing_person_is_drawn_on_the_primary_rig_even_when_a_pose_has_its_own() {
    let rig = sitting_figure().rig_for(Pose::Standing, None, None).expect("a rig");

    assert_eq!(rig.glb, "models/person/wave.glb");
}

#[test]
fn a_lying_person_is_drawn_on_the_primary_rig_when_no_pose_rig_names_lying() {
    let rig = sitting_figure().rig_for(Pose::Lying, None, None).expect("a rig");

    assert_eq!(rig.glb, "models/person/wave.glb");
}

#[test]
fn a_person_with_their_own_glb_is_drawn_on_it_with_the_clips_of_their_pose() {
    let rig = sitting_figure()
        .rig_for(Pose::Sitting, None, Some("library/polypizza/x1/person.glb"))
        .expect("a rig");

    assert_eq!((rig.glb.as_str(), rig.clips.sit.as_deref()), ("library/polypizza/x1/person.glb", Some("SitIdle")));
}

#[test]
fn a_person_is_drawn_at_the_pace_of_their_height_on_the_rig_they_are_drawn_with() {
    // Given a 1.62 m person: the sit rig stands 5.2 m, so it is scaled by 0.3115
    let rig = sitting_figure().rig_for(Pose::Sitting, Some(1.62), None).expect("a rig");

    assert!((rig.walk_ground_m_s - 3.8 * 1.62 / 5.2).abs() < 1e-4, "{}", rig.walk_ground_m_s);
}

#[test]
fn a_sitting_pose_rig_that_names_no_sitting_clip_is_refused_by_name() {
    let no_sit = SIT_RIG.replace(r#""sit": "SitIdle""#, r#""wave": "Wave""#);

    let refused = FigureDef::from_json(&figure_with(WAVE_RIG, &format!(r#""sitting": {{{no_sit}}}"#))).unwrap_err();

    assert!(refused.contains("sitting"), "{refused}");
}

#[test]
fn a_pose_that_no_rig_carries_a_clip_for_is_refused_by_name() {
    let no_wave = WAVE_RIG.replace(r#""wave": "Wave", "#, "");

    let refused = FigureDef::from_json(&figure_with(&no_wave, "")).unwrap_err();

    assert!(refused.contains("waving"), "{refused}");
}

#[test]
fn a_pose_rig_for_standing_is_refused_because_the_primary_rig_carries_standing() {
    let refused = FigureDef::from_json(&figure_with(WAVE_RIG, &format!(r#""standing": {{{SIT_RIG}}}"#))).unwrap_err();

    assert!(refused.contains("standing"), "{refused}");
}

#[test]
fn a_pose_rig_for_a_pose_the_figure_does_not_know_is_refused_by_name() {
    let refused = FigureDef::from_json(&figure_with(WAVE_RIG, &format!(r#""dancing": {{{SIT_RIG}}}"#))).unwrap_err();

    assert!(refused.contains("dancing"), "{refused}");
}

#[test]
fn pose_rigs_without_a_primary_rig_are_refused_by_name() {
    let text = format!(
        r#"{{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4, "pose_rigs": {{"sitting": {{{SIT_RIG}}}}}}}"#
    );

    let refused = FigureDef::from_json(&text).unwrap_err();

    assert!(refused.contains("pose_rigs"), "{refused}");
}

#[test]
fn a_pose_rig_that_is_not_gltf_is_refused_by_name() {
    let fbx = SIT_RIG.replace("sit.glb", "sit.fbx");

    let refused = FigureDef::from_json(&figure_with(WAVE_RIG, &format!(r#""sitting": {{{fbx}}}"#))).unwrap_err();

    assert!(refused.contains("sit.fbx"), "{refused}");
}

#[test]
fn a_rig_that_runs_slower_than_it_walks_is_refused_by_name() {
    let text = r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4,
        "rig": {"glb": "models/person.glb", "clips": {"idle": "Idle", "walk": "Walk", "run": "Run", "wave": "Wave", "sit": "Sit", "lie": "Death"},
                "walk_ground_m_s": 1.4, "run_ground_m_s": 1.0, "run_above_m_s": 2.0, "blend_s": 0.25, "standing_height_m": 1.8}}"#;

    let refused = FigureDef::from_json(text).unwrap_err();

    assert!(refused.contains("run_ground_m_s"), "{refused}");
}
