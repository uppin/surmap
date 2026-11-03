//! Scripted `survey-loop` flight: a deterministic kinematic loop over the
//! block, so a capture can be recorded again and give the same frames.
//! It moves the simulation's own drone; SurMap has no flight control.

#![allow(dead_code)]

use bevy::math::Vec3;

/// Where the rig is at a moment of the loop, in Bevy coordinates.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FlightPose {
    pub position: Vec3,
    /// Heading about Bevy +y, radians; 0 looks down -z (north).
    pub yaw_rad: f32,
}

/// A closed survey loop over the disaster block.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SurveyLoop {
    pub period_s: f32,
}

const SPEED_M_S: f32 = 1.5;
const CORNER_RADIUS_M: f32 = 8.0;
// Rounded rectangle in ENU: corners (-14, 8), (14, 8), (14, 78), (-14, 78).
const HALF_WIDTH_M: f32 = 14.0;
const SOUTH_M: f32 = 8.0;
const NORTH_M: f32 = 78.0;

fn straight_horizontal_m() -> f32 {
    2.0 * (HALF_WIDTH_M - CORNER_RADIUS_M)
}
fn straight_vertical_m() -> f32 {
    (NORTH_M - SOUTH_M) - 2.0 * CORNER_RADIUS_M
}
fn arc_m() -> f32 {
    std::f32::consts::FRAC_PI_2 * CORNER_RADIUS_M
}
fn perimeter_m() -> f32 {
    2.0 * straight_horizontal_m() + 2.0 * straight_vertical_m() + 4.0 * arc_m()
}

/// Point and unit tangent at arc length `s` along the loop, in ENU.
/// Starts at (0, 8) heading east, counter-clockwise.
fn point_at_distance(s_in: f32) -> (f32, f32, f32, f32) {
    let r = CORNER_RADIUS_M;
    let cx = HALF_WIDTH_M - r; // 6
    let cy_south = SOUTH_M + r; // 16
    let cy_north = NORTH_M - r; // 70
    let h = straight_horizontal_m();
    let v = straight_vertical_m();
    let a = arc_m();
    // Segments from (0, 8): east to (6, 8) is the second half of the bottom straight.
    let segments: [(f32, u8); 9] = [
        (cx, 0),     // bottom: (0,8) -> (6,8)
        (a, 1),      // SE corner centre (6,16)
        (v, 2),      // east side x=14, y 16->70
        (a, 3),      // NE corner centre (6,70)
        (h, 4),      // top y=78, x 6->-6
        (a, 5),      // NW corner centre (-6,70)
        (v, 6),      // west side x=-14, y 70->16
        (a, 7),      // SW corner centre (-6,16)
        (h - cx, 8), // bottom y=8, x -6->0 (remaining, total bottom = cx + (h-cx) from -6? see below)
    ];
    // Bottom straight total is h (from -6 to 6 in centre-x terms, i.e. x -6..6 at y=8,
    // plus the start offset: first piece 6, last piece 6, h=12.)
    let mut s = s_in.rem_euclid(perimeter_m());
    for (len, kind) in segments {
        if s <= len {
            return match kind {
                0 => (s, SOUTH_M, 1.0, 0.0),
                1 => {
                    let ang = -std::f32::consts::FRAC_PI_2 + s / r;
                    (
                        cx + r * ang.cos(),
                        cy_south + r * ang.sin(),
                        -ang.sin(),
                        ang.cos(),
                    )
                }
                2 => (HALF_WIDTH_M, cy_south + s, 0.0, 1.0),
                3 => {
                    let ang = s / r;
                    (
                        cx + r * ang.cos(),
                        cy_north + r * ang.sin(),
                        -ang.sin(),
                        ang.cos(),
                    )
                }
                4 => (cx - s, NORTH_M, -1.0, 0.0),
                5 => {
                    let ang = std::f32::consts::FRAC_PI_2 + s / r;
                    (
                        -cx + r * ang.cos(),
                        cy_north + r * ang.sin(),
                        -ang.sin(),
                        ang.cos(),
                    )
                }
                6 => (-HALF_WIDTH_M, cy_north - s, 0.0, -1.0),
                7 => {
                    let ang = std::f32::consts::PI + s / r;
                    (
                        -cx + r * ang.cos(),
                        cy_south + r * ang.sin(),
                        -ang.sin(),
                        ang.cos(),
                    )
                }
                _ => (-cx + s, SOUTH_M, 1.0, 0.0),
            };
        }
        s -= len;
    }
    (0.0, SOUTH_M, 1.0, 0.0)
}

