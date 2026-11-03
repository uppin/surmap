//! Building presets (changeset § *Everything is runtime JSON*): facades, roofs and districts are
//! files under `assets/building/`, named after Overture's `facade_material` / `roof_material`
//! values. This module parses them and resolves each building's style — its own fields, else
//! its district's weighted draw, else the legacy material.

#![allow(dead_code)]

use bevy::math::Vec2;
use serde::Deserialize;

use crate::scene_manifest::PbrTextureSet;

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

/// `brick` → `building/facades/brick.facade.json`; a path is kept, if it is of that kind.
pub fn facade_path(name_or_path: &str) -> Result<String, String> {
    let _ = name_or_path;
    todo!("facade path")
}

/// `slate` → `building/roofs/slate.roof.json`; a path is kept, if it is of that kind.
pub fn roof_path(name_or_path: &str) -> Result<String, String> {
    let _ = name_or_path;
    todo!("roof path")
}

/// `downtown` → `building/districts/downtown.district.json`; a path is kept, if it is of that kind.
pub fn district_path(name_or_path: &str) -> Result<String, String> {
    let _ = name_or_path;
    todo!("district path")
}

impl FacadePreset {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let _ = text;
        todo!("parse a facade preset")
    }
}

impl RoofPreset {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let _ = text;
        todo!("parse a roof preset")
    }
}

impl DistrictPreset {
    /// Parse and validate: non-empty weighted lists with positive weights, every facade and roof
    /// a known name or a path of its kind, non-empty palettes, `floor_m` > 0.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let _ = text;
        todo!("parse a district preset")
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
    let _ = (id, centre, height_m, own, districts);
    todo!("resolve a building's style")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shipped(path: &str) -> String {
        std::fs::read_to_string(format!("{}/assets/{path}", env!("CARGO_MANIFEST_DIR")))
            .unwrap_or_else(|e| panic!("assets/{path} is shipped: {e}"))
    }

    fn district(name: &str, centre: Vec2, size: Vec2, seed: u64) -> PlacedDistrict {
        let preset = DistrictPreset::from_json(&shipped(&district_path(name).expect("name")))
            .expect("district");
        PlacedDistrict {
            id: name.to_owned(),
            centre,
            size_m: size,
            seed,
            preset,
        }
    }

    #[test]
    fn every_overture_facade_and_roof_has_a_valid_shipped_preset() {
        for name in OVERTURE_FACADES {
            FacadePreset::from_json(&shipped(&facade_path(name).expect("name")))
                .unwrap_or_else(|e| panic!("facade {name}: {e}"));
        }
        for name in OVERTURE_ROOFS {
            RoofPreset::from_json(&shipped(&roof_path(name).expect("name")))
                .unwrap_or_else(|e| panic!("roof {name}: {e}"));
        }
    }

    #[test]
    fn every_shipped_district_is_valid() {
        for name in ["old-town", "downtown", "industrial", "suburban"] {
            DistrictPreset::from_json(&shipped(&district_path(name).expect("name")))
                .unwrap_or_else(|e| panic!("{name}: {e}"));
        }
    }

    #[test]
    fn a_name_is_the_shipped_file_and_a_path_must_be_of_its_kind() {
        assert_eq!(
            facade_path("brick").as_deref(),
            Ok("building/facades/brick.facade.json")
        );
        assert_eq!(
            roof_path("slate").as_deref(),
            Ok("building/roofs/slate.roof.json")
        );
        assert_eq!(
            facade_path("building/facades/red.facade.json").as_deref(),
            Ok("building/facades/red.facade.json")
        );
        assert!(facade_path("building/roofs/slate.roof.json").is_err());
        assert!(
            roof_path("/etc/passwd.roof.json").is_err(),
            "absolute paths are refused"
        );
        assert!(
            facade_path("marble").is_err(),
            "not an Overture facade value"
        );
    }

