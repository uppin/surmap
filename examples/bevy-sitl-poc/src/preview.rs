//! The chat's preview of the simulation (`?view=preview`), pure: one view and nothing else on
//! the page — the overview (the chase view, with its PTZ) while the viewed drone is on the
//! ground, its first-person camera once it flies. In the air the FPV shows the frame RTAB-Map
//! processed with that frame's tracked keypoints: a sent frame is held until its odometry comes
//! back (`HeldFrames`), so the view may lag the live camera but points never sit on another
//! frame. The Bevy systems that draw it are `preview_ui`.

use std::collections::VecDeque;

use crate::fleet::autopilot::Phase;

/// How the page shows the simulation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ViewMode {
    /// The full page: chase view, stereo panel, HUD and the Take off button.
    #[default]
    Full,
    /// The chat's preview: one view, edge to edge.
    Preview,
}

/// The view mode a page URL's query (`location.search`) names: `view=preview`.
pub fn view_mode(search: &str) -> ViewMode {
    let _ = search;
    todo!("view_mode")
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
    let _ = (fleet_phase, engaged);
    todo!("preview_view")
}

/// A keypoint's colour by its depth: near red, through yellow and green, to far blue.
pub fn depth_colour(depth_m: f32) -> [u8; 3] {
    let _ = depth_m;
    todo!("depth_colour")
}

/// The sent frames still waiting for their odometry, oldest first, at most `capacity`.
#[derive(Debug, Clone, PartialEq)]
pub struct HeldFrames {
    capacity: usize,
    frames: VecDeque<(u64, Vec<u8>)>,
}

impl HeldFrames {
    /// Holds at most `capacity` frames; holding one more drops the oldest.
    pub fn new(capacity: usize) -> Self {
        Self { capacity, frames: VecDeque::new() }
    }

    /// Holds `pixels`, the frame sent as `frame_id`.
    pub fn hold(&mut self, frame_id: u64, pixels: Vec<u8>) {
        let _ = (frame_id, pixels);
        todo!("HeldFrames::hold")
    }

    /// The pixels of `frame_id`, whose odometry came back; it and every older frame stop being
    /// held (their odometry, if it ever comes, is stale). `None` when it is not held.
    pub fn take(&mut self, frame_id: u64) -> Option<Vec<u8>> {
        let _ = frame_id;
        todo!("HeldFrames::take")
    }

    /// The ids of the frames held, oldest first.
    pub fn held(&self) -> Vec<u64> {
        self.frames.iter().map(|(id, _)| *id).collect()
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
