//! The manifest parser and validator, against inline manifests and the shipped files.

use super::*;
use bevy::math::Vec3;

mod fleet;
mod nature;
mod water;

const A_MANIFEST: &str = r#"{
    "version": 1,
    "camera": "cameras/rig.camera.json",
    "environment": {"hdri": "hdri/sky.hdr", "sun_illuminance_lux": 100000.0,
                    "sun_elevation_deg": 38.0, "sun_azimuth_deg": 135.0,
                    "fog_visibility_m": 450.0},
    "materials": {"asphalt": {"base_color": "textures/asphalt_color.jpg",
                              "normal": "textures/asphalt_normal.png",
                              "arm": "textures/asphalt_arm.png", "uv_scale": 0.25}},
    "models": [
        {"id": "car-1", "glb": "models/car.glb", "position_enu": [3.0, 12.0, 0.0],
         "yaw_deg": 90.0, "collider": "box", "ground_truth": true, "kind": "car"},
        {"id": "rubble-1", "glb": "models/rubble.glb", "position_enu": [-4.0, 30.0, 0.0],
         "scale": 2.0, "collider": "trimesh"}
    ]
}"#;

fn with_models(models: &str) -> String {
    format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null, "sun_illuminance_lux": 1.0,
            "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0}},
            "models": {models}}}"#
    )
}

fn a_valid_manifest() -> SceneManifest {
    SceneManifest::from_json(A_MANIFEST).expect("valid manifest")
}

#[test]
fn a_manifest_lists_its_models_with_their_defaults() {
    let manifest = a_valid_manifest();

    let rubble = &manifest.models[1];
    assert_eq!(manifest.models.len(), 2);
    assert_eq!(
        (rubble.id.as_str(), rubble.scale, rubble.yaw_deg),
        ("rubble-1", 2.0, 0.0)
    );
    assert_eq!(rubble.collider, ColliderKind::Trimesh);
    assert!(!rubble.ground_truth);
}

#[test]
fn a_manifest_parses_its_arm_map_and_model_kinds() {
    let manifest = a_valid_manifest();

    let asphalt = &manifest.materials["asphalt"];
    assert_eq!(asphalt.arm.as_deref(), Some("textures/asphalt_arm.png"));
    assert_eq!(manifest.models[0].kind, "car");
    assert_eq!(manifest.models[1].kind, "model");
}

#[test]
fn a_manifest_names_every_asset_it_needs_once() {
    let manifest = a_valid_manifest();

    assert_eq!(
        manifest.asset_paths(),
        vec![
            "cameras/rig.camera.json",
            "hdri/sky.hdr",
            "models/car.glb",
            "models/rubble.glb",
            "textures/asphalt_arm.png",
            "textures/asphalt_color.jpg",
            "textures/asphalt_normal.png",
        ]
    );
}

#[test]
fn a_future_manifest_version_is_refused() {
    let text = A_MANIFEST.replacen("\"version\": 1", "\"version\": 2", 1);

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::UnsupportedVersion(2))
    );
}

#[test]
fn two_models_with_one_id_are_refused() {
    let twice = r#"[{"id": "car", "glb": "models/a.glb", "position_enu": [0,0,0], "collider": "none"},
                    {"id": "car", "glb": "models/b.glb", "position_enu": [1,0,0], "collider": "none"}]"#;

    assert_eq!(
        SceneManifest::from_json(&with_models(twice)),
        Err(ManifestError::DuplicateId("car".into()))
    );
}

#[test]
fn a_path_escaping_the_assets_directory_is_refused() {
    let escaping =
        r#"[{"id": "x", "glb": "../secret.glb", "position_enu": [0,0,0], "collider": "none"}]"#;

    assert_eq!(
        SceneManifest::from_json(&with_models(escaping)),
        Err(ManifestError::BadAssetPath("../secret.glb".into()))
    );
}

#[test]
fn a_model_that_is_not_gltf_is_refused() {
    let obj =
        r#"[{"id": "x", "glb": "models/x.obj", "position_enu": [0,0,0], "collider": "none"}]"#;

    assert_eq!(
        SceneManifest::from_json(&with_models(obj)),
        Err(ManifestError::BadAssetPath("models/x.obj".into()))
    );
}

