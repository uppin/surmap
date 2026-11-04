//! Trackpad PTZ for the chase view: two-finger scroll orbits the camera around
//! the drone (pan/tilt), pinch zooms it. The drone stays centred and keyboard
//! flight is untouched; with no input the view is the chase view it replaces.

use bevy::input::gestures::PinchGesture;
use bevy::input::mouse::{MouseScrollUnit, MouseWheel};
use bevy::prelude::*;

/// How far the view may dolly in and out, metres from the drone.
pub const MIN_DISTANCE_M: f32 = 3.0;
pub const MAX_DISTANCE_M: f32 = 40.0;

/// The chase offset this replaces, in the drone's frame (+z behind it).
const CHASE_OFFSET: Vec3 = Vec3::new(5.0, 2.6, 7.5);
/// Orbit angle per pixel of two-finger scroll.
const SCROLL_RAD_PER_PX: f32 = 0.004;

/// Orbit state of the chase view, relative to the drone's facing.
#[derive(Resource, Debug, Clone, Copy, PartialEq)]
pub struct ViewOrbit {
    /// Pan: orbit angle around the drone, radians; 0 is dead behind it.
    pub yaw_rad: f32,
    /// Tilt: orbit elevation above the horizon, radians.
    pub pitch_rad: f32,
    /// Zoom: distance from the drone, metres.
    pub distance_m: f32,
}

impl Default for ViewOrbit {
    fn default() -> Self {
        Self {
            yaw_rad: CHASE_OFFSET.x.atan2(CHASE_OFFSET.z),
            pitch_rad: (CHASE_OFFSET.y / CHASE_OFFSET.length()).asin(),
            distance_m: CHASE_OFFSET.length(),
        }
    }
}

impl ViewOrbit {
    /// Two-finger scroll, in pixels: horizontal pans, vertical tilts.
    pub fn on_scroll(&mut self, dx_px: f32, dy_px: f32) {
        self.yaw_rad = (self.yaw_rad - dx_px * SCROLL_RAD_PER_PX).rem_euclid(std::f32::consts::TAU);
        self.pitch_rad =
            (self.pitch_rad + dy_px * SCROLL_RAD_PER_PX).clamp(0.0, std::f32::consts::FRAC_PI_2);
    }

    /// Pinch gesture: positive delta magnifies (zooms in).
    pub fn on_pinch(&mut self, delta: f32) {
        self.distance_m = (self.distance_m * (-delta).exp()).clamp(MIN_DISTANCE_M, MAX_DISTANCE_M);
    }

    /// The camera offset from the drone, in world space.
    pub fn offset(&self, facing: Quat) -> Vec3 {
        let horizontal = self.distance_m * self.pitch_rad.cos();
        let local = Vec3::new(
            horizontal * self.yaw_rad.sin(),
            self.distance_m * self.pitch_rad.sin(),
            horizontal * self.yaw_rad.cos(),
        );
        facing * local
    }
}

