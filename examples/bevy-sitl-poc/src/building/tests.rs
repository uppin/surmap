use super::*;
use crate::scene_manifest::{DistrictDef, Element, SceneManifest};

fn manifest(extra: &str) -> SceneManifest {
    let text = format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null,
            "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0}},
            {extra}}}"#
    );
    SceneManifest::from_json(&text).expect("valid manifest")
}

fn building_of(manifest: &SceneManifest) -> &Building {
    manifest
        .elements
        .iter()
        .find_map(|e| {
            if let Element::Building(b) = e {
                Some(b)
            } else {
                None
            }
        })
        .expect("a building")
}

fn core() -> DistrictDef {
    DistrictDef {
        id: "core".into(),
        preset: "downtown".into(),
        position_enu: [0.0, 0.0, 0.0],
        size_m: [100.0, 100.0],
        seed: 0,
    }
}

#[test]
fn a_building_with_a_preset_or_inside_a_district_is_drawn_from_presets() {
    let by_preset = manifest(
        r#""elements": [{"kind": "building", "id": "a", "size_m": [5, 5, 5], "position_enu": [500, 0, 0], "facade": "brick", "roof": "slate"}]"#,
    );
    let by_district = manifest(
        r#""districts": [{"id": "core", "preset": "downtown", "position_enu": [0, 0, 0], "size_m": [100, 100]}], "elements": [{"kind": "building", "id": "b", "size_m": [5, 5, 5], "position_enu": [10, 0, 0]}]"#,
    );
    let legacy = manifest(
        r#""materials": {"wall": {"color": [1, 1, 1]}}, "elements": [{"kind": "building", "id": "c", "material": "wall", "size_m": [5, 5, 5], "position_enu": [10, 0, 0]}]"#,
    );

    assert!(is_styled(building_of(&by_preset), &[]));
    assert!(is_styled(building_of(&by_district), &[core()]));
    assert!(
        !is_styled(building_of(&legacy), &[]),
        "a legacy building with no district is drawn as before"
    );
}

#[test]
fn a_footprint_turns_with_the_buildings_yaw() {
    let tower = manifest(
        r#""districts": [{"id": "core", "preset": "downtown", "position_enu": [0, 0, 0], "size_m": [100, 100]}], "elements": [{"kind": "building", "id": "t", "size_m": [10, 4, 5], "position_enu": [20, 30, 0], "yaw_deg": 90}]"#,
    );

    let footprint = footprint(building_of(&tower), 2);

    let xs: Vec<f32> = footprint.polygon_enu.iter().map(|p| p.x).collect();
    let ys: Vec<f32> = footprint.polygon_enu.iter().map(|p| p.y).collect();
    assert!(
        (xs.iter().cloned().fold(f32::MIN, f32::max) - 22.0).abs() < 1e-4,
        "{xs:?}"
    );
    assert!(
        (ys.iter().cloned().fold(f32::MIN, f32::max) - 35.0).abs() < 1e-4,
        "{ys:?}"
    );
    assert_eq!(footprint.floors, 2);
}
