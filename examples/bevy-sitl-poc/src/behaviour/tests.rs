//! Each node kind, determinism, fleeing the burnt area, the wind ramp and validation.

use super::*;

const DT: f32 = 1.0 / TICK_HZ;

fn calm() -> WindModel {
    WindModel {
        from_deg: 270.0,
        speed_m_s: 0.0,
        gust_m_s: 0.0,
    }
}

fn tree(json: &str) -> Tree {
    serde_json::from_str(json).unwrap_or_else(|e| panic!("{e}"))
}

/// Ticks `runner` from `t0` for `seconds`, with `fires` and the runner's own wind as the world.
fn run(runner: &mut Runner, fires: &[FireSpec], t0: f32, seconds: f32) -> Status {
    let mut status = Status::Running;
    for i in 0..(seconds * TICK_HZ).round() as usize {
        let wind = runner.wind;
        let world = World {
            t_s: t0 + i as f32 * DT,
            fires,
            burning_areas: &[],
            wind: &wind,
            objects: &[],
        };
        status = runner.tick(&world, DT);
    }
    status
}

fn a_fire_west_of_the_origin() -> FireSpec {
    FireSpec {
        ignition: Vec2::new(-10.0, 0.0),
        start_s: 0.0,
        spread_m_s: 0.3,
        max_radius_m: 40.0,
        head_wind_gain: 0.5,
        lb_wind_gain: 0.25,
    }
}

#[test]
fn a_body_walks_to_its_goal_at_its_speed_then_succeeds() {
    let mut runner = Runner::new(
        tree(r#"{"node": "move_to", "enu": [10, 0], "speed_m_s": 2}"#),
        Vec2::ZERO,
        calm(),
    );

    let halfway = run(&mut runner, &[], 0.0, 2.5);
    let at_two_and_a_half = runner.position;
    let done = run(&mut runner, &[], 2.5, 3.0);

    assert_eq!(halfway, Status::Running);
    assert!(
        (at_two_and_a_half.x - 5.0).abs() < 0.11,
        "{at_two_and_a_half:?}"
    );
    assert_eq!(done, Status::Success);
    assert!(runner.position.distance(Vec2::new(10.0, 0.0)) <= 0.25);
}

#[test]
fn a_sequence_walks_its_path_then_idles() {
    let mut runner = Runner::new(
        tree(
            r#"{"node": "sequence", "children": [
                {"node": "follow_path", "enu": [[4, 0], [4, 3]], "speed_m_s": 1},
                {"node": "idle", "s": 2}]}"#,
        ),
        Vec2::ZERO,
        calm(),
    );

    run(&mut runner, &[], 0.0, 7.5);
    let idling = runner.action().map(str::to_owned);
    let done = run(&mut runner, &[], 7.5, 2.0);

    assert!(runner.position.distance(Vec2::new(4.0, 3.0)) <= 0.25);
    assert_eq!(idling.as_deref(), Some("idle"));
    assert_eq!(done, Status::Success);
}

