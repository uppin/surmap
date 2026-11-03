//! Building presets (docs/simulation/bevy-simulation.md § *Preset files*): facades, roofs and
//! districts are files under `assets/building/`, named after Overture's `facade_material` /
//! `roof_material` values. This module parses them and resolves each building's style — its own
//! fields, else its district's weighted draw, else the legacy material.

use bevy::math::Vec2;
use serde::Deserialize;

use crate::scene_manifest::PbrTextureSet;
use crate::world::Seeded;

/// Overture's `facade_material` values; each has a shipped `building/facades/<v>.facade.json`.
pub const OVERTURE_FACADES: [&str; 11] = [
    "brick",
    "cement_block",
    "clay",
    "concrete",
    "glass",
    "metal",
    "plaster",
    "plastic",
    "stone",
    "timber",
    "wood",
];

/// Overture's `roof_material` values; each has a shipped `building/roofs/<v>.roof.json`.
pub const OVERTURE_ROOFS: [&str; 14] = [
    "concrete",
    "copper",
    "eternit",
    "glass",
    "grass",
    "gravel",
    "metal",
    "plastic",
    "roof_tiles",
    "slate",
    "solar_panels",
    "tar_paper",
    "thatch",
    "wood",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GlazingKind {
    None,
    Punched,
    CurtainWall,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RoofShape {
    Flat,
    Gabled,
    Hipped,
    Pyramidal,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Glazing {
    pub kind: GlazingKind,
    #[serde(default)]
    pub window_ratio: Option<f32>,
    #[serde(default)]
    pub pane_m: Option<[f32; 2]>,
    #[serde(default)]
    pub bay_m: Option<f32>,
    #[serde(default)]
    pub mullion_m: Option<[f32; 2]>,
    #[serde(default)]
    pub glass: Option<PbrTextureSet>,
    #[serde(default)]
    pub frame: Option<PbrTextureSet>,
    #[serde(default)]
    pub mullion: Option<PbrTextureSet>,
    /// Punched windows: how far a pane sits behind the wall face, m.
    #[serde(default)]
    pub recess_m: Option<f32>,
    /// Punched windows: the frame's border around a pane, m.
    #[serde(default)]
    pub frame_m: Option<f32>,
    /// Curtain walls: the opaque band at each slab, m, and its material.
    #[serde(default)]
    pub spandrel_m: Option<f32>,
    #[serde(default)]
    pub spandrel: Option<PbrTextureSet>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FacadePreset {
    pub material: PbrTextureSet,
    #[serde(default)]
    pub colourable: bool,
    pub glazing: Glazing,
    pub burnt: PbrTextureSet,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct RoofPreset {
    pub material: PbrTextureSet,
    #[serde(default)]
    pub colourable: bool,
    pub burnt: PbrTextureSet,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct DistrictPreset {
    /// `[[facade name or path, weight], …]`.
    pub facades: Vec<(String, f32)>,
    pub roofs: Vec<(String, f32)>,
    pub roof_shapes: Vec<(RoofShape, f32)>,
    pub facade_colours: Vec<[f32; 3]>,
    pub roof_colours: Vec<[f32; 3]>,
    pub floor_m: f32,
    /// Glazed share of a facade cell, over the facade preset's own.
    #[serde(default)]
    pub window_ratio: Option<f32>,
    /// Glazed share of the ground floor's cell (a shopfront).
    #[serde(default)]
    pub ground_window_ratio: Option<f32>,
}

/// A building's style after resolution: preset files by path, never names.
#[derive(Debug, Clone, PartialEq)]
pub struct ResolvedStyle {
    pub facade: String,
    pub roof: String,
    pub roof_shape: RoofShape,
    pub facade_colour: Option<[f32; 3]>,
    pub roof_colour: Option<[f32; 3]>,
    pub floors: u32,
    /// `None`: the facade preset's default glazing.
    pub glazing: Option<Glazing>,
    /// The district's window ratio (over the facade's default), if it names one.
    pub window_ratio: Option<f32>,
    /// The district's ground-floor (shopfront) window ratio, if it names one.
    pub ground_window_ratio: Option<f32>,
}

/// What a building declares itself (each `None` falls to its district).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct OwnStyle {
    pub facade: Option<String>,
    pub roof: Option<String>,
    pub roof_shape: Option<RoofShape>,
    pub facade_colour: Option<[f32; 3]>,
    pub roof_colour: Option<[f32; 3]>,
    pub floors: Option<u32>,
    pub glazing: Option<Glazing>,
}

/// A district rectangle (ENU, centre + size) with its loaded preset.
#[derive(Debug, Clone, PartialEq)]
pub struct PlacedDistrict {
    pub id: String,
    pub centre: Vec2,
    pub size_m: Vec2,
    pub seed: u64,
    pub preset: DistrictPreset,
}

/// The districts the station ships; any other district is a file path.
pub const SHIPPED_DISTRICTS: [&str; 4] = ["old-town", "downtown", "industrial", "suburban"];

/// Floor height a style with no district falls back to when a building names no `floors`.
pub const DEFAULT_FLOOR_M: f32 = 3.0;

/// A preset reference: a bare name from `shipped`, or a path `building/<folder>/*.<suffix>`.
fn preset_path(
    value: &str,
    shipped: &[&str],
    folder: &str,
    suffix: &str,
    what: &str,
) -> Result<String, String> {
    if !value.contains('/') {
        return if shipped.contains(&value) {
            Ok(format!("building/{folder}/{value}.{suffix}"))
        } else {
            Err(format!(
                "{what} {value:?} is not a shipped name or a building/{folder}/*.{suffix} path"
            ))
        };
    }
    let prefix = format!("building/{folder}/");
    let clean = !value.starts_with('/')
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "..");
    if clean && value.starts_with(&prefix) && value.ends_with(&format!(".{suffix}")) {
        Ok(value.to_owned())
    } else {
        Err(format!(
            "{what} {value:?} must be a building/{folder}/*.{suffix} path"
        ))
    }
}

/// `brick` → `building/facades/brick.facade.json`; a path is kept, if it is of that kind.
pub fn facade_path(name_or_path: &str) -> Result<String, String> {
    preset_path(
        name_or_path,
        &OVERTURE_FACADES,
        "facades",
        "facade.json",
        "facade",
    )
}

/// `slate` → `building/roofs/slate.roof.json`; a path is kept, if it is of that kind.
pub fn roof_path(name_or_path: &str) -> Result<String, String> {
    preset_path(name_or_path, &OVERTURE_ROOFS, "roofs", "roof.json", "roof")
}

/// `downtown` → `building/districts/downtown.district.json`; a path is kept, if it is of that kind.
pub fn district_path(name_or_path: &str) -> Result<String, String> {
    preset_path(
        name_or_path,
        &SHIPPED_DISTRICTS,
        "districts",
        "district.json",
        "district",
    )
}

fn positive(value: Option<f32>, what: &str) -> Result<f32, String> {
    match value {
        Some(v) if v > 0.0 => Ok(v),
        _ => Err(format!("{what} must be > 0")),
    }
}

impl Glazing {
    /// Each kind carries what it draws with.
    pub fn validate(&self, what: &str) -> Result<(), String> {
        match self.kind {
            GlazingKind::None => Ok(()),
            GlazingKind::Punched => {
                let ratio = positive(self.window_ratio, &format!("{what} window_ratio"))?;
                if ratio > 1.0 {
                    return Err(format!("{what} window_ratio must be <= 1"));
                }
                positive(self.bay_m, &format!("{what} bay_m"))?;
                if self.pane_m.is_none() || self.glass.is_none() || self.frame.is_none() {
                    return Err(format!(
                        "{what}: punched glazing needs pane_m, glass and frame"
                    ));
                }
                Ok(())
            }
            GlazingKind::CurtainWall => {
                if self.mullion_m.is_none_or(|m| m[0] <= 0.0 || m[1] <= 0.0) {
                    return Err(format!("{what}: a curtain wall needs mullion_m > 0"));
                }
                positive(self.bay_m, &format!("{what} bay_m"))?;
                positive(self.spandrel_m, &format!("{what} spandrel_m"))?;
                if self.glass.is_none() || self.mullion.is_none() || self.spandrel.is_none() {
                    return Err(format!(
                        "{what}: a curtain wall needs glass, mullion and spandrel"
                    ));
                }
                Ok(())
            }
        }
    }
}

impl FacadePreset {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let preset: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        preset.glazing.validate("facade glazing")?;
        Ok(preset)
    }
}

impl RoofPreset {
    pub fn from_json(text: &str) -> Result<Self, String> {
        serde_json::from_str(text).map_err(|e| e.to_string())
    }
}

fn weighted<T>(list: &[(T, f32)], what: &str) -> Result<(), String> {
    if list.is_empty() {
        return Err(format!("{what} must not be empty"));
    }
    if list.iter().any(|(_, w)| w.is_nan() || *w <= 0.0) {
        return Err(format!("{what} weights must be > 0"));
    }
    Ok(())
}

impl DistrictPreset {
    /// Parse and validate: non-empty weighted lists with positive weights, every facade and roof
    /// a known name or a path of its kind, non-empty palettes, `floor_m` > 0.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let preset: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        weighted(&preset.facades, "facades")?;
        weighted(&preset.roofs, "roofs")?;
        weighted(&preset.roof_shapes, "roof_shapes")?;
        for (name, _) in &preset.facades {
            facade_path(name)?;
        }
        for (name, _) in &preset.roofs {
            roof_path(name)?;
        }
        if preset.facade_colours.is_empty() || preset.roof_colours.is_empty() {
            return Err("colour palettes must not be empty".into());
        }
        if preset.floor_m.is_nan() || preset.floor_m <= 0.0 {
            return Err("floor_m must be > 0".into());
        }
        for ratio in [preset.window_ratio, preset.ground_window_ratio]
            .into_iter()
            .flatten()
        {
            if !(ratio > 0.0 && ratio <= 1.0) {
                return Err("window ratios must be in (0, 1]".into());
            }
        }
        Ok(preset)
    }
}

/// FNV-1a over the building's id, mixed with the district's seed: one stable stream per building.
fn stream_seed(id: &str, seed: u64) -> u64 {
    let hash = id.bytes().fold(0xcbf2_9ce4_8422_2325_u64, |h, b| {
        (h ^ u64::from(b)).wrapping_mul(0x0100_0000_01b3)
    });
    hash ^ seed.rotate_left(32)
}

fn pick<'a, T>(list: &'a [(T, f32)], rng: &mut Seeded) -> &'a T {
    let total: f32 = list.iter().map(|(_, w)| w).sum();
    let mut at = rng.range(0.0, total);
    for (item, weight) in list {
        if at < *weight {
            return item;
        }
        at -= weight;
    }
    &list[list.len() - 1].0
}

