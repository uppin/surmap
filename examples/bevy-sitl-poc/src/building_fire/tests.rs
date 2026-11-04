use super::*;

const DT: f32 = 0.5;

fn tuning() -> BuildingFireTuning {
    BuildingFireTuning {
        climb_s_per_floor: 45.0,
        descend_factor: 3.0,
        floor_burn_s: 600.0,
        ignite_distance_m: 6.0,
        ignite_wind_gain_s: 1.0,
        exposure_s: 60.0,
        effects: FireEffectPaths {
            window_flames: "fx/window_flames.fx.json".into(),
            smoke: "fx/building_smoke.fx.json".into(),
            embers: "fx/embers.fx.json".into(),
        },
        glow_colour: [1.0, 0.45, 0.12],
        glow_intensity: 10.0,
    }
}

/// A 10 × 10 m block with its west wall at `west`.
fn block(id: &str, west: f32, floors: u32) -> Footprint {
    Footprint {
        id: id.into(),
        polygon_enu: vec![
            Vec2::new(west, 0.0),
            Vec2::new(west + 10.0, 0.0),
            Vec2::new(west + 10.0, 10.0),
            Vec2::new(west, 10.0),
        ],
        floors,
    }
}

fn run(fires: &mut BuildingFires, from: f32, to: f32, wind: Vec2, wildfires: &[FireSpec]) {
    let mut t = from;
    while t < to {
        t += DT;
        fires.step(t, DT, wind, wildfires);
    }
}

fn tower_lit_on_floor_3() -> BuildingFires {
    BuildingFires::new(
        vec![block("tower", 0.0, 10)],
        vec![Ignition {
            building: "tower".into(),
            floor: 3,
            start_s: 5.0,
        }],
        tuning(),
    )
}

#[test]
fn the_shipped_tuning_is_valid() {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/assets/building/fire.json"
    ))
    .expect("shipped");

    BuildingFireTuning::from_json(&text).expect("valid");
}

#[test]
fn nothing_burns_before_the_ignition() {
    let mut fires = tower_lit_on_floor_3();

    run(&mut fires, 0.0, 4.0, Vec2::ZERO, &[]);

    assert_eq!(fires.floor("tower", 3), FloorState::Intact);
    assert_eq!(fires.ignited_at("tower"), None);
}

#[test]
fn the_fire_climbs_a_floor_per_climb_time_and_descends_slower() {
    let mut fires = tower_lit_on_floor_3();

    run(&mut fires, 0.0, 5.0 + 45.0 * 2.0 + 1.0, Vec2::ZERO, &[]);

    assert_eq!(fires.floor("tower", 3), FloorState::Burning);
    assert_eq!(
        fires.floor("tower", 5),
        FloorState::Burning,
        "two floors up after two climb times"
    );
    assert_eq!(fires.floor("tower", 6), FloorState::Intact);
    assert_eq!(
        fires.floor("tower", 2),
        FloorState::Intact,
        "one floor down takes 135 s"
    );
}

#[test]
fn a_floor_burns_out_after_its_burn_time() {
    let mut fires = tower_lit_on_floor_3();

    run(&mut fires, 0.0, 5.0 + 600.0 + 1.0, Vec2::ZERO, &[]);

    assert_eq!(fires.floor("tower", 3), FloorState::Burnt);
    assert_eq!(fires.floor("tower", 4), FloorState::Burning);
}

#[test]
fn a_close_neighbour_catches_after_its_exposure_time() {
    let mut fires = BuildingFires::new(
        vec![block("a", 0.0, 4), block("b", 15.0, 4)],
        vec![Ignition {
            building: "a".into(),
            floor: 0,
            start_s: 0.0,
        }],
        tuning(),
    );

    run(&mut fires, 0.0, 59.0, Vec2::ZERO, &[]);
    let before = fires.ignited_at("b");
    run(&mut fires, 59.0, 62.0, Vec2::ZERO, &[]);

    assert_eq!(before, None, "5 m apart, but not exposed for 60 s yet");
    assert!(fires.ignited_at("b").is_some());
}

#[test]
fn wind_carries_the_fire_farther_downwind_than_upwind() {
    // Neighbours 9 m away on both sides: beyond 6 m calm reach, within 6 + 1·4 downwind.
    let mut fires = BuildingFires::new(
        vec![
            block("west", -19.0, 3),
            block("source", 0.0, 3),
            block("east", 19.0, 3),
        ],
        vec![Ignition {
            building: "source".into(),
            floor: 0,
            start_s: 0.0,
        }],
        tuning(),
    );

    run(&mut fires, 0.0, 300.0, Vec2::new(4.0, 0.0), &[]);

    assert!(
        fires.ignited_at("east").is_some(),
        "downwind neighbour caught"
    );
    assert_eq!(fires.ignited_at("west"), None, "upwind neighbour did not");
}

#[test]
fn a_wildfire_reaching_a_building_lights_its_ground_floor() {
    let wildfire = FireSpec {
        ignition: Vec2::new(-10.0, 5.0),
        start_s: 0.0,
        spread_m_s: 0.5,
        max_radius_m: 40.0,
        head_wind_gain: 0.5,
        lb_wind_gain: 0.25,
    };
    let mut fires = BuildingFires::new(vec![block("hut", 0.0, 2)], vec![], tuning());

    run(
        &mut fires,
        0.0,
        25.0,
        Vec2::ZERO,
        std::slice::from_ref(&wildfire),
    );

    let lit = fires
        .ignited_at("hut")
        .expect("the front reached the west wall at 20 s");
    assert!((lit - 20.0).abs() <= 1.0, "{lit}");
    assert_eq!(fires.floor("hut", 0), FloorState::Burning);
}

#[test]
fn only_burning_buildings_are_burning_areas() {
    let mut fires = BuildingFires::new(
        vec![block("a", 0.0, 2), block("far", 200.0, 2)],
        vec![Ignition {
            building: "a".into(),
            floor: 0,
            start_s: 0.0,
        }],
        tuning(),
    );

    run(&mut fires, 0.0, 10.0, Vec2::ZERO, &[]);

    assert_eq!(
        fires.burning_footprints(),
        vec![block("a", 0.0, 2).polygon_enu]
    );
}
