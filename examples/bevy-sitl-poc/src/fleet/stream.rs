//! The page's stereo stream to the station's bridge, pure: when a pair is due on the simulation
//! clock, whether the socket is too backed up to take it, the header that labels it with the
//! active drone, and the `?bridge=` page parameter. The wasm socket is `bridge_wasm`.

#![allow(dead_code)]

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
        // TODO(pr-5): implement
        let _ = (t_ns, buffered_bytes, self.period_ns, self.backlog_cap_bytes, self.next_due_ns);
        todo!("pr-5: implement")
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
    // TODO(pr-5): implement
    let _ = (active, frame_id, t_ns, width, height, pose_enu);
    todo!("pr-5: implement")
}

/// The bridge socket a page URL's query (`location.search`) names: `bridge=ws://host:port`.
pub fn bridge_url(search: &str) -> Option<String> {
    // TODO(pr-5): implement
    let _ = search;
    todo!("pr-5: implement")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::wire::encode_pair;

    const PAIR_GOLDEN: &[u8] = include_bytes!("../../../../tests/fixtures/bevy_sim_wire/pair.bin");
    const PAIR_DRONE_GOLDEN: &[u8] =
        include_bytes!("../../../../tests/fixtures/bevy_sim_wire/pair-drone.bin");
    const SW_D1: &str = "nest-sw-d1";
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
    fn a_page_without_the_bridge_parameter_does_not_stream() {
        let search = "?scenario=quake-fleet&fleet=1";

        let url = bridge_url(search);

        assert_eq!(url, None);
    }
}
