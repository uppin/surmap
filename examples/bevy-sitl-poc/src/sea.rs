//! Water under boats and ships (docs/simulation/bevy-simulation.md § *Vehicles* → vessels): a sea
//! state from the scenario's wind, and the heave, pitch and roll it gives a vessel of a class.
//! Kinematic, not buoyancy physics — pure and on the simulation clock, so a still at `--at t` and
//! a recording replay identically. Every vessel number lives in its class file.

#![allow(dead_code)]

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
    // TODO(pr-3): implement
    let _ = wind_speed_m_s;
    todo!("sea_state")
}

/// The motion of a vessel whose class answers waves with `wave_response` (≈ 1 for a small boat,
/// ≈ 0.1 for a ship) at `t_s`: three seeded swells from `phase` (per vessel id), heave within the
/// wave height, pitch and roll scaled by the response.
pub fn vessel_motion(sea: SeaState, wave_response: f32, t_s: f32, phase: f32) -> VesselMotion {
    // TODO(pr-3): implement
    let _ = (sea, wave_response, t_s, phase);
    todo!("vessel_motion")
}

#[cfg(test)]
mod tests;