#[test]
fn an_instance_north_of_the_origin_sits_down_bevy_minus_z() {
    let car = &a_valid_manifest().models[0];

    let transform = car.bevy_transform();

    assert!(transform
        .translation
        .abs_diff_eq(Vec3::new(3.0, 0.0, -12.0), 1e-5));
}

#[test]
fn a_ninety_degree_yaw_turns_east_into_north() {
    let car = &a_valid_manifest().models[0];

    let east_after_yaw = car.bevy_transform().rotation * Vec3::X;

    assert!(
        east_after_yaw.abs_diff_eq(Vec3::NEG_Z, 1e-5),
        "{east_after_yaw:?}"
    );
}

#[test]
fn the_shipped_scene_manifest_is_valid() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/assets/scene.json");
    let text = std::fs::read_to_string(path).expect("assets/scene.json is committed");

    let manifest = SceneManifest::from_json(&text).expect("shipped manifest validates");

    assert!(
        manifest.models.iter().any(|m| m.ground_truth),
        "a ground-truth object exists"
    );
}

fn with_elements(elements: &str) -> String {
    format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null, "sun_illuminance_lux": 1.0,
            "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0}},
            "materials": {{"concrete": {{"color": [0.5, 0.5, 0.5]}}}},
            "elements": {elements}}}"#
    )
}

#[test]
fn every_element_kind_is_declared_in_json() {
    let text = with_elements(
        r#"[{"kind": "box", "id": "pad", "material": "concrete", "size_m": [8, 8, 0.07], "position_enu": [0, 0, 0]},
            {"kind": "collapsed_building", "id": "c1", "material": "concrete", "footprint_m": [12, 10], "position_enu": [-16, 30, 0], "seed": 3},
            {"kind": "building", "id": "b1", "material": "concrete", "size_m": [12, 12, 15], "position_enu": [80, 0, 0], "windows": {"material": "concrete"}},
            {"kind": "person", "id": "p1", "position_enu": [-3.5, 16, 0], "coat": "concrete", "skin": "concrete"}]"#,
    );

    let manifest = SceneManifest::from_json(&text).expect("valid elements");

    let ids: Vec<&str> = manifest.elements.iter().map(Element::id).collect();
    assert_eq!(ids, vec!["pad", "c1", "b1", "p1"]);
    assert!(
        matches!(&manifest.elements[1], Element::CollapsedBuilding(c) if c.slabs == 4 && c.rubble == 25)
    );
}

#[test]
fn an_element_naming_an_undeclared_material_is_refused() {
    let text = with_elements(
        r#"[{"kind": "box", "id": "pad", "material": "marble", "size_m": [1, 1, 1], "position_enu": [0, 0, 0]}]"#,
    );

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::UnknownMaterial("marble".into()))
    );
}

#[test]
fn an_element_and_a_model_cannot_share_an_id() {
    let text = with_elements(r#"[{"kind": "box", "id": "car-1", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, 0, 0]}]"#)
        .replacen("\"elements\"", "\"models\": [{\"id\": \"car-1\", \"glb\": \"models/car.glb\", \"position_enu\": [0,0,0], \"collider\": \"none\"}], \"elements\"", 1);

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::DuplicateId("car-1".into()))
    );
}

#[test]
fn a_scene_scatters_debris_over_one_box_at_most() {
    let scattered = r#"{"kind": "box", "id": "IDX", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, 0, 0], "scatter": {"material": "concrete", "density": 28}}"#;
    let text = with_elements(&format!(
        "[{}, {}]",
        scattered.replace("IDX", "a"),
        scattered.replace("IDX", "b")
    ));

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::MoreThanOneScatter)
    );
}

#[test]
fn a_solid_material_needs_no_texture_and_names_no_asset_file() {
    let manifest = SceneManifest::from_json(&with_elements("[]")).expect("valid");

    assert_eq!(manifest.materials["concrete"].base_color, None);
    assert_eq!(manifest.asset_paths(), vec!["cameras/rig.camera.json"]);
}

