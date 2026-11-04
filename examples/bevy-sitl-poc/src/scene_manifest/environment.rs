//! The light and the surfaces of a manifest: the environment (HDRI, sun, fog, exposure) and the
//! PBR materials every element names by key.

use serde::Deserialize;

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
    #[serde(default = "crate::scene_manifest::instances::unit_scale")]
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
