//! The chat's preview of the simulation (`?view=preview`), pure: one view and nothing else on
//! the page — the overview (the chase view, with its PTZ) while the viewed drone is on the
//! ground, its first-person camera once it flies. In the air the FPV shows the frame RTAB-Map
//! processed with that frame's tracked keypoints: a sent frame is held until its odometry comes
//! back (`HeldFrames`), so the view may lag the live camera but points never sit on another
//! frame. When the agent runs an on-board model (`set_onboard_model`), the frame's detections are
//! outlined on it, each with a label card laid out as the demo page's SAM cards are
//! (`layout_cards`): near its object, joined by a leader, never overlapping another card.

use std::collections::VecDeque;

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

use crate::calibration::CameraProfile;
use crate::fleet::autopilot::Phase;
use crate::fleet::stream::DetectedObject;
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

/// What the page holds of each sent frame until its odometry comes back — its pixels, or what
/// the on-board model found on it — oldest first, at most `capacity`.
#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
#[derive(Debug, Clone, PartialEq)]
pub struct HeldFrames<T = Vec<u8>> {
    capacity: usize,
    frames: VecDeque<(u64, T)>,
}

#[cfg_attr(not(target_arch = "wasm32"), allow(dead_code))]
impl<T> HeldFrames<T> {
    /// Holds at most `capacity` frames; holding one more drops the oldest.
    pub fn new(capacity: usize) -> Self {
        Self { capacity, frames: VecDeque::new() }
    }

    /// Holds `pixels`, what the page keeps of the frame sent as `frame_id`.
    pub fn hold(&mut self, frame_id: u64, pixels: T) {
        if self.frames.len() == self.capacity {
            self.frames.pop_front();
        }
        self.frames.push_back((frame_id, pixels));
    }

    /// The pixels of `frame_id`, whose odometry came back; it and every older frame stop being
    /// held (their odometry, if it ever comes, is stale). `None` when it is not held.
    pub fn take(&mut self, frame_id: u64) -> Option<T> {
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

/// The FPV frame RTAB-Map processed last, with its keypoints (`[u, v, depth_m]`, raw pixels)
/// and what the on-board model found on it: the bridge stream writes it once a held frame's
/// odometry came back.
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct FpvFrame {
    /// The frame's tight RGBA rows, at the camera profile's size.
    pub rgba: Vec<u8>,
    pub keypoints: Vec<[f32; 3]>,
    pub detections: Vec<DetectedObject>,
}

/// The colour of a detection's outline, leader and card border: the demo's SAM card cyan.
pub const DETECTION_COLOUR: [u8; 3] = [34, 211, 238];
/// A card's text size, logical px; Bevy's default font is monospaced, `CHAR_EM` of it per glyph.
pub const CARD_FONT_PX: f32 = 11.0;
const CHAR_EM: f32 = 0.6;
/// A one-line card's height and its text's horizontal padding, px (the demo's cards).
pub const CARD_HEIGHT_PX: f32 = 19.0;
const CARD_PADDING_PX: f32 = 6.0;
/// The image margin a card keeps, the gap between cards (and to their object), and the grid
/// step of the free spots tried: the demo's `CARD_MARGIN_PX`, `CARD_GAP_PX`, `CARD_GRID_PX`.
const CARD_MARGIN_PX: f32 = 4.0;
const CARD_GAP_PX: f32 = 4.0;
const CARD_GRID_PX: f32 = 4.0;

/// A label card to place, display px: its object's `anchor` (where the leader ends) and box
/// `[x0, y0, x1, y1]`, and the card's size.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CardItem {
    pub anchor: [f32; 2],
    pub bbox: [f32; 4],
    pub width: f32,
    pub height: f32,
}

/// A placed card, display px: its top-left and size, and its leader from the card's edge
/// (`from`) to its object's anchor (`to`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Card {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub from: [f32; 2],
    pub to: [f32; 2],
}