#[test]
fn a_scenario_written_by_the_station_store_is_a_valid_manifest() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/sim_scenario/wreck-on-the-avenue.json"
    );
    let text = std::fs::read_to_string(path).expect("the station store's scenario fixture");

    let manifest =
        SceneManifest::from_json(&text).expect("the renderer accepts the store's scenario");

    assert!(manifest
        .models
        .iter()
        .any(|m| m.glb == "library/sketchfab/3f1c0a/model.glb"));
}

fn a_person_with(behaviour: &str) -> String {
    format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null,
            "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0,
            "fog_visibility_m": 1.0}},
            "materials": {{"coat": {{"color": [0.9, 0.4, 0.1]}}, "skin": {{"color": [0.8, 0.6, 0.5]}}}},
            "elements": [{{"kind": "person", "id": "evacuee-1", "position_enu": [0, 0, 0],
                           "coat": "coat", "skin": "skin", "behaviour": {behaviour}}}]}}"#
    )
}

#[test]
fn a_person_carries_its_behaviour_tree() {
    let text = a_person_with(r#"{"node": "wander", "radius_m": 6, "speed_m_s": 0.8, "seed": 7}"#);

    let manifest = SceneManifest::from_json(&text).expect("valid");

    assert!(matches!(&manifest.elements[0], Element::Person(p)
        if matches!(p.behaviour.as_ref().map(|b| &b.root.kind), Some(crate::behaviour::Kind::Wander { seed: 7, .. }))));
}

#[test]
fn a_person_whose_tree_sets_the_wind_is_refused() {
    let text = a_person_with(r#"{"node": "set_wind", "from_deg": 0, "speed_m_s": 5, "gust_m_s": 0, "over_s": 1}"#);

    assert!(matches!(SceneManifest::from_json(&text), Err(ManifestError::Invalid(_))));
}

#[test]
fn the_store_written_evacuation_scenario_drives_people_and_the_wind() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/wildfire-evacuation.json");
    let text = std::fs::read_to_string(path).expect("the station store's evacuation fixture");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts the store's evacuation scenario");

    let walkers = manifest.elements.iter().filter(|e| matches!(e, Element::Person(p) if p.behaviour.is_some())).count();
    assert_eq!(walkers, 3);
    assert!(manifest.weather.expect("weather").wind.behaviour.is_some());
}

fn a_downtown(extra: &str) -> String {
    format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null,
            "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0,
            "fog_visibility_m": 1.0}},
            "districts": [{{"id": "core", "preset": "downtown", "position_enu": [0, 0, 0], "size_m": [120, 80], "seed": 4}}],
            {extra}}}"#
    )
}

