//! The chat's preview of the simulation (`?view=preview`), pure: one view and nothing else on
//! the page — the overview (the chase view, with its PTZ) while the viewed drone is on the
//! ground, its first-person camera once it flies. In the air the FPV is the live left eye, never
//! waiting on the station: RTAB-Map's keypoints of a recent frame (`fresh_keypoints`) are drawn
//! over it as one overlay image (`keypoint_overlay`). Only the cameras the view shows render,
//! plus both eyes in a frame whose pair the stream reads back (`preview_renders`).

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

use crate::calibration::CameraProfile;
use crate::fleet::autopilot::Phase;
use crate::fleet::stream::{BridgeStreamSet, FrameKeypoints};
use crate::fleet::{ActiveDrone, Fleet};
use crate::{ChaseCam, Flight, LeftEye, RightEye, StereoFeeds};

/// How the page shows the simulation.
#[derive(Resource, Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ViewMode {
    /// The full page: chase view, stereo panel, HUD and the Take off button.
    #[default]
    Full,
    /// The chat's preview: one view, edge to edge.
    Preview,
}

/// The page's view mode (`?view=`, wasm); natively `--view preview` sets it.
#[cfg(target_arch = "wasm32")]
pub fn page_view_mode(_args: &[String]) -> ViewMode {
    web_sys::window()
        .and_then(|window| window.location().search().ok())
        .map_or(ViewMode::Full, |search| view_mode(&search))
}

#[cfg(not(target_arch = "wasm32"))]
pub fn page_view_mode(args: &[String]) -> ViewMode {
    let named = args.windows(2).any(|pair| pair[0] == "--view" && pair[1] == "preview");
    if named { ViewMode::Preview } else { ViewMode::Full }
}

/// The view mode a page URL's query (`location.search`) names: `view=preview`.
#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
pub fn view_mode(search: &str) -> ViewMode {
    let preview = search.trim_start_matches('?').split('&').any(|pair| pair == "view=preview");
    if preview { ViewMode::Preview } else { ViewMode::Full }
}

/// What the preview shows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreviewView {
    /// The chase view orbiting the drone, with the trackpad PTZ.
    Overview,
    /// The drone's left camera, full frame.
    Fpv,
}

/// The preview's view: the viewed fleet drone's `phase` when one is viewed (`Docked` is on the
/// ground), else whether the keyboard drone is engaged.
pub fn preview_view(fleet_phase: Option<Phase>, engaged: bool) -> PreviewView {
    let flying = match fleet_phase {
        Some(phase) => phase != Phase::Docked,
        None => engaged,
    };
    if flying { PreviewView::Fpv } else { PreviewView::Overview }
}

/// The depth ramp's colours, near to far: the demo page's (`surmap.demo.view_math`).
const DEPTH_STOPS: [[f32; 3]; 5] =
    [[255.0, 72.0, 40.0], [255.0, 200.0, 40.0], [80.0, 230.0, 120.0], [40.0, 170.0, 255.0], [120.0, 90.0, 255.0]];
/// The depths the ramp spans, metres; it runs on a log scale, as outdoor depth spans decades.
const NEAR_M: f32 = 1.0;
const FAR_M: f32 = 60.0;

/// A keypoint's colour by its depth: near red, through yellow and green, to far blue.
pub fn depth_colour(depth_m: f32) -> [u8; 3] {
    let t = ((depth_m.max(NEAR_M) / NEAR_M).ln() / (FAR_M / NEAR_M).ln()).clamp(0.0, 1.0);
    let scaled = t * (DEPTH_STOPS.len() - 1) as f32;
    let i = (scaled.floor() as usize).min(DEPTH_STOPS.len() - 2);
    let f = scaled - i as f32;
    let (a, b) = (DEPTH_STOPS[i], DEPTH_STOPS[i + 1]);
    [0, 1, 2].map(|k| (a[k] + (b[k] - a[k]) * f).round() as u8)
}

/// Which of the preview's cameras render this frame.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Renders {
    pub chase: bool,
    pub left: bool,
    pub right: bool,
}

