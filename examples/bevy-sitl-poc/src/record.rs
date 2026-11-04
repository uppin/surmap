//! `--record <dir> --frames N [--rate-hz 10] [--start <t_s>] [--jpeg]`:
//! fly the survey loop frame by frame and write a stereo capture that
//! `surmap.simulation.bevy_capture.load_bevy_capture` reads — grey8
//! eye images, `frames.jsonl` with each frame's ground-truth rig pose,
//! `calibration.json`, and `ground_truth.json`.

use std::io::Write as _;
use std::path::{Path, PathBuf};

use bevy::app::AppExit;
use bevy::prelude::*;
use bevy::render::gpu_readback::{Readback, ReadbackComplete};
use image::{codecs::jpeg::JpegEncoder, GrayImage};

use crate::actors::{self, Figure};
use crate::building::BuildingBlaze;
use crate::calibration::CameraProfile;
use crate::fire;
use crate::flight::SurveyLoop;
use crate::wildfire::Wildfire;
use crate::world::{scene_ready, GroundTruth, PendingModel, SceneState};
use crate::{wire, StereoFeeds};

#[derive(Debug, Clone, PartialEq)]
pub struct RecordPlan {
    pub dir: PathBuf,
    pub frames: u32,
    pub rate_hz: f32,
    pub start_s: f32,
    pub jpeg: bool,
}

impl RecordPlan {
    pub fn t_at(&self, frame: u32) -> f32 {
        self.start_s + frame as f32 / self.rate_hz
    }

    /// The frame's timestamp in exact integer nanoseconds.
    pub fn t_ns(&self, frame: u32) -> u64 {
        let start = (f64::from(self.start_s) * 1e9).round() as u64;
        start + u64::from(frame) * (1e9 / f64::from(self.rate_hz)).round() as u64
    }
}

/// The moment the scripted flight shows; `None` follows the clock.
#[derive(Resource, Default)]
pub struct SimTime(pub Option<f32>);

/// Frames to wait after the scene loaded, and after each pose change.
const FIRST_SETTLE: u32 = 90;
const STEP_SETTLE: u32 = 3;
/// Progress line every N frames; a warning after this many seconds without one.
const PROGRESS_EVERY: u32 = 10;
const STALL_S: f64 = 10.0;

#[derive(Resource)]
pub struct Recorder {
    plan: RecordPlan,
    frame: u32,
    wait: u32,
    started: bool,
    requested: bool,
    left: Option<Vec<u8>>,
    right: Option<Vec<u8>>,
    lines: Vec<String>,
    /// `fire_perimeter.jsonl`: one line per frame while the scene has fires.
    fire_lines: Vec<String>,
    /// `building_fires.jsonl`: one line per frame while the scene has buildings that can burn.
    building_lines: Vec<String>,
    /// `object_tracks.jsonl`: one line per frame, always: the wind and each moving body.
    track_lines: Vec<String>,
    /// Wall-clock seconds at the start and at the last written frame.
    started_at: f64,
    last_frame_at: f64,
    stall_warned: bool,
}

impl Recorder {
    pub fn new(plan: RecordPlan) -> Self {
        Self { plan, frame: 0, wait: FIRST_SETTLE, started: false, requested: false, left: None, right: None, lines: Vec::new(), fire_lines: Vec::new(), building_lines: Vec::new(), track_lines: Vec::new(), started_at: 0.0, last_frame_at: 0.0, stall_warned: false }
    }
}

#[derive(Component, Clone, Copy)]
enum Eye {
    Left,
    Right,
}

/// GPU readbacks pad each row to 256 bytes.
fn padded_row_bytes(width: u32) -> u32 {
    (width * 4).div_ceil(256) * 256
}

/// An eye readback landed: keep its grey frame, stop reading back.
fn on_eye_read(read: On<ReadbackComplete>, eyes: Query<&Eye>, rig: Res<CameraProfile>, mut recorder: ResMut<Recorder>, mut commands: Commands) {
    let Ok(eye) = eyes.get(read.entity) else { return };
    let pixels = wire::bgra_to_gray8(&read.data, rig.width, rig.height, padded_row_bytes(rig.width));
    match eye {
        Eye::Left if recorder.left.is_none() => recorder.left = Some(pixels),
        Eye::Right if recorder.right.is_none() => recorder.right = Some(pixels),
        _ => {}
    }
    commands.entity(read.entity).despawn();
}