#[test]
fn time_after_fails_before_its_time_and_succeeds_after() {
    let gate = tree(r#"{"node": "time_after", "s": 30}"#);
    let wind = calm();
    let before = World {
        t_s: 29.0,
        fires: &[],
        burning_areas: &[],
        wind: &wind,
        objects: &[],
    };
    let after = World {
        t_s: 31.0,
        fires: &[],
        burning_areas: &[],
        wind: &wind,
        objects: &[],
    };

    assert_eq!(
        Runner::new(gate.clone(), Vec2::ZERO, wind).tick(&before, DT),
        Status::Failure
    );
    assert_eq!(
        Runner::new(gate, Vec2::ZERO, wind).tick(&after, DT),
        Status::Success
    );
}

#[test]
fn a_selector_flees_a_near_fire_and_otherwise_wanders() {
    let evacuee = r#"{"node": "selector", "children": [
        {"node": "sequence", "children": [
            {"node": "near_fire", "within_m": 20},
            {"id": "flee", "node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 30}]},
        {"node": "wander", "radius_m": 6, "speed_m_s": 0.8, "seed": 7}]}"#;
    let fire = [a_fire_west_of_the_origin()];
    let mut far = Runner::new(tree(evacuee), Vec2::new(200.0, 0.0), calm());
    let mut near = Runner::new(tree(evacuee), Vec2::ZERO, calm());

    run(&mut far, &fire, 0.0, 3.0);
    run(&mut near, &fire, 0.0, 3.0);

    assert_eq!(far.action(), Some("wander"));
    assert_eq!(near.action(), Some("flee_from_fire"));
    assert!(
        near.position.x > 0.0,
        "flees east, away from the fire: {:?}",
        near.position
    );
}

#[test]
fn a_fleeing_person_never_stands_in_the_burnt_area() {
    let mut runner = Runner::new(
        tree(r#"{"node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 30}"#),
        Vec2::new(-4.0, 1.0),
        WindModel {
            from_deg: 270.0,
            speed_m_s: 6.0,
            gust_m_s: 0.0,
        },
    );
    let fire = a_fire_west_of_the_origin();

    for i in 0..(120.0 * TICK_HZ) as usize {
        let t_s = i as f32 * DT;
        let wind = runner.wind;
        runner.tick(
            &World {
                t_s,
                fires: std::slice::from_ref(&fire),
                burning_areas: &[],
                wind: &wind,
                objects: &[],
            },
            DT,
        );
        assert!(
            !fire.burnt(runner.position, t_s, wind.velocity_enu(t_s)),
            "burnt at t={t_s}: {:?}",
            runner.position
        );
    }
}

#[test]
fn repeat_runs_its_child_the_given_number_of_times() {
    let mut runner = Runner::new(
        tree(
            r#"{"node": "repeat", "times": 2, "child":
                {"node": "follow_path", "enu": [[2, 0], [0, 0]], "speed_m_s": 1}}"#,
        ),
        Vec2::ZERO,
        calm(),
    );

    let after_one_lap = run(&mut runner, &[], 0.0, 4.5);
    let after_two = run(&mut runner, &[], 4.5, 4.5);

    assert_eq!(after_one_lap, Status::Running);
    assert_eq!(after_two, Status::Success);
}

#[test]
fn invert_swaps_success_and_failure() {
    let wind = calm();
    let early = World {
        t_s: 0.0,
        fires: &[],
        burning_areas: &[],
        wind: &wind,
        objects: &[],
    };

    let status = Runner::new(
        tree(r#"{"node": "invert", "child": {"node": "time_after", "s": 5}}"#),
        Vec2::ZERO,
        wind,
    )
    .tick(&early, DT);

    assert_eq!(status, Status::Success);
}

#[test]
fn near_object_reads_the_other_bodies() {
    let wind = calm();
    let others = [("car-1".to_owned(), Vec2::new(3.0, 4.0))];
    let world = World {
        t_s: 0.0,
        fires: &[],
        burning_areas: &[],
        wind: &wind,
        objects: &others,
    };

    let near = Runner::new(
        tree(r#"{"node": "near_object", "object": "car-1", "within_m": 6}"#),
        Vec2::ZERO,
        wind,
    )
    .tick(&world, DT);
    let far = Runner::new(
        tree(r#"{"node": "near_object", "object": "car-1", "within_m": 4}"#),
        Vec2::ZERO,
        wind,
    )
    .tick(&world, DT);

    assert_eq!((near, far), (Status::Success, Status::Failure));
}

#[test]
fn a_burning_building_is_a_fire_to_flee_from() {
    let wind = calm();
    let block = [vec![
        Vec2::new(-12.0, -5.0),
        Vec2::new(-2.0, -5.0),
        Vec2::new(-2.0, 5.0),
        Vec2::new(-12.0, 5.0),
    ]];
    let mut runner = Runner::new(
        tree(
            r#"{"node": "sequence", "children": [
            {"node": "near_fire", "within_m": 5},
            {"node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 20}]}"#,
        ),
        Vec2::ZERO,
        wind,
    );

    for i in 0..100 {
        runner.tick(
            &World {
                t_s: i as f32 * DT,
                fires: &[],
                burning_areas: &block,
                wind: &wind,
                objects: &[],
            },
            DT,
        );
    }

    assert!(
        runner.position.x >= 18.0 - 0.1,
        "18 m east of the block's east wall: {:?}",
        runner.position
    );
}

#[test]
fn wandering_is_deterministic_for_a_seed_and_stays_in_its_radius() {
    let wanderer = r#"{"node": "wander", "radius_m": 6, "speed_m_s": 0.8, "seed": 3}"#;
    let mut a = Runner::new(tree(wanderer), Vec2::new(5.0, 5.0), calm());
    let mut b = Runner::new(tree(wanderer), Vec2::new(5.0, 5.0), calm());

    let mut farthest: f32 = 0.0;
    for i in 0..600 {
        let wind = calm();
        let world = World {
            t_s: i as f32 * DT,
            fires: &[],
            burning_areas: &[],
            wind: &wind,
            objects: &[],
        };
        a.tick(&world, DT);
        b.tick(&world, DT);
        farthest = farthest.max(a.position.distance(Vec2::new(5.0, 5.0)));
    }

    assert_eq!(a.position, b.position);
    assert!(farthest > 1.0 && farthest <= 6.0 + 1e-3, "{farthest}");
}

#[test]
fn the_wind_tree_veers_and_strengthens_the_wind_over_its_ramp() {
    let mut wind = Runner::new(
        tree(
            r#"{"node": "sequence", "children": [
                {"node": "idle", "s": 20},
                {"node": "set_wind", "from_deg": 300, "speed_m_s": 10, "gust_m_s": 3, "over_s": 30}]}"#,
        ),
        Vec2::ZERO,
        WindModel {
            from_deg: 270.0,
            speed_m_s: 6.0,
            gust_m_s: 1.0,
        },
    );

    run(&mut wind, &[], 0.0, 20.0);
    let before_ramp = wind.wind;
    run(&mut wind, &[], 20.0, 15.0);
    let halfway = wind.wind;
    let done = run(&mut wind, &[], 35.0, 16.0);

    assert_eq!(
        before_ramp,
        WindModel {
            from_deg: 270.0,
            speed_m_s: 6.0,
            gust_m_s: 1.0
        }
    );
    assert!(
        (halfway.from_deg - 285.0).abs() < 0.5 && (halfway.speed_m_s - 8.0).abs() < 0.15,
        "{halfway:?}"
    );
    assert_eq!(done, Status::Success);
    assert_eq!(
        wind.wind,
        WindModel {
            from_deg: 300.0,
            speed_m_s: 10.0,
            gust_m_s: 3.0
        }
    );
}

#[test]
fn the_wind_turns_the_short_way_round_the_compass() {
    let mut wind = Runner::new(
        tree(
            r#"{"node": "set_wind", "from_deg": 10, "speed_m_s": 5, "gust_m_s": 0, "over_s": 10}"#,
        ),
        Vec2::ZERO,
        WindModel {
            from_deg: 350.0,
            speed_m_s: 5.0,
            gust_m_s: 0.0,
        },
    );

    run(&mut wind, &[], 0.0, 5.0);

    let d = wind.wind.from_deg.rem_euclid(360.0);
    assert!(!(1.0..=359.0).contains(&d), "through north, not south: {d}");
}

#[test]
fn an_unknown_node_kind_is_refused_by_name() {
    let err = serde_json::from_str::<Tree>(r#"{"node": "teleport", "enu": [0, 0]}"#)
        .expect_err("unknown kind")
        .to_string();

    assert!(err.contains("teleport"), "{err}");
}

#[test]
fn an_object_may_not_set_the_wind_and_the_wind_may_not_walk() {
    let gusty =
        tree(r#"{"node": "set_wind", "from_deg": 0, "speed_m_s": 5, "gust_m_s": 0, "over_s": 1}"#);
    let walker = tree(r#"{"node": "move_to", "enu": [1, 1], "speed_m_s": 1}"#);

    assert!(gusty.validate(Target::Object).is_err());
    assert!(walker.validate(Target::Wind).is_err());
    assert!(gusty.validate(Target::Wind).is_ok() && walker.validate(Target::Object).is_ok());
}

#[test]
fn duplicate_node_ids_and_empty_composites_are_refused() {
    let twins = tree(
        r#"{"node": "sequence", "children": [
            {"id": "a", "node": "idle", "s": 1}, {"id": "a", "node": "idle", "s": 2}]}"#,
    );
    let empty = tree(r#"{"node": "selector", "children": []}"#);
    let still = tree(r#"{"node": "move_to", "enu": [1, 1], "speed_m_s": 0}"#);

    assert!(twins.validate(Target::Object).unwrap_err().contains('a'));
    assert!(empty.validate(Target::Object).is_err());
    assert!(still.validate(Target::Object).is_err());
}