/// The cameras `view` shows, plus both eyes when the stream reads a pair back this frame
/// (`pair_due`): nothing renders that nobody sees or reads.
pub fn preview_renders(view: PreviewView, pair_due: bool) -> Renders {
    Renders {
        chase: view == PreviewView::Overview,
        left: view == PreviewView::Fpv || pair_due,
        right: pair_due,
    }
}

/// How many frames the stream may have sent since the one an answer is for, for its keypoints
/// still to be drawn over the live eye: 200 ms at 10 Hz.
pub const FRESH_FRAMES: u64 = 2;

/// The keypoints of `answer` while its frame is at most `FRESH_FRAMES` behind `last_sent`, the
/// last frame the stream sent; none before any answer or once it is stale.
pub fn fresh_keypoints(answer: Option<&FrameKeypoints>, last_sent: u64) -> Option<&[[f32; 3]]> {
    answer.filter(|answer| answer.frame_id + FRESH_FRAMES >= last_sent).map(|answer| &answer.keypoints[..])
}

/// The keypoint dot's side, camera pixels.
const DOT_PX: i64 = 5;

/// `keypoints` (`[u, v, depth_m]`, raw left-camera pixels) as tight RGBA rows of a `width` x
/// `height` image: an opaque `DOT_PX` square per keypoint in its depth colour, transparent
/// elsewhere; a dot at the edge is clipped.
pub fn keypoint_overlay(width: u32, height: u32, keypoints: &[[f32; 3]]) -> Vec<u8> {
    let (w, h) = (i64::from(width), i64::from(height));
    let mut rgba = vec![0u8; (w * h * 4) as usize];
    for [u, v, depth] in keypoints {
        let [r, g, b] = depth_colour(*depth);
        let (cx, cy) = (u.floor() as i64, v.floor() as i64);
        for y in (cy - DOT_PX / 2).max(0)..(cy + DOT_PX / 2 + 1).min(h) {
            for x in (cx - DOT_PX / 2).max(0)..(cx + DOT_PX / 2 + 1).min(w) {
                let i = ((y * w + x) * 4) as usize;
                rgba[i..i + 4].copy_from_slice(&[r, g, b, 255]);
            }
        }
    }
    rgba
}

/// The keypoints drawn over the FPV now: the bridge stream writes them when the fresh answer
/// changes (empty once it is stale).
#[derive(Resource, Debug, Clone, Default, PartialEq)]
pub struct FpvKeypoints(pub Vec<[f32; 3]>);

/// Set by the bridge stream in a frame whose pair it reads back, so both eyes render that frame.
#[derive(Resource, Debug, Default)]
pub struct PairDue(pub bool);

/// The preview's full-window layer over the chase view; shown in FPV.
#[derive(Component)]
pub struct PreviewFpv;

/// The keypoint overlay's image, over the live eye.
#[derive(Resource)]
struct Overlay(Handle<Image>);

/// The view the preview shows this frame (`switch_preview`).
#[derive(Resource, Debug, Clone, Copy, PartialEq, Eq)]
struct Shown(PreviewView);

/// The preview's systems; the page spawns none of the full page's UI in this mode.
pub struct PreviewPlugin;

impl Plugin for PreviewPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Shown(PreviewView::Overview))
            .init_resource::<PairDue>()
            .add_systems(Update, setup_preview.run_if(resource_added::<StereoFeeds>))
            .add_systems(Update, (switch_preview, show_keypoints).after(setup_preview))
            .add_systems(Update, render_only_what_is_seen.after(switch_preview).after(BridgeStreamSet));
    }
}

