//! The runtime scene manifest (`assets/scene.json`).
//!
//! The whole scene is declared here — environment, materials, every
//! element and model — and the page fetches it, and every GLB, texture
//! and HDRI it names, at runtime: composing a simulation is a JSON edit,
//! never a rebuild. The engine only knows the element *kinds*.
//! Positions are ENU metres (x east, y north, z up) at the element's
//! base; Bevy is x right, y up, -z north.

#![allow(dead_code)]

use std::collections::BTreeMap;

use bevy::prelude::Transform;
use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SceneManifest {
    pub version: u32,
    /// The stereo camera profile (`cameras/<id>.camera.json`).
    pub camera: String,
    pub environment: Environment,
    #[serde(default)]
    pub materials: BTreeMap<String, PbrTextureSet>,
    #[serde(default)]
    pub models: Vec<ModelInstance>,
    #[serde(default)]
    pub elements: Vec<Element>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Environment {
    pub hdri: Option<String>,
    pub sun_illuminance_lux: f32,
    pub sun_elevation_deg: f32,
    pub sun_azimuth_deg: f32,
    pub fog_visibility_m: f32,
    /// Skybox and image-light brightness (cd/m² per HDRI unit); tune here.
    #[serde(default = "sky_brightness")]
    pub sky_brightness: f32,
    /// One fixed exposure for every camera (the eyes must match).
    #[serde(default = "exposure")]
    pub exposure_ev100: f32,
}

fn sky_brightness() -> f32 {
    15_000.0
}

fn exposure() -> f32 {
    14.0
}

/// A material: textured (a `base_color` map, optional normal/ARM maps)
/// or solid (no maps, `color` and the scalar values only).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PbrTextureSet {
    pub base_color: Option<String>,
    pub normal: Option<String>,
    pub roughness: Option<String>,
    /// Poly Haven ARM map (R occlusion, G roughness, B metalness); when
    /// set it drives both metallic-roughness and occlusion (spec §2.1).
    pub arm: Option<String>,
    #[serde(default = "unit_uv_scale")]
    pub uv_scale: f32,
    /// sRGB colour; multiplies `base_color` when both are set.
    #[serde(default = "white")]
    pub color: [f32; 3],
    #[serde(default = "unit_scale")]
    pub perceptual_roughness: f32,
    #[serde(default)]
    pub metallic: f32,
    #[serde(default = "default_reflectance")]
    pub reflectance: f32,
    #[serde(default)]
    pub clearcoat: f32,
}

fn unit_uv_scale() -> f32 {
    1.0
}

fn white() -> [f32; 3] {
    [1.0, 1.0, 1.0]
}

fn default_reflectance() -> f32 {
    0.5
}

/// One declared piece of the scene; the engine knows only these kinds.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Element {
    Box(BoxElement),
    CollapsedBuilding(CollapsedBuilding),
    Building(Building),
    Person(Person),
}

impl Element {
    pub fn id(&self) -> &str {
        match self {
            Self::Box(e) => &e.id,
            Self::CollapsedBuilding(e) => &e.id,
            Self::Building(e) => &e.id,
            Self::Person(e) => &e.id,
        }
    }

    fn materials(&self) -> Vec<&str> {
        match self {
            Self::Box(e) => {
                let mut keys = vec![e.material.as_str()];
                keys.extend(e.scatter.iter().map(|s| s.material.as_str()));
                keys
            }
            Self::CollapsedBuilding(e) => vec![e.material.as_str()],
            Self::Building(e) => {
                let mut keys = vec![e.material.as_str()];
                keys.extend(e.windows.iter().map(|w| w.material.as_str()));
                keys
            }
            Self::Person(e) => vec![e.coat.as_str(), e.skin.as_str()],
        }
    }
}

/// A box: ground, road, rim, water, pad — `size_m` is (east, north, up).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BoxElement {
    pub id: String,
    pub material: String,
    pub size_m: [f32; 3],
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    /// sRGB multiplier on the material colour.
    pub tint: Option<[f32; 3]>,
    /// Overrides the material's repeats per metre.
    pub uv_scale: Option<f32>,
    #[serde(default)]
    pub collider: bool,
    /// Debris scattered over the box's top (at most one per scene).
    pub scatter: Option<Scatter>,
    /// Ground-truth kind, when a region query may target this box.
    pub ground_truth: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Scatter {
    pub material: String,
    pub density: f32,
}

