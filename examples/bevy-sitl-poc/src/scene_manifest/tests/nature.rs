//! Weather, fires and vegetation in a manifest: their defaults and the rules that refuse them.

use super::*;

fn with_weather_and_fire(extra: &str) -> String {
    format!(
        r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null,
            "sun_illuminance_lux": 1.0, "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0,
            "fog_visibility_m": 1.0}},
            "materials": {{"concrete": {{"color": [0.5, 0.5, 0.5]}}}},
            "weather": {{"rain_mm_h": 2.0, "wind": {{"from_deg": 250.0, "speed_m_s": 6.0}}}},
            {extra}}}"#
    )
}

fn a_fire(id: &str, spread: f32) -> String {
    format!(
        r#"{{"id": "{id}", "ignition_enu": [-20, 60, 0], "spread_m_s": {spread}, "max_radius_m": 35}}"#
    )
}

#[test]
fn weather_fires_and_vegetation_are_declared_in_json_with_their_defaults() {
    let text = with_weather_and_fire(&format!(
        r#""fires": [{}], "elements": [{{"kind": "vegetation", "id": "pines", "species": "species/pine.species.json",
            "position_enu": [-40, 60, 0], "size_m": [40, 60], "density_per_100m2": 3, "seed": 11}}]"#,
        a_fire("front-1", 0.15)
    ));

    let manifest = SceneManifest::from_json(&text).expect("valid");

    let weather = manifest.weather.expect("weather");
    assert_eq!(
        (weather.wind.gust_m_s, weather.rain_fx.as_str()),
        (0.0, "fx/rain.fx.json")
    );
    let fire = &manifest.fires[0];
    assert_eq!(
        (fire.start_s, fire.smoke, fire.head_wind_gain),
        (0.0, true, 0.5)
    );
    assert_eq!(fire.effects.smoke, "fx/smoke.fx.json");
    assert!(matches!(&manifest.elements[0], Element::Vegetation(v) if v.seed == 11));
}

#[test]
fn a_fire_sharing_an_element_id_is_refused() {
    let text = with_weather_and_fire(&format!(
        r#""fires": [{}], "elements": [{{"kind": "box", "id": "front-1", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, 0, 0]}}]"#,
        a_fire("front-1", 0.15)
    ));

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::DuplicateId("front-1".into()))
    );
}

#[test]
fn a_fire_that_cannot_spread_is_refused() {
    let text = with_weather_and_fire(&format!(r#""fires": [{}]"#, a_fire("front-1", 0.0)));

    assert!(matches!(
        SceneManifest::from_json(&text),
        Err(ManifestError::Invalid(_))
    ));
}

#[test]
fn a_species_path_that_is_not_a_species_file_is_refused() {
    let text = with_weather_and_fire(
        r#""elements": [{"kind": "vegetation", "id": "pines", "species": "models/pine.glb",
            "position_enu": [0, 0, 0], "size_m": [10, 10], "density_per_100m2": 3, "seed": 1}]"#,
    );

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::BadAssetPath("models/pine.glb".into()))
    );
}

#[test]
fn a_fire_effect_path_names_an_effect_file() {
    let text = with_weather_and_fire(
        r#""fires": [{"id": "f", "ignition_enu": [0, 0, 0], "spread_m_s": 0.1, "max_radius_m": 5,
            "effects": {"flames": "textures/fire.png"}}]"#,
    );

    assert_eq!(
        SceneManifest::from_json(&text),
        Err(ManifestError::BadAssetPath("textures/fire.png".into()))
    );
}

#[test]
fn the_store_written_wildfire_scenario_is_a_valid_manifest() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/sim_scenario/wildfire-edge.json"
    );
    let text = std::fs::read_to_string(path).expect("the station store's wildfire fixture");

    let manifest = SceneManifest::from_json(&text)
        .expect("the renderer accepts the store's wildfire scenario");

    assert!(!manifest.fires.is_empty() && manifest.weather.is_some());
}
