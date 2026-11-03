//! Run modes: manual flight, the scripted `survey-loop`, and the native
//! `--screenshot <dir> --at <t_s>` review stills (visual spec §1).

use std::path::PathBuf;

use bevy::app::AppExit;
use bevy::camera::RenderTarget;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat, TextureUsages};
use bevy::render::view::screenshot::{save_to_disk, Screenshot, ScreenshotCaptured};

use crate::flight::SurveyLoop;
use crate::look::{photographic, Lens};
use crate::world::{enu, scene_ready, PendingModel, SceneState};
use crate::{Drone, StereoFeeds, RIG_FORWARD_M, RIG_UP_M};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FlightMode {
    Manual,
    SurveyLoop,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ShotPlan {
    pub dir: PathBuf,
    pub at_s: f32,
}

#[derive(Resource, Debug, Clone, PartialEq)]
pub struct RunMode {
    pub flight: FlightMode,
    pub screenshot: Option<ShotPlan>,
}

impl RunMode {
    /// `--flight survey-loop`, `--screenshot <dir> --at <t_s>` (the
    /// latter implies the survey loop).
    pub fn from_args(args: &[String]) -> Result<Self, String> {
        let value = |flag: &str| args.iter().position(|a| a == flag).map(|i| args.get(i + 1).cloned());
        let flight = match value("--flight") {
            None => FlightMode::Manual,
            Some(Some(name)) if name == "survey-loop" => FlightMode::SurveyLoop,
            Some(other) => return Err(format!("unknown --flight {other:?}")),
        };
        let screenshot = match value("--screenshot") {
            None => None,
            Some(Some(dir)) => {
                let at_s = match value("--at") {
                    Some(Some(t)) => t.parse::<f32>().map_err(|e| format!("--at: {e}"))?,
                    _ => return Err("--screenshot needs --at <t_s>".into()),
                };
                Some(ShotPlan { dir: PathBuf::from(dir), at_s })
            }
            Some(None) => return Err("--screenshot needs a directory".into()),
        };
        let flight = if screenshot.is_some() { FlightMode::SurveyLoop } else { flight };
        Ok(Self { flight, screenshot })
    }
}

/// The scripted rig pose drives the (kinematic) drone body.
pub fn fly_scripted(mode: Res<RunMode>, time: Res<Time>, mut drone: Query<&mut Transform, With<Drone>>) {
    if mode.flight != FlightMode::SurveyLoop {
        return;
    }
    let t = mode.screenshot.as_ref().map_or(time.elapsed_secs(), |plan| plan.at_s);
    let pose = SurveyLoop::disaster_block().pose_at(t);
    let Ok(mut body) = drone.single_mut() else { return };
    body.rotation = Quat::from_rotation_y(pose.yaw_rad);
    body.translation = pose.position - body.rotation * Vec3::new(0.0, RIG_UP_M, -RIG_FORWARD_M);
}

#[derive(Component)]
pub struct OverviewCam;

#[derive(Resource)]
pub struct Shots {
    overview: Handle<Image>,
    settled_frames: u32,
    requested: bool,
    captured: u32,
}

pub fn shot_target(images: &mut Assets<Image>, width: u32, height: u32) -> Handle<Image> {
    let mut image = Image::new_fill(
        Extent3d { width, height, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &[0, 0, 0, 255],
        TextureFormat::Bgra8UnormSrgb,
        bevy::asset::RenderAssetUsages::default(),
    );
    image.texture_descriptor.usage = TextureUsages::TEXTURE_BINDING
        | TextureUsages::COPY_DST
        | TextureUsages::COPY_SRC
        | TextureUsages::RENDER_ATTACHMENT;
    images.add(image)
}

/// The overview still: from ENU (−40, −5, 35) towards ENU (0, 45, 0), 50° vertical.
pub fn setup_overview(mut commands: Commands, mode: Res<RunMode>, mut images: ResMut<Assets<Image>>) {
    if mode.screenshot.is_none() {
        return;
    }
    let overview = shot_target(&mut images, 1280, 720);
    let mut camera = commands.spawn((
        OverviewCam,
        Camera3d::default(),
        Camera { order: 2, ..default() },
        RenderTarget::Image(overview.clone().into()),
        Projection::Perspective(PerspectiveProjection { fov: 50f32.to_radians(), near: 0.1, far: 600.0, ..default() }),
        Transform::from_translation(enu(-40.0, -5.0, 35.0)).looking_at(enu(0.0, 45.0, 0.0), Vec3::Y),
    ));
    photographic(&mut camera, Lens::Still);
    commands.insert_resource(Shots { overview, settled_frames: 0, requested: false, captured: 0 });
}

/// Frames to wait after everything loaded: mips upload, shadows and TAA settle.
const SETTLE_FRAMES: u32 = 90;

#[allow(clippy::too_many_arguments)]
pub fn take_shots(
    mut commands: Commands,
    mode: Res<RunMode>,
    shots: Option<ResMut<Shots>>,
    scene: Option<Res<SceneState>>,
    assets: Res<AssetServer>,
    pending: Query<(), With<PendingModel>>,
    feeds: Res<StereoFeeds>,
    mut exit: MessageWriter<AppExit>,
) {
    let (Some(plan), Some(mut shots), Some(scene)) = (mode.screenshot.as_ref(), shots, scene) else { return };
    if shots.captured == 3 {
        exit.write(AppExit::Success);
        return;
    }
    // A still of a half-loaded scene is worse than none: fail loudly.
    let failed = scene.pending.iter().map(|h| h.id()).chain([scene.manifest.id().untyped()]).find(|id| assets.load_state(*id).is_failed());
    if let Some(id) = failed {
        error!("asset failed to load: {:?}", assets.get_path(id));
        exit.write(AppExit::error());
        return;
    }
    if shots.requested || !scene_ready(&scene, &assets, pending.iter().count()) {
        return;
    }
    shots.settled_frames += 1;
    if shots.settled_frames < SETTLE_FRAMES {
        return;
    }
    std::fs::create_dir_all(&plan.dir).expect("screenshot directory");
    for (name, screenshot) in [
        ("chase.png", Screenshot::primary_window()),
        ("left.png", Screenshot::image(feeds.left.clone())),
        ("overview.png", Screenshot::image(shots.overview.clone())),
    ] {
        commands.spawn(screenshot).observe(save_to_disk(plan.dir.join(name))).observe(count_capture);
    }
    shots.requested = true;
}

fn count_capture(_captured: On<ScreenshotCaptured>, mut shots: ResMut<Shots>) {
    shots.captured += 1;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(list: &[&str]) -> Vec<String> {
        std::iter::once("bevy-sitl-poc").chain(list.iter().copied()).map(String::from).collect()
    }

    #[test]
    fn no_flags_fly_manually_without_stills() {
        let mode = RunMode::from_args(&args(&[])).expect("valid");

        assert_eq!(mode, RunMode { flight: FlightMode::Manual, screenshot: None });
    }

    #[test]
    fn a_screenshot_request_flies_the_survey_loop_to_its_moment() {
        let mode = RunMode::from_args(&args(&["--screenshot", "shots/V1", "--at", "20"])).expect("valid");

        assert_eq!(mode.flight, FlightMode::SurveyLoop);
        assert_eq!(mode.screenshot, Some(ShotPlan { dir: PathBuf::from("shots/V1"), at_s: 20.0 }));
    }

    #[test]
    fn a_screenshot_without_a_moment_is_refused() {
        assert!(RunMode::from_args(&args(&["--screenshot", "shots"])).is_err());
    }

    #[test]
    fn an_unknown_flight_is_refused() {
        assert!(RunMode::from_args(&args(&["--flight", "loop-de-loop"])).is_err());
    }
}
