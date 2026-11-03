//! Run modes: manual flight, the scripted `survey-loop`, and the native
//! `--screenshot <dir> --at <t_s>` review stills (visual spec §1).

use std::path::PathBuf;

use bevy::app::AppExit;
use bevy::camera::RenderTarget;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat, TextureUsages};
use bevy::render::view::screenshot::{save_to_disk, Screenshot, ScreenshotCaptured};

use crate::flight::SurveyLoop;
use crate::record::{RecordPlan, SimTime};
use crate::look::{photographic, Lens};
use crate::world::{enu, scene_ready, PendingModel, SceneState};
use crate::calibration::CameraProfile;
use crate::{Drone, StereoFeeds};

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
    pub record: Option<RecordPlan>,
    /// `--camera cameras/<id>.camera.json`: another profile than the scene's.
    pub camera: Option<String>,
    /// `--scenario <id>` (native) / `?scenario=<id>` (page): a station scenario instead of `scene.json`.
    pub scenario: Option<String>,
}

/// The manifest a run loads: a station scenario, or the shipped scene.
pub fn manifest_path(scenario: Option<&str>) -> String {
    scenario.map_or_else(|| "scene.json".to_owned(), |id| format!("scenarios/{id}.json"))
}

/// A scenario id is a slug the station made: letters, digits and dashes only.
fn checked_scenario(id: &str) -> Result<String, String> {
    let ok = !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-');
    if ok { Ok(id.to_owned()) } else { Err(format!("scenario id {id:?} must be letters, digits and dashes")) }
}

/// The page's `?scenario=<id>` (wasm); natively the flag carries it.
#[cfg(target_arch = "wasm32")]
pub fn page_scenario() -> Option<String> {
    let search = web_sys::window()?.location().search().ok()?;
    search.trim_start_matches('?').split('&').find_map(|pair| pair.strip_prefix("scenario=").map(str::to_owned))
}

#[cfg(not(target_arch = "wasm32"))]
pub fn page_scenario() -> Option<String> {
    None
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
        let number = |flag: &str, default: f32| -> Result<f32, String> {
            match value(flag) {
                None => Ok(default),
                Some(Some(v)) => v.parse::<f32>().map_err(|e| format!("{flag}: {e}")),
                Some(None) => Err(format!("{flag} needs a value")),
            }
        };
        let record = match value("--record") {
            None => None,
            Some(Some(dir)) => Some(RecordPlan {
                dir: PathBuf::from(dir),
                frames: number("--frames", 60.0)? as u32,
                rate_hz: number("--rate-hz", 10.0)?,
                start_s: number("--start", 0.0)?,
                jpeg: args.iter().any(|a| a == "--jpeg"),
            }),
            Some(None) => return Err("--record needs a directory".into()),
        };
        let scripted = screenshot.is_some() || record.is_some();
        let flight = if scripted { FlightMode::SurveyLoop } else { flight };
        let camera = match value("--camera") {
            None => None,
            Some(Some(path)) => Some(path),
            Some(None) => return Err("--camera needs a profile path".into()),
        };
        let scenario = match value("--scenario") {
            None => page_scenario().map(|id| checked_scenario(&id)).transpose()?,
            Some(Some(id)) => Some(checked_scenario(&id)?),
            Some(None) => return Err("--scenario needs an id".into()),
        };
        Ok(Self { flight, screenshot, record, camera, scenario })
    }

    /// No window chrome: stills and recordings run unattended.
    pub fn unattended(&self) -> bool {
        self.screenshot.is_some() || self.record.is_some()
    }
}

/// The scripted rig pose drives the (kinematic) drone body.
pub fn fly_scripted(
    mode: Res<RunMode>,
    time: Res<Time>,
    sim_time: Res<SimTime>,
    rig: Option<Res<CameraProfile>>,
    mut drone: Query<&mut Transform, With<Drone>>,
) {
    let Some(rig) = rig else { return };
    if mode.flight != FlightMode::SurveyLoop {
        return;
    }
    let t = sim_time.0.unwrap_or(time.elapsed_secs());
    let pose = SurveyLoop::disaster_block().pose_at(t);
    let Ok(mut body) = drone.single_mut() else { return };
    body.rotation = Quat::from_rotation_y(pose.yaw_rad);
    body.translation = pose.position - body.rotation * rig.mount_offset();
}

#[derive(Component)]
pub struct OverviewCam;

/// The review still of what the rig sees of a fire (screenshot mode only).
#[derive(Component)]
pub struct FireEyeCam;

#[derive(Resource)]
pub struct FireEyeFeed(pub Handle<Image>);