/// A pancaked building: `slabs` tilted slabs and a rubble fan, laid out
/// by `seed` (spec §4.1).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CollapsedBuilding {
    pub id: String,
    pub material: String,
    /// (east, north) before yaw.
    pub footprint_m: [f32; 2],
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    pub seed: u64,
    #[serde(default = "four")]
    pub slabs: u32,
    #[serde(default = "slab_thickness")]
    pub slab_thickness_m: f32,
    #[serde(default = "rubble_count")]
    pub rubble: u32,
    #[serde(default = "rubble_radius")]
    pub rubble_radius_m: f32,
    pub tint: Option<[f32; 3]>,
}

fn four() -> u32 {
    4
}
fn slab_thickness() -> f32 {
    0.30
}
fn rubble_count() -> u32 {
    25
}
fn rubble_radius() -> f32 {
    4.0
}

/// An intact building with an optional window grid (spec §4.2).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Building {
    pub id: String,
    pub material: String,
    pub size_m: [f32; 3],
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    pub tint: Option<[f32; 3]>,
    pub windows: Option<Windows>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Windows {
    pub material: String,
    #[serde(default = "pane")]
    pub pane_m: [f32; 2],
    #[serde(default = "three")]
    pub bay_m: f32,
    #[serde(default = "three")]
    pub floor_m: f32,
    #[serde(default = "first_row")]
    pub first_row_m: f32,
}

fn pane() -> [f32; 2] {
    [1.4, 1.6]
}
fn three() -> f32 {
    3.0
}
fn first_row() -> f32 {
    4.2
}

