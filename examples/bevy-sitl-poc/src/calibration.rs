//! Stereo calibration produced by the Bevy rig.
//!
//! The numbers mirror the SurMap Gazebo stereo camera
//! (`docs/simulation/gz/surmap_stereo_cam/model.sdf`): 640x480,
//! fx = fy ~= 381.36 px, principal point at the image centre,
//! 0.07 m baseline. The rig frame is the camera convention used by
//! the calibration JSON: x right, y up, z back (cameras look down -z).

use bevy::ecs::resource::Resource;
use serde::Serialize;

/// One stereo rig: two identical cameras offset along rig x.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Resource)]
pub struct StereoCalibration {
    pub width: u32,
    pub height: u32,
    pub fx: f32,
    pub fy: f32,
    pub cx: f32,
    pub cy: f32,
    pub baseline_m: f32,
    /// Rig-frame translation of each eye, in metres.
    pub left_translation_m: [f32; 3],
    pub right_translation_m: [f32; 3],
}

impl StereoCalibration {
    /// The SurMap stereo rig as flown in the Gazebo disaster world.
    pub fn surmap_rig() -> Self {
        let half = 0.07 / 2.0;
        Self {
            width: 640,
            height: 480,
            fx: 381.36,
            fy: 381.36,
            cx: 320.0,
            cy: 240.0,
            baseline_m: 0.07,
            left_translation_m: [-half, 0.0, 0.0],
            right_translation_m: [half, 0.0, 0.0],
        }
    }

    /// Vertical field of view the Bevy `PerspectiveProjection` needs,
    /// derived from the calibration (not chosen independently).
    pub fn vertical_fov_rad(&self) -> f32 {
        2.0 * (self.cy / self.fy).atan()
    }

    /// The calibration as the JSON a backend would consume.
    /// Seam for the frame-export phase; exercised by the tests.
    #[allow(dead_code)]
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("calibration serializes")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rig_matches_the_surmap_stereo_camera() {
        let rig = StereoCalibration::surmap_rig();
        assert_eq!(rig.width, 640);
        assert_eq!(rig.height, 480);
        assert!((rig.fx - 381.36).abs() < 0.01);
        assert!((rig.fy - 381.36).abs() < 0.01);
        assert!((rig.cx - 320.0).abs() < f32::EPSILON);
        assert!((rig.cy - 240.0).abs() < f32::EPSILON);
        assert!((rig.baseline_m - 0.07).abs() < f32::EPSILON);
    }

    #[test]
    fn eyes_sit_half_a_baseline_either_side_of_the_rig_origin() {
        let rig = StereoCalibration::surmap_rig();
        assert_eq!(rig.left_translation_m, [-0.035, 0.0, 0.0]);
        assert_eq!(rig.right_translation_m, [0.035, 0.0, 0.0]);
        let separation = rig.right_translation_m[0] - rig.left_translation_m[0];
        assert!((separation - rig.baseline_m).abs() < f32::EPSILON);
    }

    #[test]
    fn vertical_fov_is_derived_from_fy_and_the_image_centre() {
        // Given the 640x480 rig, When the FOV is derived from fy and cy,
        // Then it equals 2*atan(cy/fy) (~64.4 degrees), so the Bevy
        // projection and the calibration can never drift apart.
        let rig = StereoCalibration::surmap_rig();
        let expected = 2.0 * (240.0f32 / 381.36).atan();
        assert!((rig.vertical_fov_rad() - expected).abs() < 1e-6);
    }

    #[test]
    fn json_carries_every_field_a_backend_needs() {
        let text = StereoCalibration::surmap_rig().to_json();
        for field in [
            "\"width\":640",
            "\"height\":480",
            "\"fx\":381.36",
            "\"baseline_m\":0.07",
            "\"left_translation_m\":[-0.035,0.0,0.0]",
            "\"right_translation_m\":[0.035,0.0,0.0]",
        ] {
            assert!(text.contains(field), "missing {field} in {text}");
        }
    }
}