fn pick_colour(palette: &[[f32; 3]], rng: &mut Seeded) -> [f32; 3] {
    palette[(rng.next_u64() % palette.len() as u64) as usize]
}

impl PlacedDistrict {
    fn holds(&self, point: Vec2) -> bool {
        let half = self.size_m / 2.0;
        let rel = (point - self.centre).abs();
        rel.x <= half.x && rel.y <= half.y
    }
}

/// The style of building `id` at `centre`, `height_m` tall: its own fields, else the last district
/// holding `centre` (a draw weighted by the district's lists, hashed from its seed and `id`), else
/// `Err` naming the missing part (the caller falls back to the legacy material).
pub fn resolve(
    id: &str,
    centre: Vec2,
    height_m: f32,
    own: &OwnStyle,
    districts: &[PlacedDistrict],
) -> Result<ResolvedStyle, String> {
    let district = districts.iter().rev().find(|d| d.holds(centre));
    let Some(district) = district else {
        let (Some(facade), Some(roof)) = (&own.facade, &own.roof) else {
            return Err(format!(
                "building {id} is in no district and names no facade and roof"
            ));
        };
        return Ok(ResolvedStyle {
            facade: facade_path(facade)?,
            roof: roof_path(roof)?,
            roof_shape: own.roof_shape.unwrap_or(RoofShape::Flat),
            facade_colour: own.facade_colour,
            roof_colour: own.roof_colour,
            floors: own
                .floors
                .unwrap_or_else(|| floors_for(height_m, DEFAULT_FLOOR_M)),
            glazing: own.glazing.clone(),
            window_ratio: None,
            ground_window_ratio: None,
        });
    };
    let preset = &district.preset;
    let mut rng = Seeded::new(stream_seed(id, district.seed));
    let drawn_facade = pick(&preset.facades, &mut rng);
    let drawn_roof = pick(&preset.roofs, &mut rng);
    let drawn_shape = *pick(&preset.roof_shapes, &mut rng);
    let drawn_facade_colour = pick_colour(&preset.facade_colours, &mut rng);
    let drawn_roof_colour = pick_colour(&preset.roof_colours, &mut rng);
    Ok(ResolvedStyle {
        facade: facade_path(own.facade.as_deref().unwrap_or(drawn_facade))?,
        roof: roof_path(own.roof.as_deref().unwrap_or(drawn_roof))?,
        roof_shape: own.roof_shape.unwrap_or(drawn_shape),
        facade_colour: Some(own.facade_colour.unwrap_or(drawn_facade_colour)),
        roof_colour: Some(own.roof_colour.unwrap_or(drawn_roof_colour)),
        floors: own
            .floors
            .unwrap_or_else(|| floors_for(height_m, preset.floor_m)),
        glazing: own.glazing.clone(),
        window_ratio: preset.window_ratio,
        ground_window_ratio: preset.ground_window_ratio,
    })
}

/// Whole floors of `floor_m` in `height_m`, at least one.
pub fn floors_for(height_m: f32, floor_m: f32) -> u32 {
    ((height_m / floor_m + 1e-3).floor() as u32).max(1)
}

#[cfg(test)]
mod tests;
