//! Declarative effect and species definitions (`assets/fx/*.fx.json`,
//! `assets/species/*.species.json`): every visual number of weather, fire and vegetation lives in
//! these runtime files, never in Rust.

#![allow(dead_code)]

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::reflect::TypePath;
use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    #[default]
    Quad,
    SoftDisc,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Blend {
    Additive,
    Alpha,
}

/// One colour stop: position 0..1 over the lifetime, sRGB colour, HDR intensity, alpha.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ColourStop(pub f32, pub [f32; 3], pub f32, pub f32);

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Motion {
    /// Initial upward speed, m/s.
    pub up: f32,
    /// Fraction of the wind velocity added to the particle's.
    pub wind_coupling: f32,
    /// Vertical acceleration, m/s² (negative falls).
    #[serde(default)]
    pub gravity: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Spawn {
    PerMetre(f32),
    PerSecond(f32),
    /// Per second for every mm/h of rain (rain only).
    PerMmH(f32),
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FxDef {
    pub colour_gradient: Vec<ColourStop>,
    pub size_m: [f32; 2],
    pub lifetime_s: [f32; 2],
    pub motion: Motion,
    pub blend: Blend,
    pub spawn: Spawn,
    pub max_particles: u32,
    /// Streak length over width, along the velocity; 1 is a camera-facing quad.
    #[serde(default = "one")]
    pub stretch: f32,
    /// Side of the box of air around the camera a weather effect fills (rain).
    #[serde(default)]
    pub box_m: Option<f32>,
    /// 0 leaves each particle a rectangle, 1 makes it an ellipse (flames, embers, smoke).
    #[serde(default)]
    pub round: f32,
    /// `soft_disc`: a radial alpha falloff from a small generated texture (flames, smoke).
    #[serde(default)]
    pub shape: Shape,
    /// Soft discs: 0 is a hard edge, 1 a gaussian-like falloff from the centre.
    #[serde(default = "half")]
    pub softness: f32,
    /// Fire effects: one emitter per this many metres of perimeter.
    #[serde(default = "two")]
    pub emitter_spacing_m: f32,
    /// Fire effects: emitters are re-placed on the front every this many seconds.
    #[serde(default = "half")]
    pub refresh_s: f32,
    /// The scorched ground a fire leaves (read from the fire's flames effect).
    #[serde(default)]
    pub ground: Option<GroundDef>,
    /// The glow a fire casts on its surroundings (read from the fire's flames effect).
    #[serde(default)]
    pub light: Option<LightDef>,
}

/// Burnt ground: a flat mesh above the terrain, its outer rim glowing with the front.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct GroundDef {
    pub height_m: f32,
    pub colour: [f32; 3],
    pub roughness: f32,
    pub glow_width_m: f32,
    pub glow_colour: [f32; 3],
    pub glow_intensity: f32,
}

/// One point light per fire at the perimeter centroid.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct LightDef {
    pub colour: [f32; 3],
    pub height_m: f32,
    /// Lumens per metre of perimeter.
    pub lumens_per_m: f32,
    pub range_m: f32,
}

fn two() -> f32 {
    2.0
}

fn half() -> f32 {
    0.5
}

fn one() -> f32 {
    1.0
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Generator {
    Pine,
    Grass,
}

/// Multipliers on Feronia's wind parameters for one species (stiff trunks sway less).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct WindDamping {
    pub strength: f32,
    pub micro_strength: f32,
    pub s_curve_strength: f32,
    pub bop_strength: f32,
    pub twist_strength: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct SpeciesDef {
    pub generator: Generator,
    /// sRGB stops the generator's vertex colours sample (bark first for pines).
    pub palette: Vec<[f32; 3]>,
    pub burnt_palette: Vec<[f32; 3]>,
    pub height_m: [f32; 2],
    pub wind_damping: WindDamping,
    pub lod_distance_m: f32,
    /// Generator instances per unit of the stand's `density_per_100m2` (grass clumps are tiny).
    #[serde(default = "one")]
    pub plants_per_unit: f32,
}

impl FxDef {
    /// Parse and validate: at least two stops in 0..=1, ascending; sizes, lifetimes and the
    /// particle budget positive; lifetime min ≤ max.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let fx: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        let stops = &fx.colour_gradient;
        if stops.len() < 2 {
            return Err("colour_gradient needs at least two stops".into());
        }
        if stops.iter().any(|s| !(0.0..=1.0).contains(&s.0)) {
            return Err("colour_gradient positions must lie in 0..=1".into());
        }
        if stops.windows(2).any(|w| w[0].0 >= w[1].0) {
            return Err("colour_gradient positions must ascend".into());
        }
        if fx.size_m.iter().any(|v| *v <= 0.0) {
            return Err("size_m must be positive".into());
        }
        if fx.lifetime_s.iter().any(|v| *v <= 0.0) || fx.lifetime_s[0] > fx.lifetime_s[1] {
            return Err("lifetime_s must be positive with min <= max".into());
        }
        let rate = match fx.spawn {
            Spawn::PerMetre(v) | Spawn::PerSecond(v) | Spawn::PerMmH(v) => v,
        };
        if rate <= 0.0 || fx.max_particles == 0 || fx.stretch <= 0.0 {
            return Err("spawn rate, max_particles and stretch must be positive".into());
        }
        if !(0.0..=1.0).contains(&fx.softness) {
            return Err("softness must lie in 0..=1".into());
        }
        if fx.emitter_spacing_m <= 0.0 || fx.refresh_s <= 0.0 {
            return Err("emitter_spacing_m and refresh_s must be positive".into());
        }
        Ok(fx)
    }
}

