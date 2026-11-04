//! The page's stereo stream to the station's bridge, pure: when a pair is due on the simulation
//! clock, whether the socket is too backed up to take it, what a pair captures when its eyes are
//! requested and the header that labels it with its drone, where the stream's system runs in
//! the frame, and the `?bridge=` page parameter. The wasm socket is `bridge_wasm`.

#![allow(dead_code)]

use bevy::app::{App, Update};
use bevy::ecs::schedule::{IntoScheduleConfigs, SystemSet};

use super::ActiveDrone;
use crate::wire::PairHeader;

/// How many messages may wait in the socket (`WebSocket.bufferedAmount`) before a due pair is
/// dropped instead of sent.
pub const BACKLOG_MESSAGES: usize = 4;

/// What the stream does with the pair due at one tick.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pace {
    /// No pair is due yet.
    Wait,
    /// Read the eyes back and send the pair.
    Send,
    /// A pair is due but the link is backed up: skip it, it is never sent later.
    Drop,
}

/// Paces the stream at the camera's `rate_hz` of simulation time.
#[derive(Debug, Clone, PartialEq)]
pub struct StreamPacer {
    period_ns: u64,
    backlog_cap_bytes: usize,
    next_due_ns: Option<u64>,
}

impl StreamPacer {
    /// A pacer sending `rate_hz` pairs per second of simulation time, each `message_bytes`
    /// long; more than `BACKLOG_MESSAGES` of them waiting in the socket drops the due pair.
    pub fn new(rate_hz: f64, message_bytes: usize) -> Self {
        Self {
            period_ns: (1e9 / rate_hz).round() as u64,
            backlog_cap_bytes: BACKLOG_MESSAGES * message_bytes,
            next_due_ns: None,
        }
    }

    /// What to do at simulation time `t_ns` with `buffered_bytes` still waiting in the socket.
    /// The first tick is due; after a due tick, sent or dropped, the next pair is due one
    /// period later.
    pub fn decide(&mut self, t_ns: u64, buffered_bytes: usize) -> Pace {
        let due_at = self.next_due_ns.unwrap_or(t_ns);
        if t_ns < due_at {
            return Pace::Wait;
        }
        self.next_due_ns = Some(due_at + self.period_ns);
        if buffered_bytes > self.backlog_cap_bytes { Pace::Drop } else { Pace::Send }
    }
}

/// The header of the pair rendered at `frame_id` / `t_ns`, labelled with the active drone's id
/// (none without a fleet, so the message is the single-drone wire).
pub fn pair_for(
    active: &ActiveDrone,
    frame_id: u64,
    t_ns: u64,
    width: u32,
    height: u32,
    pose_enu: [f64; 7],
) -> PairHeader {
    PairHeader { frame_id, t_ns, width, height, pose_enu, drone_id: active.0.clone() }
}

/// A pair whose eyes are being read back: what the stream captured when it requested them.
#[derive(Debug, Clone)]
pub struct PendingPair {
    requested_by: ActiveDrone,
    t_ns: u64,
    pose_enu: [f64; 7],
}

impl PendingPair {
    /// Captured when the stream requests `active`'s eyes at `t_ns`, posed at `pose_enu`.
    pub fn requested(active: &ActiveDrone, t_ns: u64, pose_enu: [f64; 7]) -> Self {
        Self { requested_by: active.clone(), t_ns, pose_enu }
    }

    /// The pair's header as the stream's `frame_id`-th pair, once both eyes have landed. It
    /// names the drone whose eyes were requested, whichever drone is active by then.
    pub fn header(&self, frame_id: u64, width: u32, height: u32) -> PairHeader {
        pair_for(&self.requested_by, frame_id, self.t_ns, width, height, self.pose_enu)
    }
}

/// The system set the stream's system (`bridge_wasm::stream_bridge`) runs in, in `Update`.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct BridgeStreamSet;

