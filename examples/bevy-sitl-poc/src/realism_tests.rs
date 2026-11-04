//! The on-board detector realism contracts (docs/simulation/bevy-simulation.md § *On-board
//! detectors*): colour frames beside the grey eyes, humanoid figures posed from their walk clip,
//! people in the ground truth, and recognisable car models — every asset pinned with a licence.

use std::path::PathBuf;

use crate::actors::{clip_time, person_truth, FigureDef, FigureModel};
use crate::record::{frame_line, RecordPlan};
use crate::shots::RunMode;
use crate::wire::bgra_to_rgb8;

fn shipped(path: &str) -> String {
    std::fs::read_to_string(format!("{}/assets/{path}", env!("CARGO_MANIFEST_DIR")))
        .unwrap_or_else(|e| panic!("assets/{path} is shipped: {e}"))
}

fn args(list: &[&str]) -> Vec<String> {
    std::iter::once("bevy-sitl-poc").chain(list.iter().copied()).map(str::to_owned).collect()
}

/// The pin of `path` in `assets/assets.lock.json`, if any.
fn pin(path: &str) -> Option<serde_json::Value> {
    let lock: serde_json::Value = serde_json::from_str(&shipped("assets.lock.json")).expect("lock");
    lock["assets"].as_array()?.iter().find(|a| a["path"] == path).cloned()
}

fn a_walker() -> FigureModel {
    FigureModel { glb: "models/man/Man.glb".into(), scale: 1.0, yaw_deg: 0.0, clip_s: 0.6, coat_tint: false, rig: None }
}

#[test]
fn a_colour_recording_is_asked_for_with_its_own_flag() {
    let mode = RunMode::from_args(&args(&["--record", "cap", "--frames", "5", "--jpeg", "--colour"])).expect("valid");

    assert_eq!(
        mode.record,
        Some(RecordPlan { dir: PathBuf::from("cap"), frames: 5, rate_hz: 10.0, start_s: 0.0, jpeg: true, colour: true })
    );
}

#[test]
fn a_recording_stays_grey_unless_colour_is_asked_for() {
    let mode = RunMode::from_args(&args(&["--record", "cap"])).expect("valid");

    assert!(!mode.record.expect("a recording").colour);
}

#[test]
fn colour_conversion_reorders_bgra_into_rgb_and_skips_the_row_padding() {
    let mut padded = vec![9_u8; 2 * 12];
    padded[0..8].copy_from_slice(&[1, 2, 3, 255, 4, 5, 6, 255]);
    padded[12..20].copy_from_slice(&[7, 8, 9, 255, 10, 11, 12, 255]);

    let rgb = bgra_to_rgb8(&padded, 2, 2, 12);

    assert_eq!(rgb, vec![3, 2, 1, 6, 5, 4, 9, 8, 7, 12, 11, 10]);
}

#[test]
fn a_colour_frame_line_names_its_colour_image_beside_the_grey_eyes() {
    let pose = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0];

    let line: serde_json::Value = serde_json::from_str(&frame_line(1, 15, "frames/left/15.jpg", "frames/right/15.jpg", Some("frames/left_rgb/15.jpg"), pose)).expect("json");

    assert_eq!(line["left_rgb_ref"], "frames/left_rgb/15.jpg");
    assert_eq!((line["left_ref"].as_str(), line["frame_id"].as_u64()), (Some("frames/left/15.jpg"), Some(1)));
}

#[test]
fn a_grey_frame_line_names_no_colour_image() {
    let line: serde_json::Value =
        serde_json::from_str(&frame_line(1, 15, "l.png", "r.png", None, [0.0; 7])).expect("json");

    assert!(line.get("left_rgb_ref").is_none(), "{line}");
}

#[test]
fn a_figure_may_wear_a_humanoid_model() {
    let def = FigureDef::from_json(
        r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4,
            "model": {"glb": "models/man/Man.glb", "scale": 1.16, "yaw_deg": 180, "clip_s": 0.6}}"#,
    )
    .expect("valid");

    assert_eq!(def.model, Some(FigureModel { glb: "models/man/Man.glb".into(), scale: 1.16, yaw_deg: 180.0, clip_s: 0.6, coat_tint: false, rig: None }));
}