impl SpeciesDef {
    /// Parse and validate: a non-empty palette, heights 0 < min ≤ max, a positive LOD distance.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let species: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if species.palette.is_empty() || species.burnt_palette.is_empty() {
            return Err("palette and burnt_palette must not be empty".into());
        }
        let [min, max] = species.height_m;
        if min <= 0.0 || min > max {
            return Err("height_m must satisfy 0 < min <= max".into());
        }
        if species.lod_distance_m <= 0.0 {
            return Err("lod_distance_m must be positive".into());
        }
        Ok(species)
    }
}

/// A validated effect, loaded like any asset (`fx/<name>.fx.json`).
#[derive(Asset, TypePath, Debug)]
pub struct FxAsset(pub FxDef);

/// A validated species, loaded like any asset (`species/<name>.species.json`).
#[derive(Asset, TypePath, Debug)]
pub struct SpeciesAsset(pub SpeciesDef);

async fn read_text(reader: &mut dyn Reader) -> Result<String, std::io::Error> {
    let mut bytes = Vec::new();
    reader.read_to_end(&mut bytes).await?;
    String::from_utf8(bytes).map_err(std::io::Error::other)
}

#[derive(Default, TypePath)]
pub struct FxLoader;

impl AssetLoader for FxLoader {
    type Asset = FxAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(&self, reader: &mut dyn Reader, _: &(), _: &mut LoadContext<'_>) -> Result<FxAsset, std::io::Error> {
        FxDef::from_json(&read_text(reader).await?).map(FxAsset).map_err(std::io::Error::other)
    }

    fn extensions(&self) -> &[&str] {
        &["fx.json"]
    }
}

#[derive(Default, TypePath)]
pub struct SpeciesLoader;

impl AssetLoader for SpeciesLoader {
    type Asset = SpeciesAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(&self, reader: &mut dyn Reader, _: &(), _: &mut LoadContext<'_>) -> Result<SpeciesAsset, std::io::Error> {
        SpeciesDef::from_json(&read_text(reader).await?).map(SpeciesAsset).map_err(std::io::Error::other)
    }

    fn extensions(&self) -> &[&str] {
        &["species.json"]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shipped(path: &str) -> String {
        std::fs::read_to_string(format!("{}/assets/{path}", env!("CARGO_MANIFEST_DIR")))
            .unwrap_or_else(|e| panic!("assets/{path} is shipped: {e}"))
    }

    #[test]
    fn every_shipped_effect_is_a_valid_definition() {
        for name in ["flames", "embers", "smoke", "rain"] {
            FxDef::from_json(&shipped(&format!("fx/{name}.fx.json")))
                .unwrap_or_else(|e| panic!("{name}: {e}"));
        }
    }

    #[test]
    fn flames_are_additive_and_lean_with_the_wind_while_smoke_is_alpha_blended_and_drifts() {
        let flames = FxDef::from_json(&shipped("fx/flames.fx.json")).expect("flames");
        let smoke = FxDef::from_json(&shipped("fx/smoke.fx.json")).expect("smoke");

        assert_eq!((flames.blend, smoke.blend), (Blend::Additive, Blend::Alpha));
        assert!(
            flames.motion.wind_coupling > 0.0
                && smoke.motion.wind_coupling >= flames.motion.wind_coupling
        );
    }

    #[test]
    fn every_shipped_species_is_a_valid_definition() {
        for name in ["pine", "dry_grass"] {
            SpeciesDef::from_json(&shipped(&format!("species/{name}.species.json")))
                .unwrap_or_else(|e| panic!("{name}: {e}"));
        }
    }

    #[test]
    fn flames_and_smoke_are_soft_discs_and_embers_the_least_soft() {
        let load = |n: &str| FxDef::from_json(&shipped(&format!("fx/{n}.fx.json"))).expect(n);
        let (flames, smoke, embers) = (load("flames"), load("smoke"), load("embers"));

        assert!([&flames, &smoke, &embers].iter().all(|f| f.shape == Shape::SoftDisc));
        assert!(embers.softness < flames.softness && flames.softness < smoke.softness);
    }

    #[test]
    fn a_softness_outside_zero_to_one_is_refused() {
        let text = r#"{"colour_gradient": [[0.0, [1,1,1], 1, 1], [1.0, [1,1,1], 1, 0]],
            "size_m": [1, 2], "lifetime_s": [1, 2], "motion": {"up": 1, "wind_coupling": 0.5},
            "blend": "alpha", "spawn": {"per_second": 10}, "max_particles": 100,
            "shape": "soft_disc", "softness": 1.5}"#;

        assert!(FxDef::from_json(text).is_err());
    }

    #[test]
    fn a_gradient_out_of_order_is_refused() {
        let text = r#"{"colour_gradient": [[0.8, [1,1,1], 1, 1], [0.2, [1,1,1], 1, 0]],
            "size_m": [1, 2], "lifetime_s": [1, 2], "motion": {"up": 1, "wind_coupling": 0.5},
            "blend": "alpha", "spawn": {"per_second": 10}, "max_particles": 100}"#;

        assert!(FxDef::from_json(text).is_err());
    }

    #[test]
    fn a_species_taller_at_its_minimum_than_its_maximum_is_refused() {
        let text = r#"{"generator": "pine", "palette": [[0.4,0.3,0.2]], "burnt_palette": [[0.1,0.1,0.1]],
            "height_m": [15, 9], "lod_distance_m": 40,
            "wind_damping": {"strength": 0.4, "micro_strength": 0.65, "s_curve_strength": 0.45,
                             "bop_strength": 0.3, "twist_strength": 0.4}}"#;

        assert!(SpeciesDef::from_json(text).is_err());
    }
}
