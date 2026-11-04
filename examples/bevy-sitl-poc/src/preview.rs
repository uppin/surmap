//! The chat's preview of the simulation (`?view=preview`), pure: one view and nothing else on
//! the page — the overview (the chase view, with its PTZ) while the viewed drone is on the
//! ground, its first-person camera once it flies. In the air the FPV is the live left eye, never
//! waiting on the station: RTAB-Map's keypoints of a recent frame (`fresh_keypoints`) are drawn
//! over it as one overlay image (`keypoint_overlay`). When the agent runs an on-board model
//! (`set_onboard_model`), a recent frame's detections (`fresh_detections`) are outlined in that
//! overlay too, each with a label card laid out as the demo page's SAM cards are
//! (`layout_cards`): near its object, joined by a leader, never overlapping another card. Only
//! the cameras the view shows render, plus both eyes in a frame whose pair the stream reads back
//! (`preview_renders`).

use bevy::asset::RenderAssetUsages;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};

use crate::calibration::CameraProfile;
use crate::fleet::autopilot::Phase;
use crate::fleet::stream::{BridgeStreamSet, DetectedObject, FrameDetections, FrameKeypoints};
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

/// The on-board detections of `found` while its frame is at most `FRESH_FRAMES` behind
/// `last_sent`, as for keypoints; none before any or once they are stale.
pub fn fresh_detections(found: Option<&FrameDetections>, last_sent: u64) -> Option<&[DetectedObject]> {
    found.filter(|found| found.frame_id + FRESH_FRAMES >= last_sent).map(|found| &found.objects[..])
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

/// The on-board detections outlined over the FPV now: the bridge stream writes them when the
/// fresh detections change (empty once they are stale).
#[derive(Resource, Debug, Clone, Default, PartialEq)]
pub struct FpvDetections(pub Vec<DetectedObject>);

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

/// Set by the bridge stream in a frame whose pair it reads back, so both eyes render that frame.
#[derive(Resource, Debug, Default)]
pub struct PairDue(pub bool);

/// The preview's full-window layer over the chase view; shown in FPV.
#[derive(Component)]
pub struct PreviewFpv;

/// The keypoint and detection overlay's image, over the live eye.
#[derive(Resource)]
struct Overlay(Handle<Image>);

/// The live eye's image node, whose displayed size the label cards are laid out in.
#[derive(Component)]
struct PreviewImage;

/// The layer of detection label cards over the live eye.
#[derive(Component)]
struct PreviewCards;

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
            .add_systems(Update, (switch_preview, show_overlay).after(setup_preview))
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
                    image.spawn((ImageNode::new(overlay), layer()));
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

/// Redraws the overlay whenever the bridge stream changes the keypoints or the detections, or
/// the live eye's displayed size changes: the keypoints' dots, each detection's outline and its
/// card's leader into the overlay image (camera pixels), and a label card per detection laid out
/// in display pixels, so cards never overlap at any preview size.
#[allow(clippy::too_many_arguments)]
fn show_overlay(
    mut commands: Commands,
    keypoints: Option<Res<FpvKeypoints>>,
    detections: Option<Res<FpvDetections>>,
    overlay: Option<Res<Overlay>>,
    rig: Option<Res<CameraProfile>>,
    mut images: ResMut<Assets<Image>>,
    eye: Query<&ComputedNode, With<PreviewImage>>,
    cards: Query<Entity, With<PreviewCards>>,
    mut shown_at: Local<Vec2>,
) {
    let (Some(overlay), Some(rig)) = (overlay, rig) else { return };
    let Ok(computed) = eye.single() else { return };
    let display = computed.size() * computed.inverse_scale_factor();
    let changed = keypoints.as_ref().is_some_and(|k| k.is_changed())
        || detections.as_ref().is_some_and(|d| d.is_changed());
    if !changed && display == *shown_at {
        return;
    }
    *shown_at = display;
    let objects: &[DetectedObject] = detections.as_ref().map_or(&[], |d| &d.0[..]);
    let scale = if display.x > 0.0 { display.x / rig.width as f32 } else { 1.0 };
    let items: Vec<CardItem> = objects.iter().map(|object| card_item(object, scale)).collect();
    let laid = layout_cards(&items, display.x, display.y);
    if let Some(image) = images.get_mut(&overlay.0) {
        let mut rgba = keypoint_overlay(rig.width, rig.height, keypoints.as_ref().map_or(&[], |k| &k.0[..]));
        let boxes: Vec<[f32; 4]> = objects.iter().map(|object| object.box_xyxy).collect();
        let leaders: Vec<([f32; 2], [f32; 2])> =
            laid.iter().map(|card| (card.from.map(|v| v / scale), card.to.map(|v| v / scale))).collect();
        let line_px = (1.5 / scale).round().max(1.0) as u32;
        draw_detections(&mut rgba, rig.width, rig.height, &boxes, &leaders, line_px);
        image.data = Some(rgba);
    }
    let Ok(layer) = cards.single() else { return };
    let [r, g, b] = DETECTION_COLOUR;
    commands.entity(layer).despawn_related::<Children>();
    commands.entity(layer).with_children(|layer| {
        for (card, object) in laid.iter().zip(objects) {
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

    #[test]
    fn a_recent_frame_s_detections_are_outlined_over_the_live_eye() {
        let found = FrameDetections { frame_id: 7, objects: vec![a_car(3, [0.0, 0.0, 1.0, 1.0])] };

        assert_eq!(fresh_detections(Some(&found), 9), Some(&found.objects[..]));
    }

    #[test]
    fn detections_older_than_the_fresh_frames_are_not_drawn() {
        let found = FrameDetections { frame_id: 7, objects: vec![a_car(3, [0.0, 0.0, 1.0, 1.0])] };

        assert_eq!(fresh_detections(Some(&found), 10), None);
        assert_eq!(fresh_detections(None, 10), None);
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

    fn colour_at(rgba: &[u8], width: u32, x: u32, y: u32) -> [u8; 3] {
        let i = ((y * width + x) * 4) as usize;
        [rgba[i], rgba[i + 1], rgba[i + 2]]
    }

    #[test]
    fn a_detection_s_box_is_outlined_and_its_inside_left_as_it_was() {
        let mut rgba = vec![0; 20 * 20 * 4];

        draw_detections(&mut rgba, 20, 20, &[[4.0, 4.0, 15.0, 15.0]], &[], 1);

        assert_eq!(colour_at(&rgba, 20, 4, 10), DETECTION_COLOUR);
        assert_eq!(colour_at(&rgba, 20, 10, 15), DETECTION_COLOUR);
        assert_eq!(colour_at(&rgba, 20, 10, 10), [0, 0, 0]);
    }

    #[test]
    fn a_leader_is_drawn_from_its_card_to_its_object() {
        let mut rgba = vec![0; 20 * 20 * 4];

        draw_detections(&mut rgba, 20, 20, &[], &[([2.0, 10.0], [17.0, 10.0])], 1);

        assert_eq!(colour_at(&rgba, 20, 10, 10), DETECTION_COLOUR);
        assert_eq!(colour_at(&rgba, 20, 10, 4), [0, 0, 0]);
    }

    #[test]
    fn drawing_past_the_frame_s_edge_is_clipped() {
        let mut rgba = vec![0; 8 * 8 * 4];

        draw_detections(&mut rgba, 8, 8, &[[-5.0, -5.0, 20.0, 20.0]], &[([-3.0, 4.0], [12.0, 4.0])], 2);

        assert_eq!(colour_at(&rgba, 8, 4, 4), DETECTION_COLOUR);
    }
}
