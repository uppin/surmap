//! The chat's preview of the simulation (`?view=preview`), pure: one view and nothing else on
//! the page — the overview (the chase view, with its PTZ) while the viewed drone is on the
//! ground, its first-person camera once it flies. In the air the FPV shows the frame RTAB-Map
//! processed with that frame's tracked keypoints: a sent frame is held until its odometry comes
//! back (`HeldFrames`), so the view may lag the live camera but points never sit on another
//! frame. The Bevy systems that draw it are `preview_ui`.

use std::collections::VecDeque;

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

use crate::calibration::CameraProfile;
use crate::fleet::autopilot::Phase;
use crate::fleet::{ActiveDrone, Fleet};
use crate::{Flight, StereoFeeds};

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

/// A GPU readback of a BGRA eye (rows padded to `row_bytes`) as tight RGBA rows.
#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
pub fn bgra_to_rgba(bgra: &[u8], width: u32, height: u32, row_bytes: u32) -> Vec<u8> {
    let (w, stride) = (width as usize, row_bytes as usize);
    let mut out = Vec::with_capacity(w * height as usize * 4);
    for row in 0..height as usize {
        for pixel in bgra[row * stride..row * stride + w * 4].chunks_exact(4) {
            out.extend_from_slice(&[pixel[2], pixel[1], pixel[0], pixel[3]]);
        }
    }
    out
}

/// The sent frames still waiting for their odometry, oldest first, at most `capacity`.
#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
#[derive(Debug, Clone, PartialEq)]
pub struct HeldFrames {
    capacity: usize,
    frames: VecDeque<(u64, Vec<u8>)>,
}

#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
impl HeldFrames {
    /// Holds at most `capacity` frames; holding one more drops the oldest.
    pub fn new(capacity: usize) -> Self {
        Self { capacity, frames: VecDeque::new() }
    }

    /// Holds `pixels`, the frame sent as `frame_id`.
    pub fn hold(&mut self, frame_id: u64, pixels: Vec<u8>) {
        if self.frames.len() == self.capacity {
            self.frames.pop_front();
        }
        self.frames.push_back((frame_id, pixels));
    }

    /// The pixels of `frame_id`, whose odometry came back; it and every older frame stop being
    /// held (their odometry, if it ever comes, is stale). `None` when it is not held.
    pub fn take(&mut self, frame_id: u64) -> Option<Vec<u8>> {
        let position = self.frames.iter().position(|(id, _)| *id == frame_id)?;
        let (_, pixels) = self.frames.drain(..=position).last().expect("position is in range");
        Some(pixels)
    }

    /// The ids of the frames held, oldest first.
    #[cfg(test)]
    pub fn held(&self) -> Vec<u64> {
        self.frames.iter().map(|(id, _)| *id).collect()
    }
}

/// How many sent frames wait for their odometry; RTAB-Map answering later drops the frame.
#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
pub const HELD_FRAMES: usize = 12;

/// The FPV frame RTAB-Map processed last, with its keypoints (`[u, v, depth_m]`, raw pixels):
/// the bridge stream writes it once a held frame's odometry came back.
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct FpvFrame {
    /// The frame's tight RGBA rows, at the camera profile's size.
    pub rgba: Vec<u8>,
    pub keypoints: Vec<[f32; 3]>,
}

/// The preview's full-window layer over the chase view; shown in FPV.
#[derive(Component)]
pub struct PreviewFpv;

/// The FPV image, at the camera's aspect ratio.
#[derive(Component)]
pub struct PreviewImage;

/// The layer of keypoint dots over the FPV image.
#[derive(Component)]
pub struct PreviewDots;

/// The image an `FpvFrame` is drawn into.
#[derive(Resource)]
struct HeldFeed(Handle<Image>);

/// The keypoint dot's side, px.
const DOT_PX: f32 = 5.0;

/// The preview's systems; the page spawns none of the full page's UI in this mode.
pub struct PreviewPlugin;

impl Plugin for PreviewPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, setup_preview.run_if(resource_added::<StereoFeeds>))
            .add_systems(Update, (switch_preview, show_fpv_frame).after(setup_preview));
    }
}

