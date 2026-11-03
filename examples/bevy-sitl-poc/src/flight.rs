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

impl SurveyLoop {
    pub const MAX_SPEED_M_S: f32 = 2.0;
    pub const MAX_YAW_RATE_RAD_S: f32 = 30.0 * std::f32::consts::PI / 180.0;

    /// The loop flown by `--flight survey-loop` / `?flight=survey-loop`.
    pub fn disaster_block() -> Self {
        todo!("define the survey loop")
    }

    /// The rig pose `t_s` seconds into the flight; periodic in `period_s`.
    pub fn pose_at(&self, t_s: f32) -> FlightPose {
        let _ = t_s;
        todo!("evaluate the survey loop")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const STEP_S: f32 = 0.1;

    fn samples(flight: SurveyLoop) -> Vec<FlightPose> {
        let steps = (flight.period_s / STEP_S).ceil() as usize;
        (0..=steps).map(|i| flight.pose_at(i as f32 * STEP_S)).collect()
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

        let fastest = poses.windows(2).map(|w| w[0].position.distance(w[1].position) / STEP_S).fold(0.0, f32::max);

        assert!(fastest <= SurveyLoop::MAX_SPEED_M_S + 1e-3, "fastest {fastest} m/s");
    }

    #[test]
    fn the_rig_never_turns_faster_than_thirty_degrees_a_second() {
        let poses = samples(SurveyLoop::disaster_block());

        let fastest = poses.windows(2).map(|w| wrapped(w[1].yaw_rad - w[0].yaw_rad).abs() / STEP_S).fold(0.0, f32::max);

        assert!(fastest <= SurveyLoop::MAX_YAW_RATE_RAD_S + 1e-3, "fastest {fastest} rad/s");
    }

    #[test]
    fn the_rig_stays_between_four_and_twelve_metres_up() {
        let poses = samples(SurveyLoop::disaster_block());

        assert!(poses.iter().all(|p| (4.0..=12.0).contains(&p.position.y)));
    }

    #[test]
    fn the_loop_covers_the_block_rather_than_hovering() {
        let poses = samples(SurveyLoop::disaster_block());

        let travelled: f32 = poses.windows(2).map(|w| w[0].position.distance(w[1].position)).sum();

        assert!(travelled >= 40.0, "travelled {travelled} m");
    }
}
