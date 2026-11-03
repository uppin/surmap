//! The stereo camera profile, loaded at runtime from
//! `assets/cameras/<id>.camera.json` (named by `scene.json`).
//!
//! One file is the single source of truth for the rig: the simulation
//! builds its eye projections from it, the wire hello carries it to the
//! bridge, and the bridge and the recorder derive RTAB-Map's EuRoC
//! `sensor.yaml` from the same values, so renderer and SLAM cannot
//! disagree. Camera frame: optical (x right, y down, z forward); the rig
//! frame is x right, y up, z back (cameras look down -z).

use bevy::camera::{CameraProjection, SubCameraView};
use bevy::ecs::resource::Resource;
use bevy::math::{Mat4, Vec2, Vec3, Vec3A, Vec4};
use serde::{Deserialize, Serialize};

/// How the lens maps rays to pixels.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CameraModel {
    /// Ideal pinhole; `distortion` must be zero.
    Pinhole,
    /// Kannala–Brandt equidistant fisheye (OpenCV `fisheye`, Kalibr
    /// `equidistant`): θd = θ (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸).
    FisheyeEquidistant,
}

/// Where the rig sits on the drone body.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Mount {
    pub forward_m: f32,
    pub up_m: f32,
    /// Degrees below the horizon.
    pub pitch_deg: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Resource)]
pub struct CameraProfile {
    pub id: String,
    pub model: CameraModel,
    pub width: u32,
    pub height: u32,
    pub fx: f32,
    pub fy: f32,
    pub cx: f32,
    pub cy: f32,
    /// Pinhole: none (all zero). Fisheye: k1..k4.
    #[serde(default)]
    pub distortion: [f32; 4],
    pub baseline_m: f32,
    pub rate_hz: f32,
    pub mount: Mount,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ProfileError {
    Json(String),
    Invalid(String),
}

impl CameraProfile {
    pub fn from_json(text: &str) -> Result<Self, ProfileError> {
        let profile: Self = serde_json::from_str(text).map_err(|e| ProfileError::Json(e.to_string()))?;
        profile.validate()?;
        Ok(profile)
    }

    fn validate(&self) -> Result<(), ProfileError> {
        let bad = |why: &str| Err(ProfileError::Invalid(format!("{}: {why}", self.id)));
        if self.width == 0 || self.height == 0 {
            return bad("width and height must be positive");
        }
        if !(self.fx > 0.0 && self.fy > 0.0) {
            return bad("fx and fy must be positive");
        }
        if !(self.baseline_m > 0.0 && self.rate_hz > 0.0) {
            return bad("baseline_m and rate_hz must be positive");
        }
        if self.model == CameraModel::Pinhole && self.distortion != [0.0; 4] {
            return bad("a pinhole profile has no distortion (the renderer draws an ideal pinhole)");
        }
        Ok(())
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("profile serializes")
    }

    /// Rig-frame translation of each eye: half a baseline either side on x.
    pub fn eye_translation_m(&self, right: bool) -> Vec3 {
        let half = self.baseline_m / 2.0;
        Vec3::new(if right { half } else { -half }, 0.0, 0.0)
    }

    /// The mount offset in the drone body frame (forward is -z).
    pub fn mount_offset(&self) -> Vec3 {
        Vec3::new(0.0, self.mount.up_m, -self.mount.forward_m)
    }

    /// Lens distortion θ → θd.
    fn distort(&self, theta: f32) -> f32 {
        let [k1, k2, k3, k4] = self.distortion;
        let t2 = theta * theta;
        theta * (1.0 + t2 * (k1 + t2 * (k2 + t2 * (k3 + t2 * k4))))
    }

    /// Pixel of an optical-frame point, or `None` when it cannot be imaged.
    pub fn project(&self, p: Vec3) -> Option<Vec2> {
        match self.model {
            CameraModel::Pinhole => {
                (p.z > 0.0).then(|| Vec2::new(self.fx * p.x / p.z + self.cx, self.fy * p.y / p.z + self.cy))
            }
            CameraModel::FisheyeEquidistant => {
                let rho = (p.x * p.x + p.y * p.y).sqrt();
                if rho == 0.0 {
                    return (p.z > 0.0).then_some(Vec2::new(self.cx, self.cy));
                }
                let theta_d = self.distort(rho.atan2(p.z));
                Some(Vec2::new(self.fx * theta_d * p.x / rho + self.cx, self.fy * theta_d * p.y / rho + self.cy))
            }
        }
    }