/// Where the fire eye stands relative to the ignition: south, in metres, and its altitude.
const FIRE_EYE_SOUTH_M: f32 = 40.0;
const FIRE_EYE_ALTITUDE_M: f32 = 15.0;

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

/// With a fire in the scene the review still looks at it: from the south of the ignition,
/// raised, towards the downwind side. Re-aimed once, when the manifest has built.
pub fn aim_overview_at_fire(
    fires: Option<Res<crate::wildfire::Wildfire>>,
    mut overview: Query<&mut Transform, (With<OverviewCam>, Without<FireEyeCam>)>,
    mut eye: Query<(&mut Transform, &mut Camera), (With<FireEyeCam>, Without<OverviewCam>)>,
    mut aimed: Local<bool>,
) {
    let Some(ignition) = fires.as_ref().and_then(|f| f.first_ignition()) else {
        return;
    };
    if *aimed {
        return;
    }
    let (Ok(mut view), Ok((mut eye_at, mut eye_camera))) = (overview.single_mut(), eye.single_mut()) else {
        return;
    };
    *aimed = true;
    *view = Transform::from_translation(enu(ignition.x - 6.0, ignition.y - 48.0, 24.0))
        .looking_at(enu(ignition.x + 14.0, ignition.y, 0.0), Vec3::Y);
    *eye_at = Transform::from_translation(enu(ignition.x, ignition.y - FIRE_EYE_SOUTH_M, FIRE_EYE_ALTITUDE_M))
        .looking_at(enu(ignition.x, ignition.y, 0.0), Vec3::Y);
    eye_camera.is_active = true;
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
    feeds: Option<Res<StereoFeeds>>,
    fire_eye: Option<Res<FireEyeFeed>>,
    fires: Option<Res<crate::wildfire::Wildfire>>,
    mut exit: MessageWriter<AppExit>,
) {
    let (Some(plan), Some(mut shots), Some(scene)) = (mode.screenshot.as_ref(), shots, scene) else { return };
    if let Some(why) = &scene.failed {
        error!("scene cannot be built: {why}");
        exit.write(AppExit::error());
        return;
    }
    let Some(feeds) = feeds else { return };
    let fire_eye = fire_eye.filter(|_| fires.as_ref().is_some_and(|f| f.has_fires()));
    if shots.captured == 3 + u32::from(fire_eye.is_some()) {
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
    let mut stills = vec![
        ("chase.png", Screenshot::primary_window()),
        ("left.png", Screenshot::image(feeds.left.clone())),
        ("overview.png", Screenshot::image(shots.overview.clone())),
    ];
    if let Some(feed) = &fire_eye {
        stills.push(("fire-eye.png", Screenshot::image(feed.0.clone())));
    }
    for (name, screenshot) in stills {
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

        assert_eq!(mode, RunMode { flight: FlightMode::Manual, screenshot: None, record: None, camera: None, scenario: None });
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
    fn a_recording_flies_the_survey_loop_at_its_rate() {
        let mode = RunMode::from_args(&args(&["--record", "cap", "--frames", "120", "--start", "30", "--jpeg"])).expect("valid");

        assert_eq!(mode.flight, FlightMode::SurveyLoop);
        assert_eq!(
            mode.record,
            Some(RecordPlan { dir: PathBuf::from("cap"), frames: 120, rate_hz: 10.0, start_s: 30.0, jpeg: true })
        );
    }

    #[test]
    fn a_camera_override_names_another_profile() {
        let mode = RunMode::from_args(&args(&["--camera", "cameras/wide.camera.json"])).expect("valid");

        assert_eq!(mode.camera.as_deref(), Some("cameras/wide.camera.json"));
    }

    #[test]
    fn a_scenario_flag_names_the_scenario_to_load() {
        let mode = RunMode::from_args(&args(&["--scenario", "wreck-on-the-avenue"])).expect("valid");

        assert_eq!(mode.scenario.as_deref(), Some("wreck-on-the-avenue"));
    }

    #[test]
    fn a_scenario_loads_from_the_station_scenarios_folder() {
        assert_eq!(manifest_path(Some("wreck-on-the-avenue")), "scenarios/wreck-on-the-avenue.json");
        assert_eq!(manifest_path(None), "scene.json");
    }

    #[test]
    fn a_scenario_id_that_could_leave_the_folder_is_refused() {
        assert!(RunMode::from_args(&args(&["--scenario", "../secrets"])).is_err());
    }

    #[test]
    fn an_unknown_flight_is_refused() {
        assert!(RunMode::from_args(&args(&["--flight", "loop-de-loop"])).is_err());
    }
}