fn a_tower(fields: &str) -> String {
    format!(r#"{{"kind": "building", "id": "tower-2", "size_m": [18, 18, 42], "position_enu": [30, 10, 0]{fields}}}"#)
}

#[test]
fn a_building_in_a_district_needs_no_material_of_its_own() {
    let text = a_downtown(&format!(r#""elements": [{}]"#, a_tower(r#", "facade": "glass", "roof": "metal", "floors": 12"#)));

    let manifest = SceneManifest::from_json(&text).expect("the district styles it");

    assert!(matches!(&manifest.elements[0], Element::Building(b) if b.facade.as_deref() == Some("glass") && b.floors == Some(12)));
    assert_eq!(manifest.districts[0].preset, "downtown");
}

#[test]
fn a_facade_that_is_not_an_overture_value_or_a_facade_file_is_refused() {
    let text = a_downtown(&format!(r#""elements": [{}]"#, a_tower(r#", "facade": "marble""#)));

    assert!(matches!(SceneManifest::from_json(&text), Err(ManifestError::Invalid(_))));
}

#[test]
fn a_building_outside_every_district_without_a_material_is_refused() {
    let text = a_downtown(r#""elements": [{"kind": "building", "id": "barn", "size_m": [8, 8, 6], "position_enu": [500, 0, 0]}]"#);

    assert!(matches!(SceneManifest::from_json(&text), Err(ManifestError::Invalid(_))));
}

#[test]
fn a_building_fire_names_an_existing_building_and_one_of_its_floors() {
    let tower = a_tower(r#", "floors": 12"#);
    let fire = |building: &str, floor: u32| {
        a_downtown(&format!(r#""elements": [{tower}], "building_fires": [{{"id": "blaze-1", "building": "{building}", "floor": {floor}, "start_s": 5}}]"#))
    };

    let manifest = SceneManifest::from_json(&fire("tower-2", 3)).expect("valid");

    assert_eq!(manifest.building_fires[0].tuning, "building/fire.json");
    assert!(matches!(SceneManifest::from_json(&fire("tower-9", 3)), Err(ManifestError::Invalid(_))));
    assert!(matches!(SceneManifest::from_json(&fire("tower-2", 12)), Err(ManifestError::Invalid(_))));
}

#[test]
fn the_store_written_downtown_blaze_scenario_is_a_valid_manifest() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/downtown-blaze.json");
    let text = std::fs::read_to_string(path).expect("the station store's downtown-blaze fixture");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts the store's downtown-blaze scenario");

    assert!(!manifest.districts.is_empty() && !manifest.building_fires.is_empty());
}

fn with_vehicle(fields: &str) -> String {
    with_elements(&format!(r#"[{{"kind": "vehicle", "id": "v1", "position_enu": [0, 0, 0], {fields}}}]"#))
}

#[test]
fn a_vehicle_is_declared_by_its_class_with_its_start_pose_and_carriages() {
    let manifest = SceneManifest::from_json(&with_vehicle(r#""class": "train", "cars": 4, "yaw_deg": 90"#)).expect("a valid train");

    assert!(matches!(&manifest.elements[0], Element::Vehicle(v)
        if v.class == crate::vehicle::VehicleClass::Train && v.cars == 4 && v.ground_truth));
}

#[test]
fn carriages_on_anything_but_a_train_are_refused() {
    let refused = SceneManifest::from_json(&with_vehicle(r#""class": "bus", "cars": 2"#));

    assert!(matches!(refused, Err(ManifestError::Invalid(reason)) if reason.contains("v1") && reason.contains("cars")));
}

#[test]
fn a_vehicle_glb_override_that_is_not_gltf_is_refused() {
    let refused = SceneManifest::from_json(&with_vehicle(r#""class": "car", "glb": "models/car.obj""#));

    assert_eq!(refused, Err(ManifestError::BadAssetPath("models/car.obj".into())));
}

#[test]
fn a_vehicle_glb_override_escaping_the_assets_is_refused() {
    let refused = SceneManifest::from_json(&with_vehicle(r#""class": "car", "glb": "../car.glb""#));

    assert_eq!(refused, Err(ManifestError::BadAssetPath("../car.glb".into())));
}

#[test]
fn a_vehicle_glb_override_is_an_asset_the_scene_needs() {
    let manifest = SceneManifest::from_json(&with_vehicle(r#""class": "car", "glb": "library/sketchfab/ab12/model.glb""#)).expect("valid");

    assert!(manifest.asset_paths().contains(&"library/sketchfab/ab12/model.glb".to_owned()));
}

#[test]
fn a_vehicle_cannot_drive_the_wind() {
    let veer = r#""class": "car", "behaviour": {"node": "set_wind", "from_deg": 0, "speed_m_s": 1, "gust_m_s": 0, "over_s": 1}"#;

    let refused = SceneManifest::from_json(&with_vehicle(veer));

    assert!(matches!(refused, Err(ManifestError::Invalid(reason)) if reason.contains("vehicle v1")));
}

#[test]
fn the_street_traffic_scenario_the_station_writes_is_a_valid_manifest() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/street-traffic.json");
    let text = std::fs::read_to_string(path).expect("the station's street-traffic preset");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts it");

    let classes: Vec<_> = manifest.elements.iter().filter_map(|e| match e { Element::Vehicle(v) => Some(v.class), _ => None }).collect();
    use crate::vehicle::VehicleClass::{Bus, Car, Train, Truck};
    assert!([Car, Bus, Truck, Train].iter().all(|c| classes.contains(c)), "{classes:?}");
}

fn with_person(fields: &str) -> String {
    with_elements(&format!(r#"[{{"kind": "person", "id": "p1", "position_enu": [0, 0, 0], "coat": "concrete", "skin": "concrete", {fields}}}]"#))
}

#[test]
fn a_person_taller_than_any_survivor_is_refused() {
    let refused = SceneManifest::from_json(&with_person(r#""height_m": 3.0"#));

    assert!(matches!(refused, Err(ManifestError::Invalid(reason)) if reason.contains("p1") && reason.contains("height_m")));
}

#[test]
fn a_person_rig_override_that_is_not_gltf_is_refused() {
    let refused = SceneManifest::from_json(&with_person(r#""glb": "models/person.fbx""#));

    assert_eq!(refused, Err(ManifestError::BadAssetPath("models/person.fbx".into())));
}

#[test]
fn a_person_rig_override_is_an_asset_the_scene_needs() {
    let manifest = SceneManifest::from_json(&with_person(r#""glb": "library/polypizza/x1/person.glb""#)).expect("valid");

    assert!(manifest.asset_paths().contains(&"library/polypizza/x1/person.glb".to_owned()));
}

#[test]
fn the_survivors_scenario_the_station_writes_is_a_valid_manifest() {
    use crate::figure_anim::Pose::{Lying, Sitting, Waving};
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/earthquake-survivors.json");
    let text = std::fs::read_to_string(path).expect("the station's earthquake-survivors preset");

    let manifest = SceneManifest::from_json(&text).expect("the renderer accepts it");

    let poses: Vec<_> = manifest.elements.iter().filter_map(|e| match e { Element::Person(p) => Some(p.pose), _ => None }).collect();
    assert!([Lying, Sitting, Waving].iter().all(|p| poses.contains(p)), "{poses:?}");
}

#[test]
fn a_manifest_with_a_map_floor_parses_and_sizes_it_in_enu_metres() {
    let text = r#"{"version": 1, "camera": "cameras/rig.camera.json",
        "environment": {"hdri": null, "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0,
                        "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0},
        "map_floor": {"sw": [54.0, 25.0], "ne": [54.001, 25.002],
                      "texture": "library/map-floor/abc123.png", "zoom": 17}}"#;
    let manifest = SceneManifest::from_json(text).expect("valid map floor");
    assert!(manifest.asset_paths().iter().any(|p| p == "library/map-floor/abc123.png"));
    let floor = manifest.map_floor.expect("floor present");
    let (centre, size) = floor.centre_and_size_enu();
    assert!((centre[0] - 54.0005).abs() < 1e-9 && (centre[1] - 25.001).abs() < 1e-9);
    assert!((size[1] - 111.32).abs() < 0.01, "north size was {}", size[1]);
    assert!((size[0] - 130.84).abs() < 0.1, "east size was {}", size[0]);
}

#[test]
fn a_map_floor_with_an_absolute_texture_is_refused() {
    let text = r#"{"version": 1, "camera": "cameras/rig.camera.json",
        "environment": {"hdri": null, "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0,
                        "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0},
        "map_floor": {"sw": [54.0, 25.0], "ne": [54.001, 25.002],
                      "texture": "/etc/passwd.png", "zoom": 17}}"#;
    assert!(SceneManifest::from_json(text).is_err());
}

#[test]
fn the_shared_map_floor_fixture_parses_in_the_renderer_too() {
    // The same golden file the station validates (tests/fixtures/sim_scenario/map-floor.json).
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/map-floor.json");
    let text = std::fs::read_to_string(path).expect("shared map-floor fixture is committed");
    let manifest = SceneManifest::from_json(&text).expect("shared fixture validates in Rust");
    assert!(manifest.asset_paths().iter().any(|p| p == "library/map-floor/abc123.png"));
    let floor = manifest.map_floor.expect("fixture carries a floor");
    assert_eq!(floor.texture, "library/map-floor/abc123.png");
}
