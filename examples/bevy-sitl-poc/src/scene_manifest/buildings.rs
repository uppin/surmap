//! The building layer of a manifest: districts, each building's preset fields and the building
//! fires — their types and the rules `SceneManifest::from_json` enforces. The renderer resolves
//! the presets themselves (`building_style.rs`); here only what the manifest alone can tell.

use serde::Deserialize;

use super::{Building, Element, ManifestError, SceneManifest};
use crate::building_style::{district_path, facade_path, roof_path};

/// A district: a preset (`downtown` or `building/districts/<x>.district.json`) over an ENU
/// rectangle (`position_enu` its centre, `size_m` east, north), drawn with `seed`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct DistrictDef {
    pub id: String,
    pub preset: String,
    pub position_enu: [f32; 3],
    pub size_m: [f32; 2],
    #[serde(default)]
    pub seed: u64,
}

/// A fire lit inside `building` on `floor` at `start_s`, tuned by `tuning`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BuildingFireDef {
    pub id: String,
    pub building: String,
    pub floor: u32,
    #[serde(default)]
    pub start_s: f32,
    #[serde(default = "building_fire_tuning")]
    pub tuning: String,
}

pub(super) fn building_fire_tuning() -> String {
    "building/fire.json".into()
}

impl DistrictDef {
    /// Whether the ENU point lies in the district's rectangle.
    pub fn holds(&self, x: f32, y: f32) -> bool {
        (x - self.position_enu[0]).abs() <= self.size_m[0] / 2.0
            && (y - self.position_enu[1]).abs() <= self.size_m[1] / 2.0
    }
}

fn invalid(what: String) -> ManifestError {
    ManifestError::Invalid(what)
}

impl SceneManifest {
    fn in_a_district(&self, building: &Building) -> bool {
        self.districts
            .iter()
            .any(|d| d.holds(building.position_enu[0], building.position_enu[1]))
    }

    fn validate_building(&self, building: &Building) -> Result<(), ManifestError> {
        let id = &building.id;
        let named = |what: &str, result: Result<String, String>| {
            result
                .map(drop)
                .map_err(|e| invalid(format!("building {id}: {what}: {e}")))
        };
        if let Some(facade) = &building.facade {
            named("facade", facade_path(facade))?;
        }
        if let Some(roof) = &building.roof {
            named("roof", roof_path(roof))?;
        }
        if building.floors == Some(0) {
            return Err(invalid(format!("building {id}: floors must be >= 1")));
        }
        let colours = [building.facade_colour, building.roof_colour, building.tint];
        if colours
            .iter()
            .flatten()
            .flatten()
            .any(|c| !(0.0..=1.0).contains(c))
        {
            return Err(invalid(format!(
                "building {id}: colours must be within 0..1"
            )));
        }
        if building
            .glazing
            .as_ref()
            .and_then(|g| g.window_ratio)
            .is_some_and(|r| !(r > 0.0 && r <= 1.0))
        {
            return Err(invalid(format!(
                "building {id}: window_ratio must be in (0, 1]"
            )));
        }
        let styled =
            !building.material.is_empty() || building.facade.is_some() && building.roof.is_some();
        if !styled && !self.in_a_district(building) {
            return Err(invalid(format!(
                "building {id} is in no district: give it a material, or a facade and a roof"
            )));
        }
        Ok(())
    }

    /// Districts, building presets and building fires: names and paths of their kind, ranges,
    /// and fires that name a building of this manifest and one of its floors.
    pub(super) fn validate_buildings(&self) -> Result<(), ManifestError> {
        let mut seen = std::collections::BTreeSet::new();
        for district in &self.districts {
            if !seen.insert(district.id.as_str()) {
                return Err(ManifestError::DuplicateId(district.id.clone()));
            }
            district_path(&district.preset)
                .map_err(|e| invalid(format!("district {}: {e}", district.id)))?;
            if district.size_m.iter().any(|v| *v <= 0.0) {
                return Err(invalid(format!(
                    "district {}: size_m must be > 0",
                    district.id
                )));
            }
        }
        let buildings: Vec<&Building> = self
            .elements
            .iter()
            .filter_map(|e| {
                if let Element::Building(b) = e {
                    Some(&**b)
                } else {
                    None
                }
            })
            .collect();
        for building in &buildings {
            self.validate_building(building)?;
        }
        for fire in &self.building_fires {
            let target = buildings
                .iter()
                .find(|b| b.id == fire.building)
                .ok_or_else(|| {
                    invalid(format!(
                        "building fire {}: no building {:?}",
                        fire.id, fire.building
                    ))
                })?;
            if target.floors.is_some_and(|floors| fire.floor >= floors) {
                return Err(invalid(format!(
                    "building fire {}: floor {} is not below the building's floors",
                    fire.id, fire.floor
                )));
            }
            if fire.start_s < 0.0 {
                return Err(invalid(format!(
                    "building fire {}: start_s must be >= 0",
                    fire.id
                )));
            }
            super::expect_suffix(&fire.tuning, ".json")?;
            super::validate_asset_path(&fire.tuning)?;
        }
        Ok(())
    }
}
