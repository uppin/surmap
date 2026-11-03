//! The runtime scene manifest (`assets/scene.json`).
//!
//! The page fetches it, and every GLB, texture and HDRI it names, at
//! runtime, so new content is a file drop plus a manifest edit — the
//! WASM is never rebuilt for it. Positions are ENU metres
//! (x east, y north, z up); Bevy is x right, y up, -z north.

#![allow(dead_code)]

use std::collections::BTreeMap;

use bevy::prelude::Transform;
use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SceneManifest {
    pub version: u32,
    pub environment: Environment,
    #[serde(default)]
    pub materials: BTreeMap<String, PbrTextureSet>,
    #[serde(default)]
    pub models: Vec<ModelInstance>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Environment {
    pub hdri: Option<String>,
    pub sun_illuminance_lux: f32,
    pub sun_elevation_deg: f32,
    pub sun_azimuth_deg: f32,
    pub fog_visibility_m: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PbrTextureSet {
    pub base_color: String,
    pub normal: Option<String>,
    pub roughness: Option<String>,
    #[serde(default = "unit_uv_scale")]
    pub uv_scale: f32,
}

fn unit_uv_scale() -> f32 {
    1.0
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
        for model in &manifest.models {
            if !seen.insert(model.id.clone()) {
                return Err(ManifestError::DuplicateId(model.id.clone()));
            }
        }
        for path in manifest.referenced_paths() {
            validate_asset_path(&path)?;
        }
        for model in &manifest.models {
            if !(model.glb.ends_with(".glb") || model.glb.ends_with(".gltf")) {
                return Err(ManifestError::BadAssetPath(model.glb.clone()));
            }
        }
        Ok(manifest)
    }

    fn referenced_paths(&self) -> Vec<String> {
        let mut paths = Vec::new();
        if let Some(hdri) = &self.environment.hdri {
            paths.push(hdri.clone());
        }
        for material in self.materials.values() {
            paths.push(material.base_color.clone());
            if let Some(normal) = &material.normal {
                paths.push(normal.clone());
            }
            if let Some(roughness) = &material.roughness {
                paths.push(roughness.clone());
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
        "environment": {"hdri": "hdri/sky.hdr", "sun_illuminance_lux": 100000.0,
                        "sun_elevation_deg": 38.0, "sun_azimuth_deg": 135.0,
                        "fog_visibility_m": 450.0},
        "materials": {"asphalt": {"base_color": "textures/asphalt_color.jpg",
                                  "normal": "textures/asphalt_normal.png", "uv_scale": 0.25}},
        "models": [
            {"id": "car-1", "glb": "models/car.glb", "position_enu": [3.0, 12.0, 0.0],
             "yaw_deg": 90.0, "collider": "box", "ground_truth": true},
            {"id": "rubble-1", "glb": "models/rubble.glb", "position_enu": [-4.0, 30.0, 0.0],
             "scale": 2.0, "collider": "trimesh"}
        ]
    }"#;

    fn with_models(models: &str) -> String {
        format!(
            r#"{{"version": 1, "environment": {{"hdri": null, "sun_illuminance_lux": 1.0,
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
    fn a_manifest_names_every_asset_it_needs_once() {
        let manifest = a_valid_manifest();

        assert_eq!(
            manifest.asset_paths(),
            vec![
                "hdri/sky.hdr",
                "models/car.glb",
                "models/rubble.glb",
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
}