    #[test]
    fn a_glass_facade_is_a_curtain_wall() {
        let glass =
            FacadePreset::from_json(&shipped("building/facades/glass.facade.json")).expect("glass");

        assert_eq!(glass.glazing.kind, GlazingKind::CurtainWall);
    }

    #[test]
    fn a_district_with_a_zero_weight_or_an_unknown_roof_is_refused() {
        let base = |facades: &str, roofs: &str| {
            format!(
                r#"{{"facades": {facades}, "roofs": {roofs}, "roof_shapes": [["flat", 1]],
                    "facade_colours": [[0.5, 0.5, 0.5]], "roof_colours": [[0.3, 0.3, 0.3]], "floor_m": 3}}"#
            )
        };

        assert!(DistrictPreset::from_json(&base(r#"[["brick", 1]]"#, r#"[["slate", 1]]"#)).is_ok());
        assert!(
            DistrictPreset::from_json(&base(r#"[["brick", 0]]"#, r#"[["slate", 1]]"#)).is_err()
        );
        assert!(
            DistrictPreset::from_json(&base(r#"[["brick", 1]]"#, r#"[["marble", 1]]"#)).is_err()
        );
    }

    #[test]
    fn a_buildings_own_fields_win_over_its_district() {
        let core = [district("downtown", Vec2::ZERO, Vec2::new(100.0, 100.0), 4)];
        let own = OwnStyle {
            facade: Some("brick".into()),
            roof_shape: Some(RoofShape::Gabled),
            floors: Some(5),
            ..OwnStyle::default()
        };

        let style = resolve("b1", Vec2::new(10.0, 10.0), 18.0, &own, &core).expect("style");

        assert_eq!(style.facade, "building/facades/brick.facade.json");
        assert_eq!((style.roof_shape, style.floors), (RoofShape::Gabled, 5));
        assert!(
            style.roof.starts_with("building/roofs/"),
            "the roof still comes from the district"
        );
    }

    #[test]
    fn a_districts_draw_is_deterministic_and_follows_its_weights() {
        let old_town = [district(
            "old-town",
            Vec2::ZERO,
            Vec2::new(1000.0, 1000.0),
            9,
        )];
        let ids: Vec<String> = (0..2000).map(|i| format!("b{i}")).collect();

        let styles: Vec<ResolvedStyle> = ids
            .iter()
            .map(|id| {
                resolve(id, Vec2::ZERO, 10.0, &OwnStyle::default(), &old_town).expect("style")
            })
            .collect();
        let again =
            resolve("b17", Vec2::ZERO, 10.0, &OwnStyle::default(), &old_town).expect("style");

        assert_eq!(again, styles[17]);
        let brick = styles
            .iter()
            .filter(|s| s.facade.ends_with("/brick.facade.json"))
            .count() as f32
            / 2000.0;
        assert!(
            (brick - 0.4).abs() < 0.05,
            "old-town is 40 % brick, drew {brick}"
        );
    }

    #[test]
    fn floors_default_to_the_height_over_the_districts_floor_height() {
        let core = [district("downtown", Vec2::ZERO, Vec2::new(100.0, 100.0), 4)];

        let style = resolve("t", Vec2::ZERO, 36.0, &OwnStyle::default(), &core).expect("style");

        assert_eq!(style.floors, 10, "downtown floors are 3.6 m");
    }

    #[test]
    fn the_later_district_wins_an_overlap_and_outside_every_district_there_is_no_style() {
        let both = [
            district("old-town", Vec2::ZERO, Vec2::new(100.0, 100.0), 1),
            district("downtown", Vec2::new(40.0, 0.0), Vec2::new(40.0, 40.0), 1),
        ];

        let inside_both =
            resolve("b", Vec2::new(40.0, 0.0), 30.0, &OwnStyle::default(), &both).expect("style");
        let outside = resolve(
            "b",
            Vec2::new(500.0, 0.0),
            30.0,
            &OwnStyle::default(),
            &both,
        );

        assert_eq!(
            inside_both.roof_shape,
            RoofShape::Flat,
            "downtown roofs are flat"
        );
        assert!(outside.is_err());
    }
}