/// The demo page's `layoutCards`: each card as close to its own object as it fits — just above
/// it when free, else the nearest free spot (below, beside, then a grid) — never overlapping
/// another card and inside the `width` x `height` image. The smallest objects are placed first:
/// they have the fewest free spots near them. Cards come back in `items`' order.
pub fn layout_cards(items: &[CardItem], width: f32, height: f32) -> Vec<Card> {
    let area = |b: [f32; 4]| (b[2] - b[0]) * (b[3] - b[1]);
    let mut order: Vec<usize> = (0..items.len()).collect();
    order.sort_by(|&a, &b| area(items[a].bbox).total_cmp(&area(items[b].bbox)).then(a.cmp(&b)));
    let mut laid: Vec<Option<Card>> = vec![None; items.len()];
    let mut placed: Vec<Card> = Vec::with_capacity(items.len());
    for i in order {
        let CardItem { anchor, bbox: [bx1, by1, bx2, by2], width: w, height: h } = items[i];
        let (cx, cy) = ((bx1 + bx2) / 2.0, (by1 + by2) / 2.0);
        let max_x = CARD_MARGIN_PX.max(width - CARD_MARGIN_PX - w);
        let max_y = CARD_MARGIN_PX.max(height - CARD_MARGIN_PX - h);
        let clamp = |[x, y]: [f32; 2]| [x.max(CARD_MARGIN_PX).min(max_x), y.max(CARD_MARGIN_PX).min(max_y)];
        // Just above, below, left and right of the box; then every free spot on a grid.
        let mut candidates: Vec<[f32; 2]> = [
            [cx - w / 2.0, by1 - CARD_GAP_PX - h],
            [cx - w / 2.0, by2 + CARD_GAP_PX],
            [bx1 - CARD_GAP_PX - w, cy - h / 2.0],
            [bx2 + CARD_GAP_PX, cy - h / 2.0],
        ]
        .map(clamp)
        .to_vec();
        let mut y = CARD_MARGIN_PX;
        while y <= max_y {
            let mut x = CARD_MARGIN_PX;
            while x <= max_x {
                candidates.push([x, y]);
                x += CARD_GRID_PX;
            }
            y += CARD_GRID_PX;
        }
        let (mut best, mut best_score) = (candidates[0], f32::INFINITY);
        for [x, y] in candidates {
            let crowded = placed.iter().any(|p| {
                x < p.x + p.width + CARD_GAP_PX
                    && p.x < x + w + CARD_GAP_PX
                    && y < p.y + p.height + CARD_GAP_PX
                    && p.y < y + h + CARD_GAP_PX
            });
            if crowded {
                continue;
            }
            let dx = (bx1 - (x + w)).max(x - bx2).max(0.0);
            let dy = (by1 - (y + h)).max(y - by2).max(0.0);
            let covers = x < bx2 && bx1 < x + w && y < by2 && by1 < y + h;
            // Touching (within the gap) is as close as it gets; then the most centred above it.
            let score = dx.hypot(dy).max(CARD_GAP_PX)
                + if covers { 1e4 } else { 0.0 }
                + 1e-3 * (x + w / 2.0 - cx).abs()
                + 1e-4 * (y - by1).max(0.0);
            if score < best_score {
                (best, best_score) = ([x, y], score);
            }
        }
        let [x, y] = best;
        let card = Card {
            x,
            y,
            width: w,
            height: h,
            from: [anchor[0].max(x).min(x + w), anchor[1].max(y).min(y + h)],
            to: anchor,
        };
        placed.push(card);
        laid[i] = Some(card);
    }
    laid.into_iter().map(|card| card.expect("every item is placed")).collect()
}

/// A detection's card text: `<label> #<track> <score>%`.
pub fn card_text(object: &DetectedObject) -> String {
    format!("{} #{} {}%", object.label, object.track_id, (object.score * 100.0).round() as u32)
}