impl SurveyLoop {
    pub const MAX_SPEED_M_S: f32 = 2.0;
    pub const MAX_YAW_RATE_RAD_S: f32 = 30.0 * std::f32::consts::PI / 180.0;

    /// The loop flown by `--flight survey-loop` / `?flight=survey-loop`.
    pub fn disaster_block() -> Self {
        Self {
            period_s: perimeter_m() / SPEED_M_S,
        }
    }

    /// The rig pose `t_s` seconds into the flight; periodic in `period_s`.
    pub fn pose_at(&self, t_s: f32) -> FlightPose {
        let period = self.period_s;
        let wrapped = t_s.rem_euclid(period);
        let distance = wrapped * SPEED_M_S;
        let (east, north, dir_east, dir_north) = point_at_distance(distance);
        let altitude = 7.0 + 1.5 * (std::f32::consts::TAU * wrapped / period).sin();
        FlightPose {
            position: Vec3::new(east, altitude, -north),
            yaw_rad: (-dir_east).atan2(dir_north),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const STEP_S: f32 = 0.1;

    fn samples(flight: SurveyLoop) -> Vec<FlightPose> {
        let steps = (flight.period_s / STEP_S).ceil() as usize;
        (0..=steps)
            .map(|i| flight.pose_at(i as f32 * STEP_S))
            .collect()
    }

    fn wrapped(angle: f32) -> f32 {
        (angle + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU) - std::f32::consts::PI
    }

    #[test]
    fn the_same_moment_always_gives_the_same_pose() {
        let flight = SurveyLoop::disaster_block();

        assert_eq!(flight.pose_at(12.3), flight.pose_at(12.3));
    }

    #[test]
    fn the_loop_ends_where_it_started() {
        let flight = SurveyLoop::disaster_block();

        let start = flight.pose_at(0.0);
        let end = flight.pose_at(flight.period_s);

        assert!(start.position.distance(end.position) < 1e-3);
        assert!(wrapped(start.yaw_rad - end.yaw_rad).abs() < 1e-3);
    }

    #[test]
    fn the_rig_never_moves_faster_than_stereo_odometry_can_follow() {
        let poses = samples(SurveyLoop::disaster_block());

        let fastest = poses
            .windows(2)
            .map(|w| w[0].position.distance(w[1].position) / STEP_S)
            .fold(0.0, f32::max);

        assert!(
            fastest <= SurveyLoop::MAX_SPEED_M_S + 1e-3,
            "fastest {fastest} m/s"
        );
    }

    #[test]
    fn the_rig_never_turns_faster_than_thirty_degrees_a_second() {
        let poses = samples(SurveyLoop::disaster_block());

        let fastest = poses
            .windows(2)
            .map(|w| wrapped(w[1].yaw_rad - w[0].yaw_rad).abs() / STEP_S)
            .fold(0.0, f32::max);

        assert!(
            fastest <= SurveyLoop::MAX_YAW_RATE_RAD_S + 1e-3,
            "fastest {fastest} rad/s"
        );
    }

    #[test]
    fn the_rig_stays_between_four_and_twelve_metres_up() {
        let poses = samples(SurveyLoop::disaster_block());

        assert!(poses.iter().all(|p| (4.0..=12.0).contains(&p.position.y)));
    }

    #[test]
    fn the_loop_covers_the_block_rather_than_hovering() {
        let poses = samples(SurveyLoop::disaster_block());

        let travelled: f32 = poses
            .windows(2)
            .map(|w| w[0].position.distance(w[1].position))
            .sum();

        assert!(travelled >= 40.0, "travelled {travelled} m");
    }
}
