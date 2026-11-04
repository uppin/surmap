//! Drone nests in a manifest: where a pad may stand, how many drones it houses, what they are called.

use super::*;

/// A lot: collider ground (top at 0), `tower-1` (east 34..46, north -6..6, 15 m tall) and
/// `floodwater` (east -45..-35, north -50..50), plus `nests`.
fn a_lot_with(nests: &str) -> String {
    with_elements(&format!(
        r#"[{{"kind": "box", "id": "ground", "material": "concrete", "size_m": [200, 200, 0.2], "position_enu": [0, 0, -0.2], "collider": true}},
            {{"kind": "building", "id": "tower-1", "material": "concrete", "size_m": [12, 12, 15], "position_enu": [40, 0, 0]}},
            {{"kind": "box", "id": "floodwater", "material": "concrete", "size_m": [10, 100, 0.6], "position_enu": [-40, 0, 0], "water": true}},
            {nests}]"#
    ))
}

fn a_nest(id: &str, position_enu: [f32; 3], extra: &str) -> String {
    let [x, y, z] = position_enu;
    format!(r#"{{"kind": "drone_nest", "id": "{id}", "position_enu": [{x}, {y}, {z}]{extra}}}"#)
}

/// `count` one-drone nests 10 m apart along north 60, from east -40.
fn a_row_of_nests(count: usize) -> String {
    (0..count)
        .map(|i| a_nest(&format!("nest-{i}"), [i as f32 * 10.0 - 40.0, 60.0, 0.0], ""))
        .collect::<Vec<_>>()
        .join(", ")
}

fn refused_naming(text: &str, words: &[&str]) -> bool {
    matches!(SceneManifest::from_json(text), Err(ManifestError::Invalid(reason)) if words.iter().all(|w| reason.contains(w)))
}

fn nests_of(manifest: &SceneManifest) -> Vec<&DroneNest> {
    manifest
        .elements
        .iter()
        .filter_map(|e| match e {
            Element::DroneNest(nest) => Some(nest),
            _ => None,
        })
        .collect()
}

#[test]
fn a_drone_nest_is_declared_in_json_with_one_drone_facing_east_by_default() {
    let text = a_lot_with(&a_nest("nest-a", [0.0, 20.0, 0.0], ""));

    let manifest = SceneManifest::from_json(&text).expect("a nest on open ground is valid");

    let nest = DroneNest { id: "nest-a".into(), position_enu: [0.0, 20.0, 0.0], yaw_deg: 0.0, drones: 1 };
    assert_eq!(nests_of(&manifest), vec![&nest]);
}

#[test]
fn a_nests_drones_are_named_after_it_in_order() {
    let nest = DroneNest { id: "nest-a".into(), position_enu: [0.0, 20.0, 0.0], yaw_deg: 0.0, drones: 3 };

    let ids = nest.drone_ids();

    assert_eq!(ids, vec!["nest-a-d1", "nest-a-d2", "nest-a-d3"]);
}

#[test]
fn a_nest_on_open_ground_is_accepted() {
    let text = a_lot_with(&a_nest("nest-a", [0.0, 20.0, 0.0], r#", "yaw_deg": 90, "drones": 2"#));

    let manifest = SceneManifest::from_json(&text);

    assert!(manifest.is_ok(), "{manifest:?}");
}

#[test]
fn a_nest_on_a_roof_is_accepted() {
    let rooftop = a_lot_with(&a_nest("nest-roof", [40.0, 0.0, 15.0], ""));

    let manifest = SceneManifest::from_json(&rooftop);

    assert!(manifest.is_ok(), "{manifest:?}");
}

#[test]
fn a_nest_inside_a_building_is_refused_naming_the_building() {
    let inside = a_lot_with(&a_nest("nest-a", [40.0, 0.0, 0.0], ""));

    assert!(refused_naming(&inside, &["nest-a", "tower-1"]));
}

#[test]
fn a_square_pad_beside_a_building_is_accepted() {
    let beside = a_lot_with(&a_nest("nest-a", [32.5, 0.0, 0.0], ""));

    let manifest = SceneManifest::from_json(&beside);

    assert!(manifest.is_ok(), "{manifest:?}");
}

#[test]
fn a_pad_turned_so_its_corner_reaches_a_building_is_refused() {
    // Unturned, the pad's east edge is 0.3 m short of the wall; at 45° its corner is 0.2 m in.
    let turned = a_lot_with(&a_nest("nest-a", [32.5, 0.0, 0.0], r#", "yaw_deg": 45"#));

    assert!(refused_naming(&turned, &["nest-a", "tower-1"]));
}

#[test]
fn a_nest_on_water_is_refused() {
    let afloat = a_lot_with(&a_nest("nest-a", [-40.0, 10.0, 0.6], ""));

    assert!(refused_naming(&afloat, &["nest-a", "water"]));
}

#[test]
fn a_nest_outside_the_bounds_is_refused() {
    let far = a_lot_with(&a_nest("nest-a", [600.0, 0.0, 0.0], ""));

    assert!(refused_naming(&far, &["nest-a", "500"]));
}

#[test]
fn a_nest_higher_than_sixty_metres_is_refused() {
    let aloft = a_lot_with(&a_nest("nest-a", [0.0, 20.0, 75.0], ""));

    assert!(refused_naming(&aloft, &["nest-a", "60"]));
}

#[test]
fn a_nest_too_close_to_another_nest_is_refused_naming_both() {
    let crowded = a_lot_with(&format!(
        "{}, {}",
        a_nest("nest-a", [0.0, 20.0, 0.0], ""),
        a_nest("nest-b", [4.0, 20.0, 0.0], "")
    ));

    assert!(refused_naming(&crowded, &["nest-a", "nest-b", "6"]));
}

#[test]
fn nests_six_metres_apart_are_accepted() {
    let spaced = a_lot_with(&format!(
        "{}, {}",
        a_nest("nest-a", [0.0, 20.0, 0.0], ""),
        a_nest("nest-b", [6.0, 20.0, 0.0], "")
    ));

    let manifest = SceneManifest::from_json(&spaced);

    assert!(manifest.is_ok(), "{manifest:?}");
}

#[test]
fn a_nest_with_five_drones_is_refused() {
    let packed = a_lot_with(&a_nest("nest-a", [0.0, 20.0, 0.0], r#", "drones": 5"#));

    assert!(refused_naming(&packed, &["nest-a", "drones", "4"]));
}

#[test]
fn a_nest_with_no_drones_is_refused() {
    let empty = a_lot_with(&a_nest("nest-a", [0.0, 20.0, 0.0], r#", "drones": 0"#));

    assert!(refused_naming(&empty, &["nest-a", "drones"]));
}

#[test]
fn a_nest_whose_drone_id_is_taken_is_refused_as_a_duplicate() {
    let taken = a_lot_with(&format!(
        r#"{{"kind": "box", "id": "nest-a-d1", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, -30, 0]}}, {}"#,
        a_nest("nest-a", [0.0, 20.0, 0.0], "")
    ));

    assert_eq!(SceneManifest::from_json(&taken), Err(ManifestError::DuplicateId("nest-a-d1".into())));
}

#[test]
fn a_nest_id_outside_letters_digits_and_dashes_is_refused() {
    let spaced_id = a_lot_with(&a_nest("nest_a", [0.0, 20.0, 0.0], ""));

    assert!(refused_naming(&spaced_id, &["nest_a", "id"]));
}

#[test]
fn a_scene_holds_eight_nests_at_most() {
    let nine = a_lot_with(&a_row_of_nests(9));

    assert!(refused_naming(&nine, &["at most 8 nests"]));
}

#[test]
fn a_station_written_fleet_scenario_is_a_valid_manifest() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/fleet-nests.json");
    let text = std::fs::read_to_string(path).expect("the station's fleet-nests scenario");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts it");

    let drones: Vec<String> = nests_of(&manifest).iter().flat_map(|nest| nest.drone_ids()).collect();
    assert_eq!(drones, vec!["nest-sw-d1", "nest-sw-d2", "nest-ne-d1", "nest-ne-d2", "nest-roof-d1"]);
}
