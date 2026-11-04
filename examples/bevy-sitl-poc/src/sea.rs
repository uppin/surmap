//! Water under boats and ships (docs/simulation/bevy-simulation.md § *Vehicles* → vessels): a sea
//! state from the scenario's wind, and the heave, pitch and roll it gives a vessel of a class.
//! Kinematic, not buoyancy physics — pure and on the simulation clock, so a still at `--at t` and
//! a recording replay identically. Every vessel number lives in its class file.

use std::f32::consts::TAU;

/// The fetch the wind blows over on small, sheltered water (a flooded street, a harbour), m.
const SMALL_WATER_FETCH_M: f32 = 100.0;
/// Fetch-limited wave height per (m/s)²: 0.0016 · √(fetch / g), with g = 9.81 m/s².
const HEIGHT_PER_WIND_SQ_M: f32 = 0.0016 * 3.193;
/// The largest wave height small water raises, m: a flooded street is never a storm sea.
const MAX_WAVE_HEIGHT_M: f32 = 1.0;
/// The waves' period at calm and grows with the wind, s, capped at `MAX_PERIOD_S`.
const BASE_PERIOD_S: f32 = 2.5;
const PERIOD_PER_WIND_M_S: f32 = 0.15;
const MAX_PERIOD_S: f32 = 6.0;
/// Pitch and roll a unit-response vessel takes per metre of wave height, rad.
const PITCH_RAD_PER_M: f32 = 0.2;
const ROLL_RAD_PER_M: f32 = 0.3;
/// The three swells' frequency ratios to the sea's period, and their weights (summing to 1).
const SWELLS: [(f32, f32); 3] = [(1.0, 0.5), (1.37, 0.3), (0.71, 0.2)];

/// The water's state: significant wave height (m) and the waves' period (s).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SeaState {
    pub wave_height_m: f32,
    pub period_s: f32,
}

/// A vessel's motion about its place on the surface: heave (m, up), pitch and roll (rad).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct VesselMotion {
    pub heave_m: f32,
    pub pitch_rad: f32,
    pub roll_rad: f32,
}

/// The sea the wind raises over small, sheltered water (a flooded street, a harbour): calm wind
/// is still water; the height grows with wind speed and is capped for short fetch.
pub fn sea_state(wind_speed_m_s: f32) -> SeaState {
    let wind = wind_speed_m_s.max(0.0);
    let fetch_limited = HEIGHT_PER_WIND_SQ_M * (SMALL_WATER_FETCH_M / 100.0).sqrt() * wind * wind;
    SeaState {
        wave_height_m: fetch_limited.min(MAX_WAVE_HEIGHT_M),
        period_s: (BASE_PERIOD_S + PERIOD_PER_WIND_M_S * wind).min(MAX_PERIOD_S),
    }
}

/// The motion of a vessel whose class answers waves with `wave_response` (≈ 1 for a small boat,
/// ≈ 0.1 for a ship) at `t_s`: three seeded swells from `phase` (per vessel id), heave within the
/// wave height, pitch and roll scaled by the response.
pub fn vessel_motion(sea: SeaState, wave_response: f32, t_s: f32, phase: f32) -> VesselMotion {
    let heave = swell(sea.period_s, t_s, phase, 0.0);
    let pitch = swell(sea.period_s, t_s, phase, 1.0);
    let roll = swell(sea.period_s, t_s, phase, 2.0);
    VesselMotion {
        heave_m: wave_response * sea.wave_height_m / 2.0 * heave,
        pitch_rad: wave_response * PITCH_RAD_PER_M * sea.wave_height_m * pitch,
        roll_rad: wave_response * ROLL_RAD_PER_M * sea.wave_height_m * roll,
    }
}

/// Where a vessel's hull sits, m above the ground: its keel `draft_m` below the water's top, lifted
/// or dropped by the heave.
pub fn hull_height_m(surface_top_m: f32, draft_m: f32, motion: VesselMotion) -> f32 {
    surface_top_m + motion.heave_m - draft_m
}

/// A stable phase for a vessel from its id, in [0, τ): the same vessel rocks the same way every run.
pub fn phase_of(id: &str) -> f32 {
    let hash = id.bytes().fold(0xcbf2_9ce4_8422_2325_u64, |h, b| (h ^ u64::from(b)).wrapping_mul(0x0000_0100_0000_01b3));
    (hash % 10_000) as f32 / 10_000.0 * TAU
}

/// One lane's weighted sum of three sines, within [-1, 1]: lanes differ in their phases, so heave,
/// pitch and roll do not move in step.
fn swell(period_s: f32, t_s: f32, phase: f32, lane: f32) -> f32 {
    let omega = TAU / period_s;
    SWELLS
        .iter()
        .enumerate()
        .map(|(k, &(ratio, weight))| {
            let k = k as f32;
            let offset = phase * (1.0 + 2.0 * k) + lane * (1.7 + 0.9 * k) + k;
            weight * (omega * ratio * t_s + offset).sin()
        })
        .sum()
}

#[cfg(test)]
mod tests;