/// Feed trackpad wheel and pinch messages into the chase view's orbit.
pub fn read_trackpad(
    mut wheel: MessageReader<MouseWheel>,
    mut pinch: MessageReader<PinchGesture>,
    mut orbit: ResMut<ViewOrbit>,
) {
    for event in wheel.read() {
        let to_px = match event.unit {
            MouseScrollUnit::Line => MouseScrollUnit::SCROLL_UNIT_CONVERSION_FACTOR,
            MouseScrollUnit::Pixel => 1.0,
        };
        orbit.on_scroll(event.x * to_px, event.y * to_px);
    }
    for event in pinch.read() {
        orbit.on_pinch(event.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::FRAC_PI_2;

    fn assert_vec_near(actual: Vec3, expected: Vec3) {
        assert!(
            actual.distance(expected) < 0.01,
            "expected {expected:?}, got {actual:?}"
        );
    }

    #[test]
    fn the_default_orbit_is_the_chase_view_it_replaces() {
        // Given no trackpad input at all
        let orbit = ViewOrbit::default();

        // Then the camera sits where the hard-coded chase offset put it
        assert_vec_near(orbit.offset(Quat::IDENTITY), Vec3::new(5.0, 2.6, 7.5));
    }

    #[test]
    fn scrolling_sideways_pans_the_view_around_the_drone() {
        // Given the default view
        let mut orbit = ViewOrbit::default();
        let before = orbit.offset(Quat::IDENTITY);

        // When the user two-finger scrolls sideways
        orbit.on_scroll(250.0, 0.0);

        // Then the view has orbited to a different side at the same height and range
        let after = orbit.offset(Quat::IDENTITY);
        assert!(
            after.x < before.x,
            "pan should swing the view sideways: {before:?} -> {after:?}"
        );
        assert!((after.y - before.y).abs() < 0.01);
        assert!((after.length() - before.length()).abs() < 0.01);
    }

    #[test]
    fn scrolling_vertically_tilts_the_view_up_and_down() {
        // Given the default view
        let mut orbit = ViewOrbit::default();
        let before = orbit.offset(Quat::IDENTITY);

        // When the user two-finger scrolls vertically
        orbit.on_scroll(0.0, 250.0);

        // Then the view climbs (or dives) while keeping its range
        let after = orbit.offset(Quat::IDENTITY);
        assert!(
            after.y > before.y,
            "tilt should raise the view: {before:?} -> {after:?}"
        );
        assert!((after.length() - before.length()).abs() < 0.01);
    }

    #[test]
    fn tilt_never_goes_below_the_ground_or_past_top_down() {
        // Given the default view
        let mut orbit = ViewOrbit::default();

        // When the user tilts as far as the trackpad allows, both ways
        orbit.on_scroll(0.0, -100_000.0);
        let lowest = orbit.offset(Quat::IDENTITY);
        orbit.on_scroll(0.0, 100_000.0);
        let highest = orbit.offset(Quat::IDENTITY);

        // Then the camera stays at or above drone height and at or below top-down
        assert!(lowest.y >= 0.0, "view went under the drone: {lowest:?}");
        assert!(highest.y <= orbit.distance_m + 0.01);
        assert!(orbit.pitch_rad <= FRAC_PI_2);
    }

    #[test]
    fn pinching_in_zooms_closer_and_pinching_out_zooms_farther() {
        // Given the default view
        let mut orbit = ViewOrbit::default();
        let start = orbit.distance_m;

        // When the user pinches open (magnify) and then closed
        orbit.on_pinch(0.5);
        let zoomed_in = orbit.distance_m;
        orbit.on_pinch(-1.0);
        let zoomed_out = orbit.distance_m;

        // Then the view dollied in, then back out past where it started
        assert!(
            zoomed_in < start,
            "magnify should zoom in: {start} -> {zoomed_in}"
        );
        assert!(
            zoomed_out > start,
            "shrink should zoom out: {zoomed_in} -> {zoomed_out}"
        );
    }

    #[test]
    fn zoom_is_clamped_so_the_view_stays_usable() {
        // Given the default view
        let mut orbit = ViewOrbit::default();

        // When the user pinches to both extremes
        orbit.on_pinch(100.0);
        let closest = orbit.distance_m;
        orbit.on_pinch(-100.0);

        // Then the distance never leaves its range
        assert_eq!(closest, MIN_DISTANCE_M);
        assert_eq!(orbit.distance_m, MAX_DISTANCE_M);
    }

    #[test]
    fn the_orbit_follows_the_drones_facing() {
        // Given a drone facing the opposite way (yawed 180 degrees)
        let orbit = ViewOrbit::default();
        let facing = Quat::from_rotation_y(std::f32::consts::PI);

        // Then the default view is still behind it, mirrored with the turn
        assert_vec_near(orbit.offset(facing), Vec3::new(-5.0, 2.6, -7.5));
    }
}
