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

mod nature;

pub use nature::{FireDef, Vegetation, Weather, WindDef};

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
    #[serde(default)]
    pub weather: Option<Weather>,
    #[serde(default)]
    pub fires: Vec<FireDef>,
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
    Vegetation(Vegetation),
}

impl Element {
    pub fn id(&self) -> &str {
        match self {
            Self::Box(e) => &e.id,
            Self::CollapsedBuilding(e) => &e.id,
            Self::Building(e) => &e.id,
            Self::Person(e) => &e.id,
            Self::Vegetation(e) => &e.id,
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
            Self::Vegetation(_) => vec![],
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
    /// What the person does over time; standing still when absent.
    #[serde(default)]
    pub behaviour: Option<crate::behaviour::Node>,
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
    /// A value out of its range (e.g. a fire that cannot spread).
    Invalid(String),
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
        let ids = manifest
            .models
            .iter()
            .map(|m| m.id.as_str())
            .chain(manifest.elements.iter().map(Element::id))
            .chain(manifest.fires.iter().map(|f| f.id.as_str()));
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
        let scatters = manifest
            .elements
            .iter()
            .filter(|e| matches!(e, Element::Box(b) if b.scatter.is_some()))
            .count();
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
        manifest.validate_weather_fire_vegetation()?;
        manifest.validate_behaviours()?;
        Ok(manifest)
    }

    /// Each behaviour tree is valid for what it drives: a person's walks, the wind's own veer.
    fn validate_behaviours(&self) -> Result<(), ManifestError> {
        use crate::behaviour::{validate_node, Target};
        let refused = |who: String| move |reason: String| ManifestError::Invalid(format!("{who}: {reason}"));
        if let Some(tree) = self.weather.as_ref().and_then(|w| w.wind.behaviour.as_ref()) {
            validate_node(tree, Target::Wind).map_err(refused("the wind's behaviour".into()))?;
        }
        for element in &self.elements {
            if let Element::Person(person) = element {
                if let Some(tree) = &person.behaviour {
                    validate_node(tree, Target::Object)
                        .map_err(refused(format!("person {} behaviour", person.id)))?;
                }
            }
        }
        Ok(())
    }

    fn referenced_paths(&self) -> Vec<String> {
        let mut paths = vec![self.camera.clone()];
        if let Some(weather) = &self.weather {
            paths.push(weather.rain_fx.clone());
        }
        for fire in &self.fires {
            paths.extend([
                fire.effects.flames.clone(),
                fire.effects.embers.clone(),
                fire.effects.smoke.clone(),
            ]);
        }
        for element in &self.elements {
            if let Element::Vegetation(stand) = element {
                paths.push(stand.species.clone());
            }
        }
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

fn expect_suffix(path: &str, suffix: &str) -> Result<(), ManifestError> {
    if path.ends_with(suffix) {
        Ok(())
    } else {
        Err(ManifestError::BadAssetPath(path.to_owned()))
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
mod tests;