/// The FPV layer, hidden: the live left eye with the keypoint overlay over it.
fn setup_preview(
    mut commands: Commands,
    feeds: Res<StereoFeeds>,
    rig: Res<CameraProfile>,
    mut images: ResMut<Assets<Image>>,
) {
    let overlay = images.add(Image::new_fill(
        Extent3d { width: rig.width, height: rig.height, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &[0, 0, 0, 0],
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::default(),
    ));
    commands.insert_resource(Overlay(overlay.clone()));
    commands
        .spawn((
            PreviewFpv,
            Node {
                position_type: PositionType::Absolute,
                width: Val::Percent(100.0),
                height: Val::Percent(100.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundColor(Color::BLACK),
            Visibility::Hidden,
        ))
        .with_children(|layer| {
            layer
                .spawn((
                    ImageNode::new(feeds.left.clone()),
                    Node {
                        height: Val::Percent(100.0),
                        max_width: Val::Percent(100.0),
                        aspect_ratio: Some(rig.width as f32 / rig.height as f32),
                        ..default()
                    },
                ))
                .with_children(|image| {
                    image.spawn((
                        ImageNode::new(overlay),
                        Node {
                            position_type: PositionType::Absolute,
                            width: Val::Percent(100.0),
                            height: Val::Percent(100.0),
                            ..default()
                        },
                    ));
                });
        });
}

/// Overview on the ground, FPV in the air: the viewed fleet drone's phase, else the keyboard
/// drone's engagement.
fn switch_preview(
    fleet: Option<Res<Fleet>>,
    active: Option<Res<ActiveDrone>>,
    flight: Res<Flight>,
    mut shown: ResMut<Shown>,
    mut layer: Query<&mut Visibility, With<PreviewFpv>>,
) {
    let active_id = active.as_ref().and_then(|a| a.0.as_deref());
    let phase = fleet.as_ref().and_then(|fleet| {
        let id = active_id?;
        fleet.autopilots.iter().find(|pilot| pilot.id() == id).map(|pilot| pilot.state().phase)
    });
    let view = preview_view(phase, flight.engaged);
    shown.set_if_neq(Shown(view));
    let visibility = match view {
        PreviewView::Overview => Visibility::Hidden,
        PreviewView::Fpv => Visibility::Inherited,
    };
    for mut layer in &mut layer {
        layer.set_if_neq(visibility);
    }
}

/// Switches each preview camera on only when `preview_renders` says it is seen or read back.
fn render_only_what_is_seen(
    shown: Res<Shown>,
    mut due: ResMut<PairDue>,
    mut cameras: Query<(&mut Camera, Has<ChaseCam>, Has<LeftEye>, Has<RightEye>)>,
) {
    let renders = preview_renders(shown.0, due.0);
    due.0 = false;
    for (mut camera, chase, left, right) in &mut cameras {
        let active = if chase {
            renders.chase
        } else if left {
            renders.left
        } else if right {
            renders.right
        } else {
            continue;
        };
        if camera.is_active != active {
            camera.is_active = active;
        }
    }
}

/// Draws the keypoints into the overlay whenever the bridge stream changes them.
fn show_keypoints(
    keypoints: Option<Res<FpvKeypoints>>,
    overlay: Option<Res<Overlay>>,
    rig: Option<Res<CameraProfile>>,
    mut images: ResMut<Assets<Image>>,
) {
    let (Some(keypoints), Some(overlay), Some(rig)) = (keypoints, overlay, rig) else { return };
    if !keypoints.is_changed() {
        return;
    }
    if let Some(image) = images.get_mut(&overlay.0) {
        image.data = Some(keypoint_overlay(rig.width, rig.height, &keypoints.0));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_page_opened_with_view_preview_is_the_preview() {
        assert_eq!(view_mode("?scenario=quake&view=preview&fleet=1"), ViewMode::Preview);
    }

    #[test]
    fn a_page_without_a_view_is_the_full_page() {
        assert_eq!(view_mode("?scenario=quake&fleet=1"), ViewMode::Full);
        assert_eq!(view_mode(""), ViewMode::Full);
        assert_eq!(view_mode("?view=other"), ViewMode::Full);
    }

    #[test]
    fn a_docked_fleet_drone_is_seen_from_the_overview() {
        assert_eq!(preview_view(Some(Phase::Docked), false), PreviewView::Overview);
    }

    #[test]
    fn a_fleet_drone_in_the_air_is_seen_through_its_camera() {
        for phase in [
            Phase::Climbing,
            Phase::Cruising,
            Phase::Detouring,
            Phase::Hovering,
            Phase::Returning,
            Phase::Landing,
        ] {
            assert_eq!(preview_view(Some(phase), false), PreviewView::Fpv, "{phase:?}");
        }
    }

    #[test]
    fn the_viewed_fleet_drone_decides_even_when_the_keyboard_drone_is_engaged() {
        assert_eq!(preview_view(Some(Phase::Docked), true), PreviewView::Overview);
    }

    #[test]
    fn without_a_fleet_the_keyboard_drone_flies_into_fpv_once_engaged() {
        assert_eq!(preview_view(None, false), PreviewView::Overview);
        assert_eq!(preview_view(None, true), PreviewView::Fpv);
    }

    #[test]
    fn near_keypoints_are_red_and_far_ones_blue() {
        let near = depth_colour(0.5);
        let far = depth_colour(500.0);
        assert!(near[0] > 200 && near[2] < 80, "near {near:?}");
        assert!(far[2] > 200 && far[0] < 140, "far {far:?}");
    }

    #[test]
    fn a_keypoint_colour_shifts_steadily_from_near_to_far() {
        assert_ne!(depth_colour(3.0), depth_colour(10.0));
        assert_ne!(depth_colour(10.0), depth_colour(30.0));
    }

    #[test]
    fn the_overview_renders_only_the_chase_view() {
        assert_eq!(preview_renders(PreviewView::Overview, false), Renders { chase: true, left: false, right: false });
    }

    #[test]
    fn the_fpv_renders_only_the_left_eye_not_the_hidden_chase_view() {
        assert_eq!(preview_renders(PreviewView::Fpv, false), Renders { chase: false, left: true, right: false });
    }

    #[test]
    fn a_frame_whose_pair_is_due_also_renders_both_eyes() {
        assert_eq!(preview_renders(PreviewView::Overview, true), Renders { chase: true, left: true, right: true });
        assert_eq!(preview_renders(PreviewView::Fpv, true), Renders { chase: false, left: true, right: true });
    }

    fn an_answer(frame_id: u64) -> FrameKeypoints {
        FrameKeypoints { frame_id, keypoints: vec![[3.0, 2.0, 4.0]] }
    }

    #[test]
    fn keypoints_of_a_recent_frame_are_shown_over_the_live_eye() {
        let answer = an_answer(8);

        assert_eq!(fresh_keypoints(Some(&answer), 8 + FRESH_FRAMES), Some(&answer.keypoints[..]));
    }

    #[test]
    fn keypoints_of_a_frame_the_station_answered_too_late_are_not_shown() {
        let answer = an_answer(8);

        assert_eq!(fresh_keypoints(Some(&answer), 9 + FRESH_FRAMES), None);
    }

    #[test]
    fn before_any_answer_no_keypoints_are_shown() {
        assert_eq!(fresh_keypoints(None, 3), None);
    }

    /// The overlay's RGBA pixel at `(x, y)`.
    fn pixel(overlay: &[u8], width: u32, x: u32, y: u32) -> [u8; 4] {
        let i = ((y * width + x) * 4) as usize;
        [overlay[i], overlay[i + 1], overlay[i + 2], overlay[i + 3]]
    }

    #[test]
    fn the_overlay_is_transparent_away_from_the_keypoints() {
        let overlay = keypoint_overlay(16, 12, &[[3.0, 2.0, 4.0]]);

        assert_eq!(pixel(&overlay, 16, 12, 9), [0, 0, 0, 0]);
    }

    #[test]
    fn a_keypoint_is_an_opaque_dot_in_its_depth_colour() {
        let overlay = keypoint_overlay(16, 12, &[[6.0, 5.0, 4.0]]);
        let [r, g, b] = depth_colour(4.0);

        assert_eq!(pixel(&overlay, 16, 6, 5), [r, g, b, 255]);
        assert_eq!(pixel(&overlay, 16, 8, 7), [r, g, b, 255]);
        assert_eq!(pixel(&overlay, 16, 9, 5), [0, 0, 0, 0]);
    }

    #[test]
    fn a_dot_at_the_frame_edge_is_clipped_to_the_frame() {
        let overlay = keypoint_overlay(16, 12, &[[0.0, 11.5, 4.0]]);

        assert_eq!(overlay.len(), 16 * 12 * 4);
        assert_eq!(pixel(&overlay, 16, 0, 11)[3], 255);
    }
}