#[test]
fn a_model_wears_the_persons_coat_only_when_asked_to() {
    let with = |extra: &str| {
        FigureDef::from_json(&format!(
            r#"{{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4,
                "model": {{"glb": "models/man/Man.glb", "scale": 1{extra}}}}}"#
        ))
        .expect("valid")
        .model
        .expect("a model")
    };

    assert!(!with("").coat_tint);
    assert!(with(r#", "coat_tint": true"#).coat_tint);
}

#[test]
fn a_model_without_a_size_or_outside_the_assets_is_refused() {
    let with = |model: &str| {
        FigureDef::from_json(&format!(
            r#"{{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4, "model": {model}}}"#
        ))
    };

    assert!(with(r#"{"glb": "models/man/Man.glb", "scale": 0, "yaw_deg": 0, "clip_s": 0}"#).unwrap_err().contains("scale"));
    assert!(with(r#"{"glb": "../Man.glb", "scale": 1, "yaw_deg": 0, "clip_s": 0}"#).unwrap_err().contains("glb"));
}

#[test]
fn a_standing_figure_holds_its_models_rest_moment_of_the_clip() {
    assert_eq!(clip_time(&a_walker(), 0.0, 1.4, 0.0, 7.3, 2.0), 0.6);
}

#[test]
fn a_walking_figure_plays_its_clip_in_step_with_its_speed() {
    let at_reference_speed = clip_time(&a_walker(), 1.4, 1.4, 0.0, 2.5, 2.0);
    let at_half_speed = clip_time(&a_walker(), 0.7, 1.4, 0.0, 2.5, 2.0);

    assert!((at_reference_speed - 0.5).abs() < 1e-5, "{at_reference_speed}");
    assert!((at_half_speed - 1.25).abs() < 1e-5, "{at_half_speed}");
}

#[test]
fn a_person_is_a_ground_truth_box_standing_on_their_feet() {
    let truth = person_truth("survivor-1", [-3.5, 16.0, 0.5], [0.6, 0.6, 1.8]);

    assert_eq!((truth.id.as_str(), truth.kind.as_str()), ("survivor-1", "person"));
    assert_eq!(truth.min_enu, [-3.8, 15.7, 0.5]);
    assert_eq!(truth.max_enu, [-3.2, 16.3, 2.3]);
}

#[test]
fn the_shipped_figure_wears_a_humanoid_pinned_with_an_open_licence() {
    let figure = FigureDef::from_json(&shipped("behaviour/person.figure.json")).expect("figure");

    let model = figure.model.expect("survivors are human-shaped");
    let pinned = pin(&model.glb).unwrap_or_else(|| panic!("{} is pinned", model.glb));
    assert!(["CC0-1.0", "CC-BY-4.0"].contains(&pinned["license"].as_str().unwrap_or("")), "{pinned}");
}

#[test]
fn the_shipped_cars_are_uncovered_models_pinned_with_an_open_licence() {
    let scene: serde_json::Value = serde_json::from_str(&shipped("scene.json")).expect("scene");

    let cars: Vec<&serde_json::Value> = scene["models"].as_array().expect("models").iter().filter(|m| m["kind"] == "car").collect();
    assert!(!cars.is_empty());
    for car in cars {
        let glb = car["glb"].as_str().expect("glb");
        assert!(!glb.contains("covered"), "{glb}: a car under a tarp is no car to COCO");
        let pinned = pin(glb).unwrap_or_else(|| panic!("{glb} is pinned"));
        assert!(["CC0-1.0", "CC-BY-4.0"].contains(&pinned["license"].as_str().unwrap_or("")), "{pinned}");
    }
}

#[test]
fn a_model_keeps_its_normal_maps_unless_the_manifest_drops_them() {
    let models = |extra: &str| {
        crate::scene_manifest::SceneManifest::from_json(&format!(
            r#"{{"version": 1, "camera": "cameras/rig.camera.json", "environment": {{"hdri": null, "sun_illuminance_lux": 1.0,
                "sun_elevation_deg": 1.0, "sun_azimuth_deg": 1.0, "fog_visibility_m": 1.0}}, "materials": {{}},
                "models": [{{"id": "car-0", "glb": "models/car.glb", "position_enu": [0, 0, 0], "collider": "box"{extra}}}],
                "elements": []}}"#
        ))
        .expect("valid")
        .models
    };

    assert!(models("")[0].normal_maps);
    assert!(!models(r#", "normal_maps": false"#)[0].normal_maps);
}

#[test]
fn the_shipped_cars_drop_the_flake_normal_maps_bevy_cannot_tile() {
    let scene: serde_json::Value = serde_json::from_str(&shipped("scene.json")).expect("scene");

    let cars: Vec<&serde_json::Value> = scene["models"].as_array().expect("models").iter().filter(|m| m["kind"] == "car").collect();
    assert!(cars.iter().all(|car| car["normal_maps"] == false), "{cars:?}");
}