    /// The unit optical-frame ray of a pixel (the inverse of `project`).
    pub fn unproject(&self, pixel: Vec2) -> Vec3 {
        let a = (pixel.x - self.cx) / self.fx;
        let b = (pixel.y - self.cy) / self.fy;
        match self.model {
            CameraModel::Pinhole => Vec3::new(a, b, 1.0).normalize(),
            CameraModel::FisheyeEquidistant => {
                let theta_d = (a * a + b * b).sqrt();
                if theta_d == 0.0 {
                    return Vec3::Z;
                }
                // Newton on θ (1 + k1 θ² + …) = θd.
                let [k1, k2, k3, k4] = self.distortion;
                let mut theta = theta_d;
                for _ in 0..10 {
                    let t2 = theta * theta;
                    let f = self.distort(theta) - theta_d;
                    let df = 1.0 + t2 * (3.0 * k1 + t2 * (5.0 * k2 + t2 * (7.0 * k3 + t2 * 9.0 * k4)));
                    theta -= f / df;
                }
                let s = theta.sin() / theta_d;
                Vec3::new(a * s, b * s, theta.cos())
            }
        }
    }

    /// Half-angle (radians) from the axis to the farthest image corner.
    pub fn max_half_angle(&self) -> f32 {
        let corners = [(0.0, 0.0), (self.width as f32, 0.0), (0.0, self.height as f32), (self.width as f32, self.height as f32)];
        corners.iter().map(|&(u, v)| self.unproject(Vec2::new(u, v)).z.clamp(-1.0, 1.0).acos()).fold(0.0, f32::max)
    }
}

/// Bevy projection of an ideal pinhole with the profile's exact
/// intrinsics (off-centre principal point, fx ≠ fy), reverse-Z with an
/// infinite far plane like Bevy's own perspective.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CalibratedProjection {
    pub fx: f32,
    pub fy: f32,
    pub cx: f32,
    pub cy: f32,
    pub width: f32,
    pub height: f32,
    pub near: f32,
    pub far: f32,
}

impl CalibratedProjection {
    pub fn of(profile: &CameraProfile, near: f32, far: f32) -> Self {
        Self {
            fx: profile.fx,
            fy: profile.fy,
            cx: profile.cx,
            cy: profile.cy,
            width: profile.width as f32,
            height: profile.height as f32,
            near,
            far,
        }
    }

    /// View-space point (x right, y up, looking down -z) at `depth` of a pixel.
    fn view_point(&self, u: f32, v: f32, depth: f32) -> Vec3A {
        Vec3A::new((u - self.cx) / self.fx * depth.abs(), -(v - self.cy) / self.fy * depth.abs(), depth)
    }
}

impl CameraProjection for CalibratedProjection {
    fn get_clip_from_view(&self) -> Mat4 {
        Mat4::from_cols(
            Vec4::new(2.0 * self.fx / self.width, 0.0, 0.0, 0.0),
            Vec4::new(0.0, 2.0 * self.fy / self.height, 0.0, 0.0),
            Vec4::new(-(2.0 * self.cx / self.width - 1.0), -(1.0 - 2.0 * self.cy / self.height), 0.0, -1.0),
            Vec4::new(0.0, 0.0, self.near, 0.0),
        )
    }

    fn get_clip_from_view_for_sub(&self, _sub_view: &SubCameraView) -> Mat4 {
        self.get_clip_from_view()
    }

    /// The image size is the profile's, whatever the target: nothing to do.
    fn update(&mut self, _width: f32, _height: f32) {}

    fn far(&self) -> f32 {
        self.far
    }