/// Places `BridgeStreamSet` in the frame's `Update` schedule: after the fleet has flown and the
/// eyes have followed their bodies, so the pose it captures is the frame's own, not the last one's.
pub fn order_bridge_stream(app: &mut App) {
    app.configure_sets(
        Update,
        BridgeStreamSet.after(super::fly_fleet).after(crate::follow_drone_rig),
    );
}

/// The bridge socket a page URL's query (`location.search`) names: `bridge=ws://host:port`,
/// plain or percent-encoded (`ws%3A%2F%2Fhost%3Aport`, as `URLSearchParams` writes it).
pub fn bridge_url(search: &str) -> Option<String> {
    search
        .trim_start_matches('?')
        .split('&')
        .find_map(|pair| pair.strip_prefix("bridge="))
        .filter(|url| !url.is_empty())
        .map(percent_decoded)
}

/// `value` with each `%XX` escape decoded; a malformed escape is kept as it is.
fn percent_decoded(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        let escape = (bytes[i] == b'%')
            .then(|| bytes.get(i + 1..i + 3))
            .flatten()
            .and_then(|hex| u8::from_str_radix(std::str::from_utf8(hex).ok()?, 16).ok());
        match escape {
            Some(byte) => {
                out.push(byte);
                i += 3;
            }
            None => {
                out.push(bytes[i]);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// The map status line under the feed panel, from one bridge `status` reply:
/// `MAP nest-sw-d1 · 412 frames · 37 keyframes · tracking`.
pub fn status_line(drone_id: Option<&str>, frames: u64, keyframes: u64, lost: bool) -> String {
    format!(
        "MAP {} · {frames} frames · {keyframes} keyframes · {}",
        drone_id.unwrap_or("default"),
        if lost { "lost" } else { "tracking" }
    )
}

/// One frame's odometry from a bridge `status` reply: the frame the page sent as `frame_id`,
/// and the keypoints RTAB-Map tracked in it as `[u, v, depth_m]`, raw left-camera pixels.
#[derive(Debug, Clone, PartialEq)]
pub struct FrameKeypoints {
    pub frame_id: u64,
    pub keypoints: Vec<[f32; 3]>,
}

/// The odometry frames a `status` reply carries (`"odometry"`), in order; none when it has no
/// such field. A malformed entry or keypoint is skipped.
pub fn parse_odometry(reply: &serde_json::Value) -> Vec<FrameKeypoints> {
    let Some(entries) = reply.get("odometry").and_then(serde_json::Value::as_array) else {
        return Vec::new();
    };
    entries
        .iter()
        .filter_map(|entry| {
            let frame_id = entry.get("frame_id")?.as_u64()?;
            let keypoints = entry
                .get("keypoints")
                .and_then(serde_json::Value::as_array)
                .map(|points| points.iter().filter_map(keypoint).collect())
                .unwrap_or_default();
            Some(FrameKeypoints { frame_id, keypoints })
        })
        .collect()
}

/// One `[u, v, depth]` keypoint; anything else is `None`.
fn keypoint(value: &serde_json::Value) -> Option<[f32; 3]> {
    match value.as_array()?.as_slice() {
        [u, v, depth] => Some([u.as_f64()? as f32, v.as_f64()? as f32, depth.as_f64()? as f32]),
        _ => None,
    }
}

/// One object the on-board model found on a frame: its class, score, box `[x0, y0, x1, y1]` in
/// raw left-camera pixels, and its tracker's id.
#[derive(Debug, Clone, PartialEq)]
pub struct DetectedObject {
    pub label: String,
    pub score: f32,
    pub box_xyxy: [f32; 4],
    pub track_id: u64,
}

/// What the on-board model found on the frame the page sent as `frame_id`.
#[derive(Debug, Clone, PartialEq)]
pub struct FrameDetections {
    pub frame_id: u64,
    pub objects: Vec<DetectedObject>,
}

/// The on-board detections a `status` reply carries (`"detections"`), in order; none when it has
/// no such field. A malformed entry or object is skipped.
pub fn parse_detections(reply: &serde_json::Value) -> Vec<FrameDetections> {
    let Some(entries) = reply.get("detections").and_then(serde_json::Value::as_array) else {
        return Vec::new();
    };
    entries
        .iter()
        .filter_map(|entry| {
            let frame_id = entry.get("frame_id")?.as_u64()?;
            let objects = entry
                .get("objects")
                .and_then(serde_json::Value::as_array)
                .map(|objects| objects.iter().filter_map(detected_object).collect())
                .unwrap_or_default();
            Some(FrameDetections { frame_id, objects })
        })
        .collect()
}

/// One `{label, score, box: [x0, y0, x1, y1], track_id}` object; anything else is `None`.
fn detected_object(value: &serde_json::Value) -> Option<DetectedObject> {
    let corners = value.get("box")?.as_array()?;
    let [x0, y0, x1, y1] = corners.as_slice() else { return None };
    Some(DetectedObject {
        label: value.get("label")?.as_str()?.to_owned(),
        score: value.get("score")?.as_f64()? as f32,
        box_xyxy: [x0.as_f64()? as f32, y0.as_f64()? as f32, x1.as_f64()? as f32, y1.as_f64()? as f32],
        track_id: value.get("track_id")?.as_u64()?,
    })
}

#[cfg(test)]
mod tests {
    use bevy::ecs::schedule::{InternedSystemSet, IntoSystemSet, Schedules, SystemKey};
    use bevy::prelude::{Query, Res, Transform};

    use super::*;
    use crate::fleet::fly_fleet;
    use crate::wire::encode_pair;

    const PAIR_GOLDEN: &[u8] = include_bytes!("../../../../tests/fixtures/bevy_sim_wire/pair.bin");
    const PAIR_DRONE_GOLDEN: &[u8] =
        include_bytes!("../../../../tests/fixtures/bevy_sim_wire/pair-drone.bin");
    const SW_D1: &str = "nest-sw-d1";
    const POSE: [f64; 7] = [1.0, 3.0, 2.0, 0.0, 0.0, 0.0, 1.0];
    const MS: u64 = 1_000_000;
    /// A 60 fps render loop's tick, ns.
    const TICK_NS: u64 = 16_666_667;
    /// One 640 x 480 stereo pair's payload.
    const PAIR_BYTES: usize = 2 * 640 * 480;

    fn the_golden_pair(active: &ActiveDrone) -> Vec<u8> {
        let header = pair_for(active, 7, 700_000_000, 4, 2, [1.0, 3.0, 2.0, 0.0, 0.0, 0.0, 1.0]);
        let left: Vec<u8> = (0..8).collect();
        let right: Vec<u8> = (8..16).collect();
        encode_pair(&header, &left, &right)
    }

    /// A stand-in for the stream's system: it reads what `stream_bridge` reads of the frame —
    /// the active drone and the bodies' and eyes' poses.
    fn reads_the_eyes(_active: Option<Res<ActiveDrone>>, _bodies: Query<&Transform>) {}

    /// Builds `Update` as the frame orders `fly_fleet`, `follow_drone_rig` (after it) and
    /// `BridgeStreamSet`, with `reads_the_eyes` in the set; the names of the systems that write
    /// what the stand-in reads and are not ordered against it.
    fn unordered_against_the_stream() -> Vec<String> {
        let mut app = App::new();
        app.add_systems(
            Update,
            (
                reads_the_eyes.in_set(BridgeStreamSet),
                fly_fleet,
                crate::follow_drone_rig.after(fly_fleet),
            ),
        );
        order_bridge_stream(&mut app);
        let mut schedule = app
            .world_mut()
            .resource_mut::<Schedules>()
            .remove(Update)
            .expect("the Update schedule");
        schedule.initialize(app.world_mut()).expect("the Update schedule builds");
        let graph = schedule.graph();
        let members = |set: InternedSystemSet| -> Vec<SystemKey> {
            graph.systems_in_set(set).expect("the set is in the schedule").iter().copied().collect()
        };
        let stream = members(BridgeStreamSet.intern());
        let writers = [
            ("fly_fleet", members(fly_fleet.into_system_set().intern())),
            ("follow_drone_rig", members(crate::follow_drone_rig.into_system_set().intern())),
        ];
        let mut unordered: Vec<String> = graph
            .conflicting_systems()
            .iter()
            .filter_map(|(a, b, _)| match (stream.contains(a), stream.contains(b)) {
                (true, false) => Some(*b),
                (false, true) => Some(*a),
                _ => None,
            })
            .filter_map(|other| {
                writers.iter().find(|(_, keys)| keys.contains(&other)).map(|(name, _)| name.to_string())
            })
            .collect();
        unordered.sort();
        unordered
    }

    fn decisions(pacer: &mut StreamPacer, ticks: &[(u64, usize)]) -> Vec<Pace> {
        ticks.iter().map(|&(t_ns, buffered)| pacer.decide(t_ns, buffered)).collect()
    }

    #[test]
    fn a_pair_carries_the_active_drones_id() {
        let active = ActiveDrone(Some(SW_D1.into()));

        let message = the_golden_pair(&active);

        assert_eq!(message, PAIR_DRONE_GOLDEN);
    }

    #[test]
    fn a_pair_without_a_fleet_is_byte_identical_to_the_golden() {
        let no_fleet = ActiveDrone(None);

        let message = the_golden_pair(&no_fleet);

        assert_eq!(message, PAIR_GOLDEN);
    }

    #[test]
    fn a_switch_while_the_eyes_are_read_back_keeps_the_requesting_drones_id() {
        let requested = PendingPair::requested(&ActiveDrone(Some(SW_D1.into())), 700_000_000, POSE);

        let header = requested.header(7, 4, 2);

        assert_eq!(header.drone_id.as_deref(), Some(SW_D1));
    }

    #[test]
    fn the_stream_reads_the_eyes_only_after_the_fleet_flew_and_the_eyes_followed() {
        let unordered = unordered_against_the_stream();

        assert_eq!(unordered, Vec::<String>::new());
    }

    #[test]
    fn the_pacer_sends_at_the_camera_rate_of_sim_time() {
        let mut pacer = StreamPacer::new(10.0, PAIR_BYTES);
        let one_second_of_ticks: Vec<(u64, usize)> = (0..60).map(|i| (i * TICK_NS, 0)).collect();

        let sent: Vec<u64> = one_second_of_ticks
            .iter()
            .filter(|&&(t_ns, buffered)| pacer.decide(t_ns, buffered) == Pace::Send)
            .map(|&(t_ns, _)| t_ns / MS)
            .collect();

        assert_eq!(sent, vec![0, 100, 200, 300, 400, 500, 600, 700, 800, 900]);
    }

    #[test]
    fn the_pacer_drops_when_the_link_is_backed_up() {
        let mut pacer = StreamPacer::new(10.0, PAIR_BYTES);
        let backed_up = BACKLOG_MESSAGES * PAIR_BYTES + 1;

        let paces = decisions(&mut pacer, &[(0, backed_up), (50 * MS, 0), (100 * MS, 0)]);

        assert_eq!(paces, vec![Pace::Drop, Pace::Wait, Pace::Send]);
    }

    #[test]
    fn the_pacer_still_sends_with_four_messages_waiting() {
        let mut pacer = StreamPacer::new(10.0, PAIR_BYTES);

        let paces = decisions(&mut pacer, &[(0, BACKLOG_MESSAGES * PAIR_BYTES)]);

        assert_eq!(paces, vec![Pace::Send]);
    }

    #[test]
    fn the_bridge_parameter_names_the_station_socket() {
        let search = "?scenario=quake-fleet&fleet=1&bridge=ws://127.0.0.1:8773";

        let url = bridge_url(search);

        assert_eq!(url.as_deref(), Some("ws://127.0.0.1:8773"));
    }

    #[test]
    fn a_percent_encoded_bridge_parameter_is_decoded() {
        // The chat builds the preview URL with `URLSearchParams`, which encodes `:` and `/`.
        let search = "?scenario=quake-fleet&view=preview&fleet=1&bridge=ws%3A%2F%2F127.0.0.1%3A8782";

        let url = bridge_url(search);

        assert_eq!(url.as_deref(), Some("ws://127.0.0.1:8782"));
    }

    #[test]
    fn a_page_without_the_bridge_parameter_does_not_stream() {
        let search = "?scenario=quake-fleet&fleet=1";

        let url = bridge_url(search);

        assert_eq!(url, None);
    }

    #[test]
    fn a_status_reply_s_odometry_names_each_frame_and_its_keypoints() {
        let reply = serde_json::json!({
            "type": "status", "frames": 8,
            "odometry": [
                {"frame_id": 6, "keypoints": [[1.5, 0.5, 2.25]]},
                {"frame_id": 7, "keypoints": [[3.0, 1.0, 9.0], [0.0, 0.0, 1.0]]}
            ]
        });

        assert_eq!(
            parse_odometry(&reply),
            vec![
                FrameKeypoints { frame_id: 6, keypoints: vec![[1.5, 0.5, 2.25]] },
                FrameKeypoints { frame_id: 7, keypoints: vec![[3.0, 1.0, 9.0], [0.0, 0.0, 1.0]] },
            ]
        );
    }

    #[test]
    fn a_status_reply_without_odometry_has_no_frames() {
        assert_eq!(parse_odometry(&serde_json::json!({"type": "status", "frames": 1})), vec![]);
    }

    #[test]
    fn a_malformed_odometry_entry_or_keypoint_is_skipped() {
        let reply = serde_json::json!({
            "odometry": [
                {"keypoints": [[1.0, 1.0, 1.0]]},
                {"frame_id": 4, "keypoints": [[1.0, 1.0], "x", [2.0, 2.0, 3.0]]}
            ]
        });

        assert_eq!(
            parse_odometry(&reply),
            vec![FrameKeypoints { frame_id: 4, keypoints: vec![[2.0, 2.0, 3.0]] }]
        );
    }

    #[test]
    fn a_status_reply_s_detections_name_each_frame_and_its_objects() {
        let reply = serde_json::json!({
            "type": "status", "frames": 8,
            "detections": [
                {"frame_id": 8, "objects": [
                    {"label": "car", "score": 0.82, "box": [10.0, 20.5, 64.0, 48.0], "track_id": 3}
                ]}
            ]
        });

        assert_eq!(
            parse_detections(&reply),
            vec![FrameDetections {
                frame_id: 8,
                objects: vec![DetectedObject {
                    label: "car".into(),
                    score: 0.82,
                    box_xyxy: [10.0, 20.5, 64.0, 48.0],
                    track_id: 3,
                }],
            }]
        );
    }

    #[test]
    fn a_status_reply_without_detections_has_none() {
        assert_eq!(parse_detections(&serde_json::json!({"type": "status", "frames": 1})), vec![]);
    }

    #[test]
    fn a_malformed_detection_entry_or_object_is_skipped() {
        let reply = serde_json::json!({
            "detections": [
                {"objects": []},
                {"frame_id": 4, "objects": [
                    {"label": "car", "score": 0.5, "box": [1.0, 2.0], "track_id": 1},
                    {"label": "bus", "score": 0.9, "box": [1.0, 2.0, 3.0, 4.0], "track_id": 2}
                ]}
            ]
        });

        assert_eq!(
            parse_detections(&reply),
            vec![FrameDetections {
                frame_id: 4,
                objects: vec![DetectedObject {
                    label: "bus".into(),
                    score: 0.9,
                    box_xyxy: [1.0, 2.0, 3.0, 4.0],
                    track_id: 2,
                }],
            }]
        );
    }
}