fn save(path: &Path, pixels: Vec<u8>, rig: &CameraProfile, jpeg: bool) {
    let image = GrayImage::from_raw(rig.width, rig.height, pixels).expect("grey frame size");
    if jpeg {
        let file = std::fs::File::create(path).expect("frame file");
        JpegEncoder::new_with_quality(file, 90).encode_image(&image).expect("jpeg frame");
    } else {
        image.save(path).expect("png frame");
    }
}

fn write_capture_files(plan: &RecordPlan, rig: &CameraProfile, truth: &GroundTruth, rec: &Recorder) {
    let (lines, fire_lines, building_lines, track_lines) = (&rec.lines, &rec.fire_lines, &rec.building_lines, &rec.track_lines);
    // The exact profile the eyes rendered with: RTAB-Map's calibration is derived from it.
    std::fs::write(plan.dir.join("camera.json"), serde_json::to_string_pretty(rig).expect("json")).expect("camera.json");
    let calibration = serde_json::json!({
        "calibration_id": rig.id,
        "width": rig.width, "height": rig.height,
        "fx": rig.fx, "fy": rig.fy, "cx": rig.cx, "cy": rig.cy,
        "baseline_m": rig.baseline_m, "rate_hz": plan.rate_hz,
    });
    std::fs::write(plan.dir.join("calibration.json"), serde_json::to_string_pretty(&calibration).expect("json")).expect("calibration.json");
    std::fs::write(plan.dir.join("ground_truth.json"), serde_json::to_string_pretty(&truth.0).expect("json")).expect("ground_truth.json");
    if !fire_lines.is_empty() {
        std::fs::write(plan.dir.join("fire_perimeter.jsonl"), fire_lines.iter().map(|l| format!("{l}\n")).collect::<String>()).expect("fire_perimeter.jsonl");
    }
    if !building_lines.is_empty() {
        std::fs::write(plan.dir.join("building_fires.jsonl"), building_lines.iter().map(|l| format!("{l}\n")).collect::<String>()).expect("building_fires.jsonl");
    }
    std::fs::write(plan.dir.join("object_tracks.jsonl"), track_lines.iter().map(|l| format!("{l}\n")).collect::<String>()).expect("object_tracks.jsonl");
    let mut frames = std::fs::File::create(plan.dir.join("frames.jsonl")).expect("frames.jsonl");
    for line in lines {
        writeln!(frames, "{line}").expect("frames.jsonl line");
    }
}

