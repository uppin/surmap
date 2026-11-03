//! Building fires (changeset § *Building fire model*): a fire climbs a building floor by floor,
//! burns each floor out, jumps to neighbours (farther downwind) and is lit by a wildfire's burnt
//! area. Pure and stepped, so the renderer, the behaviour trees and the recorder share one state.
//! Every coefficient comes from `building/fire.json`.

use bevy::math::Vec2;
use serde::Deserialize;

use crate::fire::FireSpec;

mod geometry;

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct FireEffectPaths {
    pub window_flames: String,
    pub smoke: String,
    pub embers: String,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BuildingFireTuning {
    pub climb_s_per_floor: f32,
    pub descend_factor: f32,
    pub floor_burn_s: f32,
    pub ignite_distance_m: f32,
    /// Extra reach downwind, metres per m/s of wind toward the neighbour.
    pub ignite_wind_gain_s: f32,
    pub exposure_s: f32,
    pub effects: FireEffectPaths,
    pub glow_colour: [f32; 3],
    pub glow_intensity: f32,
}

/// One building as the fire sees it: its ENU footprint (counter-clockwise) and floor count.
#[derive(Debug, Clone, PartialEq)]
pub struct Footprint {
    pub id: String,
    pub polygon_enu: Vec<Vec2>,
    pub floors: u32,
}

/// A declared building fire: `building` lit on `floor` at `start_s`.
#[derive(Debug, Clone, PartialEq)]
pub struct Ignition {
    pub building: String,
    pub floor: u32,
    pub start_s: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FloorState {
    Intact,
    Burning,
    Burnt,
}

/// Spacing of the points along a footprint's walls the wildfire's burnt area is tested at.
const WALL_STEP_M: f32 = 1.0;

/// When and where a building caught: floor `floor` at `at_s`.
#[derive(Debug, Clone, Copy, PartialEq)]
struct Lit {
    at_s: f32,
    floor: u32,
}

/// How close building `from` stands to building `to`, and the unit direction between their walls.
#[derive(Debug, Clone, Copy)]
struct Reach {
    gap_m: f32,
    direction: Vec2,
}

pub struct BuildingFires {
    buildings: Vec<Footprint>,
    tuning: BuildingFireTuning,
    declared: Vec<Ignition>,
    lit: Vec<Option<Lit>>,
    /// Seconds each building has been continuously within reach of a burning neighbour.
    exposed_s: Vec<f32>,
    /// `reach[from][to]`.
    reach: Vec<Vec<Reach>>,
    wall_points: Vec<Vec<Vec2>>,
    now_s: f32,
}

fn positive(value: f32, what: &str) -> Result<(), String> {
    if value > 0.0 {
        Ok(())
    } else {
        Err(format!("{what} must be > 0"))
    }
}

impl BuildingFireTuning {
    /// Parse and validate: every duration and distance positive, `descend_factor` ≥ 1, effect
    /// paths `fx/*.fx.json`.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let tuning: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        positive(tuning.climb_s_per_floor, "climb_s_per_floor")?;
        positive(tuning.floor_burn_s, "floor_burn_s")?;
        positive(tuning.ignite_distance_m, "ignite_distance_m")?;
        positive(tuning.exposure_s, "exposure_s")?;
        if tuning.descend_factor < 1.0 {
            return Err("descend_factor must be >= 1".into());
        }
        if tuning.ignite_wind_gain_s < 0.0 || tuning.glow_intensity < 0.0 {
            return Err("ignite_wind_gain_s and glow_intensity must be >= 0".into());
        }
        let effects = &tuning.effects;
        for path in [&effects.window_flames, &effects.smoke, &effects.embers] {
            if !path.starts_with("fx/") || !path.ends_with(".fx.json") || path.contains("..") {
                return Err(format!("effect {path:?} must be an fx/*.fx.json path"));
            }
        }
        Ok(tuning)
    }
}

impl FloorState {
    /// Whether this floor is alight.
    pub fn is_burning(self) -> bool {
        self == Self::Burning
    }
}

impl BuildingFires {
    pub fn new(
        buildings: Vec<Footprint>,
        ignitions: Vec<Ignition>,
        tuning: BuildingFireTuning,
    ) -> Self {
        let reach = buildings
            .iter()
            .map(|from| {
                buildings
                    .iter()
                    .map(|to| {
                        let (a, b) = geometry::closest_points(&from.polygon_enu, &to.polygon_enu);
                        let toward = if a == b {
                            geometry::centroid(&to.polygon_enu)
                                - geometry::centroid(&from.polygon_enu)
                        } else {
                            b - a
                        };
                        Reach {
                            gap_m: a.distance(b),
                            direction: toward.normalize_or_zero(),
                        }
                    })
                    .collect()
            })
            .collect();
        let wall_points = buildings
            .iter()
            .map(|b| geometry::wall_points(&b.polygon_enu, WALL_STEP_M))
            .collect();
        Self {
            lit: vec![None; buildings.len()],
            exposed_s: vec![0.0; buildings.len()],
            reach,
            wall_points,
            buildings,
            tuning,
            declared: ignitions,
            now_s: f32::MIN,
        }
    }

    pub fn buildings(&self) -> &[Footprint] {
        &self.buildings
    }

    fn index(&self, id: &str) -> Option<usize> {
        self.buildings.iter().position(|b| b.id == id)
    }

    /// The time floor `floor` of a building lit at `lit` catches fire.
    fn floor_ignites_s(&self, lit: Lit, floor: u32) -> f32 {
        let climb = self.tuning.climb_s_per_floor;
        if floor >= lit.floor {
            lit.at_s + (floor - lit.floor) as f32 * climb
        } else {
            lit.at_s + (lit.floor - floor) as f32 * climb * self.tuning.descend_factor
        }
    }

    fn state_at(&self, lit: Lit, floor: u32, t_s: f32) -> FloorState {
        let ignites = self.floor_ignites_s(lit, floor);
        if t_s < ignites {
            FloorState::Intact
        } else if t_s < ignites + self.tuning.floor_burn_s {
            FloorState::Burning
        } else {
            FloorState::Burnt
        }
    }

    fn catch(&mut self, building: usize, at_s: f32, floor: u32) {
        if self.lit[building].is_none() {
            let floor = floor.min(self.buildings[building].floors.saturating_sub(1));
            self.lit[building] = Some(Lit { at_s, floor });
        }
    }

    /// The lowest burning floor of building `index` at the current time, if any floor burns.
    fn lowest_burning(&self, index: usize) -> Option<u32> {
        (0..self.buildings[index].floors)
            .find(|&f| self.floor(&self.buildings[index].id, f).is_burning())
    }

    /// Advance to `t_s` by `dt` under `wind_enu` (m/s toward), lighting buildings that a wildfire's
    /// burnt area touches.
    pub fn step(&mut self, t_s: f32, dt: f32, wind_enu: Vec2, wildfires: &[FireSpec]) {
        self.now_s = t_s;
        for ignition in self.declared.clone() {
            if t_s >= ignition.start_s {
                if let Some(index) = self.index(&ignition.building) {
                    self.catch(index, ignition.start_s, ignition.floor);
                }
            }
        }
        for index in 0..self.buildings.len() {
            if self.lit[index].is_some() {
                continue;
            }
            let touched = self.wall_points[index]
                .iter()
                .any(|p| wildfires.iter().any(|fire| fire.burnt(*p, t_s, wind_enu)));
            if touched {
                self.catch(index, t_s, 0);
            }
        }
        self.spread(dt, wind_enu);
    }

    /// A burning building lights an intact neighbour it has stood within reach of for the
    /// exposure time; reach is longer downwind.
    fn spread(&mut self, dt: f32, wind_enu: Vec2) {
        let sources: Vec<(usize, u32)> = (0..self.buildings.len())
            .filter_map(|i| self.lowest_burning(i).map(|floor| (i, floor)))
            .collect();
        for target in 0..self.buildings.len() {
            if self.lit[target].is_some() {
                continue;
            }
            let nearest = sources
                .iter()
                .filter(|(source, _)| {
                    let reach = self.reach[*source][target];
                    let downwind = wind_enu.dot(reach.direction).max(0.0);
                    reach.gap_m
                        <= self.tuning.ignite_distance_m + self.tuning.ignite_wind_gain_s * downwind
                })
                .min_by(|a, b| {
                    self.reach[a.0][target]
                        .gap_m
                        .total_cmp(&self.reach[b.0][target].gap_m)
                });
            match nearest {
                Some((_, floor)) => {
                    self.exposed_s[target] += dt;
                    if self.exposed_s[target] >= self.tuning.exposure_s {
                        self.catch(target, self.now_s, *floor);
                    }
                }
                None => self.exposed_s[target] = 0.0,
            }
        }
    }

    pub fn floor(&self, building: &str, floor: u32) -> FloorState {
        match self.index(building).and_then(|i| self.lit[i]) {
            Some(lit) if floor < self.buildings[self.index(building).unwrap_or(0)].floors => {
                self.state_at(lit, floor, self.now_s)
            }
            _ => FloorState::Intact,
        }
    }

    pub fn ignited_at(&self, building: &str) -> Option<f32> {
        self.index(building)
            .and_then(|i| self.lit[i])
            .map(|lit| lit.at_s)
    }

    /// Floors of `building` that burn now, then those burnt out, in ascending order.
    pub fn burning_and_burnt(&self, building: &str) -> (Vec<u32>, Vec<u32>) {
        let Some(index) = self.index(building) else {
            return (Vec::new(), Vec::new());
        };
        let floors = self.buildings[index].floors;
        let of = |wanted: FloorState| {
            (0..floors)
                .filter(|&f| self.floor(building, f) == wanted)
                .collect()
        };
        (of(FloorState::Burning), of(FloorState::Burnt))
    }

    /// Footprints of buildings with at least one burning floor — n4's `World.burning_areas`.
    pub fn burning_footprints(&self) -> Vec<Vec<Vec2>> {
        (0..self.buildings.len())
            .filter(|&i| self.lowest_burning(i).is_some())
            .map(|i| self.buildings[i].polygon_enu.clone())
            .collect()
    }
}

#[cfg(test)]
mod tests;