    fn get_frustum_corners(&self, z_near: f32, z_far: f32) -> [Vec3A; 8] {
        let (w, h) = (self.width, self.height);
        // Bottom right, top right, top left, bottom left — near, then far.
        [
            self.view_point(w, h, z_near),
            self.view_point(w, 0.0, z_near),
            self.view_point(0.0, 0.0, z_near),
            self.view_point(0.0, h, z_near),
            self.view_point(w, h, z_far),
            self.view_point(w, 0.0, z_far),
            self.view_point(0.0, 0.0, z_far),
            self.view_point(0.0, h, z_far),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SHIPPED: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/assets/cameras/elp-stereo-pinhole.camera.json");

    fn elp() -> CameraProfile {
        CameraProfile::from_json(&std::fs::read_to_string(SHIPPED).expect("shipped profile")).expect("valid")
    }

    fn a_fisheye() -> CameraProfile {
        CameraProfile {
            id: "fisheye-test".into(),
            model: CameraModel::FisheyeEquidistant,
            distortion: [-0.013, 0.021, -0.012, 0.002],
            fx: 285.0,
            fy: 285.0,
            ..elp()
        }
    }

    fn close(a: Vec2, b: Vec2) -> bool {
        a.distance(b) < 1e-3
    }

    #[test]
    fn the_shipped_profile_is_the_surmap_stereo_rig() {
        let rig = elp();

        assert_eq!((rig.model, rig.width, rig.height, rig.fx, rig.cx, rig.cy), (CameraModel::Pinhole, 640, 480, 381.36, 320.0, 240.0));
        assert_eq!((rig.baseline_m, rig.mount.pitch_deg), (0.07, 35.0));
    }

    #[test]
    fn eyes_sit_half_a_baseline_either_side_of_the_rig_origin() {
        let rig = elp();

        assert_eq!((rig.eye_translation_m(false), rig.eye_translation_m(true)), (Vec3::new(-0.035, 0.0, 0.0), Vec3::new(0.035, 0.0, 0.0)));
    }

    #[test]
    fn a_pinhole_with_distortion_is_refused() {
        let text = elp().to_json().replace("\"distortion\":[0.0,0.0,0.0,0.0]", "\"distortion\":[0.1,0.0,0.0,0.0]");

        assert!(matches!(CameraProfile::from_json(&text), Err(ProfileError::Invalid(_))));
    }

    #[test]
    fn the_optical_axis_lands_on_the_principal_point_for_every_model() {
        for profile in [elp(), a_fisheye()] {
            assert_eq!(profile.project(Vec3::Z), Some(Vec2::new(320.0, 240.0)), "{}", profile.id);
        }
    }

    #[test]
    fn a_pinhole_projects_by_its_focal_lengths() {
        let rig = elp();

        assert!(close(rig.project(Vec3::new(1.0, -0.5, 4.0)).expect("in front"), Vec2::new(320.0 + 95.34, 240.0 - 47.67)));
    }

    #[test]
    fn a_fisheye_images_rays_beyond_ninety_degrees() {
        let sideways_and_back = Vec3::new(1.0, 0.0, -0.2);

        assert!(a_fisheye().project(sideways_and_back).is_some());
        assert_eq!(elp().project(sideways_and_back), None);
    }

    #[test]
    fn unprojecting_a_projected_ray_returns_it_for_every_model() {
        let ray = Vec3::new(0.4, -0.3, 0.8).normalize();
        for profile in [elp(), a_fisheye()] {
            let back = profile.unproject(profile.project(ray).expect("imaged"));
            assert!(back.abs_diff_eq(ray, 1e-4), "{}: {back:?}", profile.id);
        }
    }

    #[test]
    fn the_calibrated_projection_matches_the_profile_off_centre() {
        let off_centre = CameraProfile { cx: 300.0, cy: 250.0, fy: 390.0, ..elp() };
        let projection = CalibratedProjection::of(&off_centre, 0.1, 600.0);
        let view = Vec3::new(1.0, 0.5, -4.0); // view space: y up, looking down -z

        let clip = projection.get_clip_from_view() * view.extend(1.0);
        let ndc = clip.truncate() / clip.w;
        let pixel = Vec2::new((ndc.x + 1.0) / 2.0 * 640.0, (1.0 - ndc.y) / 2.0 * 480.0);

        let optical = Vec3::new(view.x, -view.y, -view.z);
        assert!(close(pixel, off_centre.project(optical).expect("in front")), "{pixel:?}");
    }

    #[test]
    fn the_shipped_pinhole_sees_forty_six_degrees_to_its_corners() {
        let half = elp().max_half_angle().to_degrees();

        assert!((half - 46.4).abs() < 0.5, "{half}");
    }
}
