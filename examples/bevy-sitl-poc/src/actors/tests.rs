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
fn the_track_line_carries_the_frame_time_the_wind_and_each_moving_body_by_id() {
    let line = track_line(
        1_000_000_000,
        Vec2::new(6.0, 0.5),
        &[
            Body {
                id: "evacuee-2".to_owned(),
                enu: Vec3::new(12.0, 61.0, 0.0),
                action: Some("flee_from_fire".to_owned()),
            },
            Body {
                id: "evacuee-1".to_owned(),
                enu: Vec3::new(1.0, 2.0, 0.0),
                action: None,
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
                {"id": "evacuee-1", "enu": [1.0, 2.0, 0.0], "action": null},
                {"id": "evacuee-2", "enu": [12.0, 61.0, 0.0], "action": "flee_from_fire"}
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