/// A detection's card to place in display px, its frame-pixel box scaled by `scale` (display px
/// per frame px); the card is sized to its text.
pub fn card_item(object: &DetectedObject, scale: f32) -> CardItem {
    let bbox = object.box_xyxy.map(|corner| corner * scale);
    let glyphs = card_text(object).chars().count() as f32;
    CardItem {
        anchor: [(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0],
        bbox,
        width: (glyphs * CARD_FONT_PX * CHAR_EM).round() + 2.0 * CARD_PADDING_PX,
        height: CARD_HEIGHT_PX,
    }
}

/// Draws into tight RGBA rows (`width` x `height`) each box's outline and each leader with a dot
/// at either end, `line_px` thick, in `DETECTION_COLOUR`; frame pixels throughout.
pub fn draw_detections(
    rgba: &mut [u8],
    width: u32,
    height: u32,
    boxes: &[[f32; 4]],
    leaders: &[([f32; 2], [f32; 2])],
    line_px: u32,
) {
    let mut paint = |x: i64, y: i64| {
        if (0..i64::from(width)).contains(&x) && (0..i64::from(height)).contains(&y) {
            let i = ((y as usize) * width as usize + x as usize) * 4;
            let [r, g, b] = DETECTION_COLOUR;
            rgba[i..i + 4].copy_from_slice(&[r, g, b, 255]);
        }
    };
    let line = line_px.max(1) as i64;
    let stroke = |[ax, ay]: [f32; 2], [bx, by]: [f32; 2], paint: &mut dyn FnMut(i64, i64)| {
        // Stamped every half pixel along the segment, `line` pixels square.
        let steps = ((bx - ax).abs().max((by - ay).abs()) * 2.0).ceil() as i64 + 1;
        for step in 0..=steps {
            let t = step as f32 / steps as f32;
            let x0 = (ax + (bx - ax) * t - (line - 1) as f32 / 2.0).floor() as i64;
            let y0 = (ay + (by - ay) * t - (line - 1) as f32 / 2.0).floor() as i64;
            for dy in 0..line {
                for dx in 0..line {
                    paint(x0 + dx, y0 + dy);
                }
            }
        }
    };
    for &[x0, y0, x1, y1] in boxes {
        for (a, b) in [([x0, y0], [x1, y0]), ([x1, y0], [x1, y1]), ([x1, y1], [x0, y1]), ([x0, y1], [x0, y0])] {
            stroke(a, b, &mut paint);
        }
    }
    let radius = 2.0 * line as f32;
    for &(from, to) in leaders {
        stroke(from, to, &mut paint);
        for [cx, cy] in [from, to] {
            let reach = radius.ceil() as i64;
            for y in (cy as i64 - reach)..=(cy as i64 + reach) {
                for x in (cx as i64 - reach)..=(cx as i64 + reach) {
                    if (x as f32 + 0.5 - cx).hypot(y as f32 + 0.5 - cy) <= radius {
                        paint(x, y);
                    }
                }
            }
        }
    }
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

/// The layer of detection label cards over the FPV image.
#[derive(Component)]
pub struct PreviewCards;

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
                    let layer = || Node {
                        position_type: PositionType::Absolute,
                        width: Val::Percent(100.0),
                        height: Val::Percent(100.0),
                        ..default()
                    };
                    image.spawn((PreviewDots, layer()));
                    image.spawn((PreviewCards, layer()));
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

/// Draws a new `FpvFrame`, and again when the image's displayed size changes: its pixels with
/// each detection's box and card leader drawn in, into the held image (shown in place of the
/// live eye from then on); its keypoints as dots placed as fractions of the frame, coloured by
/// depth; and a label card per detection, laid out in display pixels so cards never overlap at
/// any preview size.
#[allow(clippy::too_many_arguments)]
fn show_fpv_frame(
    mut commands: Commands,
    frame: Option<Res<FpvFrame>>,
    held: Option<Res<HeldFeed>>,
    rig: Option<Res<CameraProfile>>,
    mut images: ResMut<Assets<Image>>,
    mut image_nodes: Query<(&mut ImageNode, &ComputedNode), With<PreviewImage>>,
    dots: Query<Entity, With<PreviewDots>>,
    cards: Query<Entity, With<PreviewCards>>,
    mut shown_at: Local<Vec2>,
) {
    let (Some(frame), Some(held), Some(rig)) = (frame, held, rig) else { return };
    let Ok((mut node, computed)) = image_nodes.single_mut() else { return };
    let display = computed.size() * computed.inverse_scale_factor();
    if !frame.is_changed() && display == *shown_at {
        return;
    }
    *shown_at = display;
    let scale = if display.x > 0.0 { display.x / rig.width as f32 } else { 1.0 };
    let items: Vec<CardItem> = frame.detections.iter().map(|object| card_item(object, scale)).collect();
    let laid = layout_cards(&items, display.x, display.y);
    if let Some(image) = images.get_mut(&held.0) {
        let mut rgba = frame.rgba.clone();
        let boxes: Vec<[f32; 4]> = frame.detections.iter().map(|object| object.box_xyxy).collect();
        let leaders: Vec<([f32; 2], [f32; 2])> =
            laid.iter().map(|card| (card.from.map(|v| v / scale), card.to.map(|v| v / scale))).collect();
        let line_px = (1.5 / scale).round().max(1.0) as u32;
        draw_detections(&mut rgba, rig.width, rig.height, &boxes, &leaders, line_px);
        image.data = Some(rgba);
    }
    if node.image != held.0 {
        node.image = held.0.clone();
    }
    if let Ok(layer) = dots.single() {
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
    let Ok(layer) = cards.single() else { return };
    let [r, g, b] = DETECTION_COLOUR;
    commands.entity(layer).despawn_related::<Children>();
    commands.entity(layer).with_children(|layer| {
        for (card, object) in laid.iter().zip(&frame.detections) {
            layer
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: Val::Px(card.x),
                        top: Val::Px(card.y),
                        width: Val::Px(card.width),
                        height: Val::Px(card.height),
                        border: UiRect::all(Val::Px(1.0)),
                        padding: UiRect::horizontal(Val::Px(CARD_PADDING_PX - 1.0)),
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    BackgroundColor(Color::srgba_u8(12, 14, 17, 230)),
                    BorderColor::all(Color::srgb_u8(r, g, b)),
                ))
                .with_children(|card| {
                    card.spawn((
                        Text::new(card_text(object)),
                        TextFont { font_size: CARD_FONT_PX, ..default() },
                        TextColor(Color::srgb_u8(232, 248, 255)),
                        TextLayout::new_with_no_wrap(),
                    ));
                });
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

    #[test]
    fn what_the_on_board_model_found_is_held_by_frame_like_its_pixels() {
        let mut held: HeldFrames<Vec<&str>> = HeldFrames::new(4);
        held.hold(7, vec!["car"]);
        held.hold(8, vec![]);

        assert_eq!(held.take(7), Some(vec!["car"]));
        assert_eq!(held.held(), vec![8]);
    }

    fn a_car(track_id: u64, box_xyxy: [f32; 4]) -> DetectedObject {
        DetectedObject { label: "car".into(), score: 0.82, box_xyxy, track_id }
    }

    fn an_item(bbox: [f32; 4]) -> CardItem {
        let [x0, y0, x1, y1] = bbox;
        CardItem { anchor: [(x0 + x1) / 2.0, (y0 + y1) / 2.0], bbox, width: 60.0, height: 19.0 }
    }

    fn overlaps(a: &Card, b: &Card) -> bool {
        a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
    }

    fn inside(card: &Card, width: f32, height: f32) -> bool {
        card.x >= 0.0 && card.y >= 0.0 && card.x + card.width <= width && card.y + card.height <= height
    }

    #[test]
    fn a_lone_card_sits_just_above_its_object_centred_on_it() {
        let cards = layout_cards(&[an_item([100.0, 100.0, 140.0, 140.0])], 640.0, 480.0);

        assert_eq!((cards[0].x, cards[0].y), (90.0, 77.0));
    }

    #[test]
    fn an_object_at_the_top_edge_has_its_card_just_below_it() {
        let cards = layout_cards(&[an_item([100.0, 0.0, 140.0, 40.0])], 640.0, 480.0);

        assert_eq!((cards[0].x, cards[0].y), (90.0, 44.0));
    }

    #[test]
    fn cards_of_neighbouring_objects_never_overlap() {
        let items = [
            an_item([100.0, 100.0, 140.0, 140.0]),
            an_item([120.0, 102.0, 160.0, 142.0]),
            an_item([110.0, 98.0, 150.0, 138.0]),
        ];

        let cards = layout_cards(&items, 640.0, 480.0);

        assert!(!overlaps(&cards[0], &cards[1]), "{cards:?}");
        assert!(!overlaps(&cards[0], &cards[2]), "{cards:?}");
        assert!(!overlaps(&cards[1], &cards[2]), "{cards:?}");
    }

    #[test]
    fn a_card_stays_inside_the_image_for_an_object_at_its_corner() {
        let cards = layout_cards(&[an_item([620.0, 0.0, 640.0, 20.0])], 640.0, 480.0);

        assert!(inside(&cards[0], 640.0, 480.0), "{cards:?}");
    }

    #[test]
    fn a_leader_joins_the_card_s_nearest_edge_to_its_object() {
        let cards = layout_cards(&[an_item([100.0, 100.0, 140.0, 140.0])], 640.0, 480.0);

        assert_eq!((cards[0].from, cards[0].to), ([120.0, 96.0], [120.0, 120.0]));
    }

    #[test]
    fn a_detection_s_card_names_its_class_track_and_score() {
        assert_eq!(card_text(&a_car(3, [0.0, 0.0, 1.0, 1.0])), "car #3 82%");
    }

    #[test]
    fn a_detection_s_card_item_is_its_box_in_display_pixels_sized_to_its_text() {
        let item = card_item(&a_car(3, [10.0, 20.0, 50.0, 60.0]), 0.5);

        // "car #3 82%" is ten glyphs of 0.6 x 11 px, plus 6 px padding either side.
        assert_eq!(
            item,
            CardItem { anchor: [15.0, 20.0], bbox: [5.0, 10.0, 25.0, 30.0], width: 78.0, height: 19.0 }
        );
    }

    fn pixel(rgba: &[u8], width: u32, x: u32, y: u32) -> [u8; 3] {
        let i = ((y * width + x) * 4) as usize;
        [rgba[i], rgba[i + 1], rgba[i + 2]]
    }

    #[test]
    fn a_detection_s_box_is_outlined_and_its_inside_left_as_it_was() {
        let mut rgba = vec![0; 20 * 20 * 4];

        draw_detections(&mut rgba, 20, 20, &[[4.0, 4.0, 15.0, 15.0]], &[], 1);

        assert_eq!(pixel(&rgba, 20, 4, 10), DETECTION_COLOUR);
        assert_eq!(pixel(&rgba, 20, 10, 15), DETECTION_COLOUR);
        assert_eq!(pixel(&rgba, 20, 10, 10), [0, 0, 0]);
    }

    #[test]
    fn a_leader_is_drawn_from_its_card_to_its_object() {
        let mut rgba = vec![0; 20 * 20 * 4];

        draw_detections(&mut rgba, 20, 20, &[], &[([2.0, 10.0], [17.0, 10.0])], 1);

        assert_eq!(pixel(&rgba, 20, 10, 10), DETECTION_COLOUR);
        assert_eq!(pixel(&rgba, 20, 10, 4), [0, 0, 0]);
    }

    #[test]
    fn drawing_past_the_frame_s_edge_is_clipped() {
        let mut rgba = vec![0; 8 * 8 * 4];

        draw_detections(&mut rgba, 8, 8, &[[-5.0, -5.0, 20.0, 20.0]], &[([-3.0, 4.0], [12.0, 4.0])], 2);

        assert_eq!(pixel(&rgba, 8, 4, 4), DETECTION_COLOUR);
    }
}