#[allow(clippy::too_many_arguments)]
pub fn record_frames(
    mut commands: Commands,
    recorder: Option<ResMut<Recorder>>,
    mut sim_time: ResMut<SimTime>,
    scene: Option<Res<SceneState>>,
    assets: Res<AssetServer>,
    pending: Query<(), With<PendingModel>>,
    feeds: Option<Res<StereoFeeds>>,
    rig: Option<Res<CameraProfile>>,
    truth: Res<GroundTruth>,
    fires: Option<Res<Wildfire>>,
    blaze: Option<Res<BuildingBlaze>>,
    figures: Query<&Figure>,
    clock: Res<Time<Real>>,
    mut exit: MessageWriter<AppExit>,
) {
    let (Some(mut rec), Some(scene)) = (recorder, scene) else { return };
    if let Some(why) = &scene.failed {
        error!("scene cannot be built: {why}");
        exit.write(AppExit::error());
        return;
    }
    let (Some(feeds), Some(rig)) = (feeds, rig) else { return };
    if !rec.started {
        if !scene_ready(&scene, &assets, pending.iter().count()) {
            return;
        }
        let dir = rec.plan.dir.clone();
        std::fs::create_dir_all(dir.join("frames/left")).expect("capture dir");
        std::fs::create_dir_all(dir.join("frames/right")).expect("capture dir");
        rec.started = true;
        rec.started_at = clock.elapsed_secs_f64();
        rec.last_frame_at = rec.started_at;
        info!("recording {} frames at {} Hz from t={} s into {}", rec.plan.frames, rec.plan.rate_hz, rec.plan.start_s, dir.display());
        sim_time.0 = Some(rec.plan.t_at(0));
    }
    let now = clock.elapsed_secs_f64();
    if now - rec.last_frame_at > STALL_S && !rec.stall_warned {
        warn!("recording stalled: no frame for {:.0} s at frame {}/{}", now - rec.last_frame_at, rec.frame, rec.plan.frames);
        rec.stall_warned = true;
    }
    if rec.frame == rec.plan.frames {
        write_capture_files(&rec.plan, &rig, &truth, &rec);
        info!("recorded {} frames into {}", rec.frame, rec.plan.dir.display());
        exit.write(AppExit::Success);
        return;
    }
    if rec.wait > 0 {
        rec.wait -= 1;
        return;
    }
    if !rec.requested {
        // Readback works on the offscreen targets whatever the window does
        // (window screenshots stalled with a hidden window).
        for (eye, target) in [(Eye::Left, feeds.left.clone()), (Eye::Right, feeds.right.clone())] {
            commands.spawn((Readback::texture(target), eye)).observe(on_eye_read);
        }
        rec.requested = true;
        return;
    }
    let (Some(left), Some(right)) = (rec.left.take(), rec.right.take()) else { return };
    let frame = rec.frame;
    let t_s = rec.plan.t_at(frame);
    let t_ns = rec.plan.t_ns(frame);
    let ext = if rec.plan.jpeg { "jpg" } else { "png" };
    let (left_ref, right_ref) = (format!("frames/left/{t_ns}.{ext}"), format!("frames/right/{t_ns}.{ext}"));
    save(&rec.plan.dir.join(&left_ref), left, &rig, rec.plan.jpeg);
    save(&rec.plan.dir.join(&right_ref), right, &rig, rec.plan.jpeg);
    let pose = SurveyLoop::disaster_block().pose_at(t_s);
    let pose_enu = wire::rig_pose_enu(pose.position, Quat::from_rotation_y(pose.yaw_rad) * rig.mount_rotation());
    rec.lines.push(
        serde_json::json!({"frame_id": frame + 1, "t_ns": t_ns, "left_ref": left_ref, "right_ref": right_ref, "pose_enu": pose_enu})
            .to_string(),
    );
    if let Some(fires) = fires.as_ref().filter(|f| f.has_fires()) {
        rec.fire_lines.push(fire::perimeter_line(t_ns, &fires.fronts(t_s)));
    }
    if let Some(blaze) = blaze.as_ref() {
        rec.building_lines.push(blaze.record_line(t_ns));
    }
    let wind = fires.as_ref().map_or(Vec2::ZERO, |scene| scene.wind.velocity_enu(t_s));
    let bodies: Vec<actors::Body> = figures.iter().filter_map(Figure::body).collect();
    rec.track_lines.push(actors::track_line(t_ns, wind, &bodies));
    rec.frame += 1;
    rec.last_frame_at = now;
    rec.stall_warned = false;
    if rec.frame % PROGRESS_EVERY == 0 || rec.frame == rec.plan.frames {
        let rate = f64::from(rec.frame) / (now - rec.started_at).max(1e-6);
        info!("recorded frame {}/{} (sim t={:.1} s) at {:.2} frames/s", rec.frame, rec.plan.frames, t_s, rate);
    }
    rec.requested = false;
    rec.wait = STEP_SETTLE;
    sim_time.0 = Some(rec.plan.t_at(rec.frame));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frames_are_spaced_by_the_capture_rate_from_the_start() {
        let plan = RecordPlan { dir: PathBuf::from("c"), frames: 3, rate_hz: 10.0, start_s: 30.0, jpeg: false };

        assert_eq!([plan.t_at(0), plan.t_at(1), plan.t_at(2)], [30.0, 30.1, 30.2]);
    }

    #[test]
    fn readback_rows_are_padded_to_256_bytes() {
        assert_eq!((padded_row_bytes(640), padded_row_bytes(100)), (2560, 512));
    }

    #[test]
    fn timestamps_are_whole_steps_of_the_rate_in_nanoseconds() {
        let plan = RecordPlan { dir: PathBuf::from("c"), frames: 3, rate_hz: 10.0, start_s: 30.0, jpeg: false };

        assert_eq!([plan.t_ns(0), plan.t_ns(4)], [30_000_000_000, 30_400_000_000]);
    }
}
