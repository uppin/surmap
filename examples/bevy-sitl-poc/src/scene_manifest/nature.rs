//! The outdoor parts of a manifest: the weather with its one wind, the fires, and the
//! `vegetation` element's stands — their types, defaults and range checks.

use serde::Deserialize;

use super::{expect_suffix, Element, ManifestError, SceneManifest};

/// Rain, fog and the one wind (`docs/simulation/bevy-simulation.md` § *Weather, wind and fire*).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Weather {
    #[serde(default)]
    pub rain_mm_h: f32,
    pub fog_visibility_m: Option<f32>,
    pub wind: WindDef,
    #[serde(default = "rain_fx")]
    pub rain_fx: String,
    #[serde(default = "wet_roughness")]
    pub wet_roughness: f32,
    #[serde(default = "wet_darkening")]
    pub wet_darkening: f32,
    /// Material keys that look wet while it rains.
    #[serde(default = "wet_materials")]
    pub wet_materials: Vec<String>,
}

/// Meteorological: `from_deg` is where the wind blows from, clockwise from north.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct WindDef {
    pub from_deg: f32,
    pub speed_m_s: f32,
    #[serde(default)]
    pub gust_m_s: f32,
    /// A behaviour tree that changes the wind over time (`set_wind` leaves).
    #[serde(default)]
    pub behaviour: Option<crate::behaviour::Node>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FireEffects {
    #[serde(default = "flames_fx")]
    pub flames: String,
    #[serde(default = "embers_fx")]
    pub embers: String,
    #[serde(default = "smoke_fx")]
    pub smoke: String,
}

impl Default for FireEffects {
    fn default() -> Self {
        Self {
            flames: flames_fx(),
            embers: embers_fx(),
            smoke: smoke_fx(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FireDef {
    pub id: String,
    pub ignition_enu: [f32; 3],
    #[serde(default)]
    pub start_s: f32,
    pub spread_m_s: f32,
    pub max_radius_m: f32,
    #[serde(default = "yes")]
    pub smoke: bool,
    #[serde(default = "head_wind_gain")]
    pub head_wind_gain: f32,
    #[serde(default = "lb_wind_gain")]
    pub lb_wind_gain: f32,
    #[serde(default)]
    pub effects: FireEffects,
}

fn rain_fx() -> String {
    "fx/rain.fx.json".into()
}
fn flames_fx() -> String {
    "fx/flames.fx.json".into()
}
fn embers_fx() -> String {
    "fx/embers.fx.json".into()
}
fn smoke_fx() -> String {
    "fx/smoke.fx.json".into()
}
fn wet_roughness() -> f32 {
    0.6
}
fn wet_materials() -> Vec<String> {
    vec!["ground".into(), "asphalt".into()]
}
fn wet_darkening() -> f32 {
    0.85
}
fn yes() -> bool {
    true
}
fn head_wind_gain() -> f32 {
    0.5
}
fn lb_wind_gain() -> f32 {
    0.25
}

/// A stand of a species over an ENU rectangle (`size_m` east, north), scattered by `seed`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Vegetation {
    pub id: String,
    /// `species/<name>.species.json`.
    pub species: String,
    pub position_enu: [f32; 3],
    pub size_m: [f32; 2],
    pub density_per_100m2: f32,
    pub seed: u64,
}

impl SceneManifest {
    /// Ranges of weather, fires and vegetation, and the kind of file each path names.
    pub(super) fn validate_weather_fire_vegetation(&self) -> Result<(), ManifestError> {
        let invalid = |what: &str| Err(ManifestError::Invalid(what.to_owned()));
        if let Some(weather) = &self.weather {
            if weather.rain_mm_h < 0.0 {
                return invalid("weather rain_mm_h must be >= 0");
            }
            if weather.fog_visibility_m.is_some_and(|v| v <= 0.0) {
                return invalid("weather fog_visibility_m must be > 0");
            }
            if weather.wind.speed_m_s < 0.0 || weather.wind.gust_m_s < 0.0 {
                return invalid("weather wind speed and gust must be >= 0");
            }
            expect_suffix(&weather.rain_fx, ".fx.json")?;
        }
        for fire in &self.fires {
            if fire.spread_m_s <= 0.0 || fire.max_radius_m <= 0.0 || fire.start_s < 0.0 {
                return invalid("fire spread_m_s and max_radius_m must be > 0, start_s >= 0");
            }
            for path in [&fire.effects.flames, &fire.effects.embers, &fire.effects.smoke] {
                expect_suffix(path, ".fx.json")?;
            }
        }
        for element in &self.elements {
            if let Element::Vegetation(stand) = element {
                expect_suffix(&stand.species, ".species.json")?;
                if stand.size_m.iter().any(|v| *v <= 0.0)
                    || !(stand.density_per_100m2 > 0.0 && stand.density_per_100m2 <= 50.0)
                {
                    return invalid("vegetation size_m must be > 0 and density in (0, 50]");
                }
            }
        }
        Ok(())
    }
}
