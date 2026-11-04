//! Water boxes and vessels in a manifest: where a boat or ship may start and steer.

use super::*;

fn on_floodwater(vehicle: &str) -> String {
    with_elements(&format!(
        r#"[{{"kind": "box", "id": "floodwater", "material": "concrete", "size_m": [10, 100, 0.6], "position_enu": [0, 50, 0], "water": true}},
            {{"kind": "vehicle", "id": "b1", {vehicle}}}]"#
    ))
}

fn refused_naming(text: &str, words: &[&str]) -> bool {
    matches!(SceneManifest::from_json(text), Err(ManifestError::Invalid(reason)) if words.iter().all(|w| reason.contains(w)))
}

#[test]
fn a_boat_that_starts_on_dry_land_is_refused() {
    let ashore = on_floodwater(r#""class": "boat", "position_enu": [40, 50, 0]"#);

    assert!(refused_naming(&ashore, &["b1", "water"]));
}

#[test]
fn a_boat_steered_off_the_water_is_refused() {
    let aground = on_floodwater(r#""class": "boat", "position_enu": [0, 10, 0],
        "behaviour": {"node": "follow_path", "enu": [[0, 60], [30, 60]], "speed_m_s": 4}"#);

    assert!(refused_naming(&aground, &["b1", "water", "30"]));
}

#[test]
fn a_boat_may_not_wander_where_its_water_is_not_known() {
    let adrift = on_floodwater(r#""class": "boat", "position_enu": [0, 10, 0],
        "behaviour": {"node": "wander", "radius_m": 5, "speed_m_s": 2, "seed": 1}"#);

    assert!(refused_naming(&adrift, &["b1", "wander"]));
}

#[test]
fn a_car_cannot_start_in_the_water() {
    let sunk = on_floodwater(r#""class": "car", "position_enu": [0, 10, 0]"#);

    assert!(refused_naming(&sunk, &["b1", "water"]));
}

#[test]
fn the_flood_rescue_scenario_the_station_writes_is_a_valid_manifest() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/flood-rescue.json");
    let text = std::fs::read_to_string(path).expect("the station's flood-rescue preset");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts it");

    let boats = manifest.elements.iter().filter(|e| matches!(e, Element::Vehicle(v) if v.class == crate::vehicle::VehicleClass::Boat)).count();
    assert!(manifest.elements.iter().any(|e| matches!(e, Element::Box(b) if b.water)));
    assert_eq!(boats, 2);
}

#[test]
fn a_vessel_floats_on_the_top_of_the_water_under_its_start() {
    let text = on_floodwater(r#""class": "boat", "position_enu": [0, 10, 0]"#);
    let manifest = SceneManifest::from_json(&text).expect("a boat on the water is valid");
    let waters = surfaces(&manifest.elements);

    let top = surface_at(&waters, Vec2::new(0.0, 10.0)).expect("the boat starts on the water");

    assert_eq!(top.top_z_m, 0.6);
}

#[test]
fn a_turned_water_box_covers_the_footprint_it_is_turned_to() {
    let text = with_elements(
        r#"[{"kind": "box", "id": "floodwater", "material": "concrete", "size_m": [10, 100, 0.6],
            "position_enu": [0, 50, 0], "yaw_deg": 90, "water": true}]"#,
    );
    let manifest = SceneManifest::from_json(&text).expect("a turned water box is valid");
    let waters = surfaces(&manifest.elements);

    assert!(surface_at(&waters, Vec2::new(30.0, 50.0)).is_some());
    assert!(surface_at(&waters, Vec2::new(0.0, 80.0)).is_none());
}