/// A survivor at an ENU pose (feet at `position_enu`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Person {
    pub id: String,
    pub position_enu: [f32; 3],
    pub coat: String,
    pub skin: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ColliderKind {
    None,
    Box,
    Trimesh,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct ModelInstance {
    pub id: String,
    pub glb: String,
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    #[serde(default = "unit_scale")]
    pub scale: f32,
    pub collider: ColliderKind,
    #[serde(default)]
    pub ground_truth: bool,
    /// Ground-truth kind (`car`, `collapsed_building`, …); `model` when unnamed.
    #[serde(default = "default_kind")]
    pub kind: String,
}

fn default_kind() -> String {
    "model".into()
}

fn unit_scale() -> f32 {
    1.0
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ManifestError {
    Json(String),
    UnsupportedVersion(u32),
    DuplicateId(String),
    BadAssetPath(String),
    UnknownMaterial(String),
    MoreThanOneScatter,
}

impl SceneManifest {
    /// Parse and validate: version 1, unique model ids, every asset path
    /// relative to `assets/` (no leading `/`, no `..`), models end `.glb` or `.gltf`.
    pub fn from_json(text: &str) -> Result<Self, ManifestError> {
        let manifest: Self =
            serde_json::from_str(text).map_err(|e| ManifestError::Json(e.to_string()))?;
        if manifest.version != 1 {
            return Err(ManifestError::UnsupportedVersion(manifest.version));
        }
        let mut seen = std::collections::BTreeSet::new();
        let ids = manifest.models.iter().map(|m| m.id.as_str()).chain(manifest.elements.iter().map(Element::id));
        for id in ids {
            if !seen.insert(id.to_owned()) {
                return Err(ManifestError::DuplicateId(id.to_owned()));
            }
        }
        for key in manifest.elements.iter().flat_map(Element::materials) {
            if !manifest.materials.contains_key(key) {
                return Err(ManifestError::UnknownMaterial(key.to_owned()));
            }
        }
        let scatters = manifest.elements.iter().filter(|e| matches!(e, Element::Box(b) if b.scatter.is_some())).count();
        if scatters > 1 {
            return Err(ManifestError::MoreThanOneScatter);
        }
        for path in manifest.referenced_paths() {
            validate_asset_path(&path)?;
        }
        if !manifest.camera.ends_with(".camera.json") {
            return Err(ManifestError::BadAssetPath(manifest.camera.clone()));
        }
        for model in &manifest.models {
            if !(model.glb.ends_with(".glb") || model.glb.ends_with(".gltf")) {
                return Err(ManifestError::BadAssetPath(model.glb.clone()));
            }
        }
        Ok(manifest)
    }

    fn referenced_paths(&self) -> Vec<String> {
        let mut paths = vec![self.camera.clone()];
        if let Some(hdri) = &self.environment.hdri {
            paths.push(hdri.clone());
        }
        for material in self.materials.values() {
            paths.extend(material.base_color.clone());
            if let Some(normal) = &material.normal {
                paths.push(normal.clone());
            }
            if let Some(roughness) = &material.roughness {
                paths.push(roughness.clone());
            }
            if let Some(arm) = &material.arm {
                paths.push(arm.clone());
            }
        }
        for model in &self.models {
            paths.push(model.glb.clone());
        }
        paths
    }

    /// Every asset path the manifest references (HDRI, textures, GLBs), sorted, unique.
    pub fn asset_paths(&self) -> Vec<String> {
        self.referenced_paths()
            .into_iter()
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect()
    }
}

fn validate_asset_path(path: &str) -> Result<(), ManifestError> {
    if path.is_empty()
        || path.starts_with('/')
        || path.split('/').any(|part| part == ".." || part.is_empty())
    {
        return Err(ManifestError::BadAssetPath(path.to_string()));
    }
    Ok(())
}

impl ModelInstance {
    /// ENU position → Bevy `(x, z, -y)`; yaw is counter-clockwise from
    /// east about up, which is a rotation about Bevy +y; uniform scale.
    pub fn bevy_transform(&self) -> Transform {
        Transform::from_translation(bevy::math::Vec3::new(
            self.position_enu[0],
            self.position_enu[2],
            -self.position_enu[1],
        ))
        .with_rotation(bevy::math::Quat::from_rotation_y(self.yaw_deg.to_radians()))
        .with_scale(bevy::math::Vec3::splat(self.scale))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use bevy::math::Vec3;

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
        assert!(matches!(&manifest.elements[1], Element::CollapsedBuilding(c) if c.slabs == 4 && c.rubble == 25));
    }

    #[test]
    fn an_element_naming_an_undeclared_material_is_refused() {
        let text = with_elements(r#"[{"kind": "box", "id": "pad", "material": "marble", "size_m": [1, 1, 1], "position_enu": [0, 0, 0]}]"#);

        assert_eq!(SceneManifest::from_json(&text), Err(ManifestError::UnknownMaterial("marble".into())));
    }

    #[test]
    fn an_element_and_a_model_cannot_share_an_id() {
        let text = with_elements(r#"[{"kind": "box", "id": "car-1", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, 0, 0]}]"#)
            .replacen("\"elements\"", "\"models\": [{\"id\": \"car-1\", \"glb\": \"models/car.glb\", \"position_enu\": [0,0,0], \"collider\": \"none\"}], \"elements\"", 1);

        assert_eq!(SceneManifest::from_json(&text), Err(ManifestError::DuplicateId("car-1".into())));
    }

    #[test]
    fn a_scene_scatters_debris_over_one_box_at_most() {
        let scattered = r#"{"kind": "box", "id": "IDX", "material": "concrete", "size_m": [1, 1, 1], "position_enu": [0, 0, 0], "scatter": {"material": "concrete", "density": 28}}"#;
        let text = with_elements(&format!("[{}, {}]", scattered.replace("IDX", "a"), scattered.replace("IDX", "b")));

        assert_eq!(SceneManifest::from_json(&text), Err(ManifestError::MoreThanOneScatter));
    }

    #[test]
    fn a_solid_material_needs_no_texture_and_names_no_asset_file() {
        let manifest = SceneManifest::from_json(&with_elements("[]")).expect("valid");

        assert_eq!(manifest.materials["concrete"].base_color, None);
        assert_eq!(manifest.asset_paths(), vec!["cameras/rig.camera.json"]);
    }


    #[test]
    fn a_scenario_written_by_the_station_store_is_a_valid_manifest() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/fixtures/sim_scenario/wreck-on-the-avenue.json");
        let text = std::fs::read_to_string(path).expect("the station store's scenario fixture");

        let manifest = SceneManifest::from_json(&text).expect("the renderer accepts the store's scenario");

        assert!(manifest.models.iter().any(|m| m.glb == "library/sketchfab/3f1c0a/model.glb"));
    }

}