/// The FPV layer: hidden, the live left eye until RTAB-Map's first frame comes back.
fn setup_preview(
    mut commands: Commands,
    feeds: Res<StereoFeeds>,
    rig: Res<CameraProfile>,
    mut images: ResMut<Assets<Image>>,
) {
    let held = images.add(Image::new_fill(
        Extent3d { width: rig.width, height: rig.height, depth_or_array_layers: 1 },
        TextureDimension::D2,
        &[0, 0, 0, 255],
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::default(),
    ));
    commands.insert_resource(HeldFeed(held));
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
                    PreviewImage,
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
                        PreviewDots,
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
    mut layer: Query<&mut Visibility, With<PreviewFpv>>,
) {
    let active_id = active.as_ref().and_then(|a| a.0.as_deref());
    let phase = fleet.as_ref().and_then(|fleet| {
        let id = active_id?;
        fleet.autopilots.iter().find(|pilot| pilot.id() == id).map(|pilot| pilot.state().phase)
    });
    let shown = match preview_view(phase, flight.engaged) {
        PreviewView::Overview => Visibility::Hidden,
        PreviewView::Fpv => Visibility::Inherited,
    };
    for mut visibility in &mut layer {
        visibility.set_if_neq(shown);
    }
}

/// Draws a new `FpvFrame`: its pixels into the held image (shown in place of the live eye from
/// then on), its keypoints as dots placed as fractions of the frame, coloured by depth.
fn show_fpv_frame(
    mut commands: Commands,
    frame: Option<Res<FpvFrame>>,
    held: Option<Res<HeldFeed>>,
    rig: Option<Res<CameraProfile>>,
    mut images: ResMut<Assets<Image>>,
    mut image_nodes: Query<&mut ImageNode, With<PreviewImage>>,
    dots: Query<Entity, With<PreviewDots>>,
) {
    let (Some(frame), Some(held), Some(rig)) = (frame, held, rig) else { return };
    if !frame.is_changed() {
        return;
    }
    if let Some(image) = images.get_mut(&held.0) {
        image.data = Some(frame.rgba.clone());
    }
    for mut node in &mut image_nodes {
        if node.image != held.0 {
            node.image = held.0.clone();
        }
    }
    let Ok(layer) = dots.single() else { return };
    commands.entity(layer).despawn_related::<Children>();
    commands.entity(layer).with_children(|layer| {
        for [u, v, depth] in &frame.keypoints {
            let [r, g, b] = depth_colour(*depth);
            layer.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: Val::Percent(u / rig.width as f32 * 100.0),
                    top: Val::Percent(v / rig.height as f32 * 100.0),
                    width: Val::Px(DOT_PX),
                    height: Val::Px(DOT_PX),
                    margin: UiRect { left: Val::Px(-DOT_PX / 2.0), top: Val::Px(-DOT_PX / 2.0), ..default() },
                    ..default()
                },
                BackgroundColor(Color::srgb_u8(r, g, b)),
            ));
        }
    });
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
    fn a_padded_bgra_readback_becomes_tight_rgba_rows() {
        // Two 1-pixel rows, each padded to 8 bytes.
        let bgra = [1, 2, 3, 4, 0, 0, 0, 0, 5, 6, 7, 8, 0, 0, 0, 0];

        assert_eq!(bgra_to_rgba(&bgra, 1, 2, 8), vec![3, 2, 1, 4, 7, 6, 5, 8]);
    }

    #[test]
    fn a_frame_whose_odometry_came_back_is_taken_with_its_pixels() {
        let mut held = HeldFrames::new(4);
        held.hold(7, vec![7; 3]);
        held.hold(8, vec![8; 3]);

        assert_eq!(held.take(7), Some(vec![7; 3]));
        assert_eq!(held.held(), vec![8]);
    }

    #[test]
    fn taking_a_frame_drops_the_older_ones() {
        let mut held = HeldFrames::new(4);
        for id in [5, 6, 7] {
            held.hold(id, vec![id as u8]);
        }

        assert_eq!(held.take(6), Some(vec![6]));
        assert_eq!(held.held(), vec![7]);
        assert_eq!(held.take(5), None);
    }

    #[test]
    fn holding_past_the_capacity_drops_the_oldest_frame() {
        let mut held = HeldFrames::new(2);
        for id in [1, 2, 3] {
            held.hold(id, vec![id as u8]);
        }

        assert_eq!(held.held(), vec![2, 3]);
        assert_eq!(held.take(1), None);
    }
}
