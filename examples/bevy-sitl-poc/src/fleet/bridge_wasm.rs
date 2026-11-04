//! The page's stereo stream (wasm only): with `?bridge=ws://host:port`, a binary
//! `web_sys::WebSocket` to the station's stereo bridge. At scene ready it sends the `hello`
//! (camera profile, ground truth, scenario); then, on each tick `stream::StreamPacer` says is
//! due, it reads the eyes back (`Readback`, as `record.rs` does) and sends `wire::encode_pair`
//! labelled with `ActiveDrone`'s id, dropping the pair when the socket is backed up. The bridge's
//! status replies feed the map status line under the feed panel. Natively nothing streams.

use std::cell::RefCell;
use std::rc::Rc;

use bevy::prelude::*;
use bevy::render::gpu_readback::{Readback, ReadbackComplete};
use wasm_bindgen::closure::Closure;
use wasm_bindgen::JsCast;
use web_sys::{BinaryType, CloseEvent, ErrorEvent, MessageEvent, WebSocket};

use super::stream::{
    bridge_url, order_bridge_stream, status_line, BridgeStreamSet, Pace, PendingPair, StreamPacer,
};
use super::ActiveDrone;
use crate::calibration::CameraProfile;
use crate::ui::MapStatusLine;
use crate::wildfire::SimClock;
use crate::wire::{bgra_to_gray8, encode_hello_with_scenario, encode_pair, rig_pose_enu};
use crate::world::{scene_ready, GroundTruth, PendingModel, SceneState};
use crate::{FleetDrone, StereoFeeds};

/// The bridge socket the page URL names (`?bridge=`, via `stream::bridge_url`), if any.
pub fn page_bridge_url() -> Option<String> {
    web_sys::window()
        .and_then(|window| window.location().search().ok())
        .and_then(|search| bridge_url(&search))
}

/// Opens the bridge socket once the scene is built and streams the active drone's eyes.
pub struct BridgeStreamPlugin {
    /// The bridge socket (`?bridge=`).
    pub url: String,
    /// The scenario the page runs (`?scenario=`), sent in the `hello`.
    pub scenario: Option<String>,
}

impl Plugin for BridgeStreamPlugin {
    fn build(&self, app: &mut App) {
        match BridgeStream::open(&self.url, self.scenario.clone()) {
            Ok(stream) => {
                app.insert_resource(MapStatusLine::default());
                app.insert_non_send_resource(stream);
                app.add_systems(Update, stream_bridge.in_set(BridgeStreamSet));
                order_bridge_stream(app);
            }
            Err(why) => warn!("bridge stream: {why}"),
        }
    }
}

#[derive(Component, Clone, Copy)]
enum BridgeEye {
    Left,
    Right,
}

/// GPU readbacks pad each row to 256 bytes.
fn padded_row_bytes(width: u32) -> u32 {
    (width * 4).div_ceil(256) * 256
}

/// The open socket, the pair being read back, and the callbacks that feed it (kept alive).
struct BridgeStream {
    socket: WebSocket,
    scenario: Option<String>,
    pacer: Option<StreamPacer>,
    hello_sent: bool,
    frame_id: u64,
    requested: bool,
    left: Option<Vec<u8>>,
    right: Option<Vec<u8>>,
    pending: Option<PendingPair>,
    status: Rc<RefCell<String>>,
    _callbacks: (
        Closure<dyn FnMut(MessageEvent)>,
        Closure<dyn FnMut(CloseEvent)>,
        Closure<dyn FnMut(ErrorEvent)>,
    ),
}

impl BridgeStream {
    fn open(url: &str, scenario: Option<String>) -> Result<Self, String> {
        let socket = WebSocket::new(url).map_err(|_| format!("cannot open {url}"))?;
        socket.set_binary_type(BinaryType::Arraybuffer);
        let status: Rc<RefCell<String>> = Rc::default();
        let shared = Rc::clone(&status);
        let on_message = Closure::<dyn FnMut(MessageEvent)>::new(move |event: MessageEvent| {
            let Some(text) = event.data().as_string() else {
                return;
            };
            let Ok(reply) = serde_json::from_str::<serde_json::Value>(&text) else {
                return;
            };
            if reply.get("type").and_then(serde_json::Value::as_str) != Some("status") {
                return;
            }
            let number = |key: &str| {
                reply
                    .get(key)
                    .and_then(serde_json::Value::as_u64)
                    .unwrap_or(0)
            };
            *shared.borrow_mut() = status_line(
                reply.get("drone_id").and_then(serde_json::Value::as_str),
                number("frames"),
                number("keyframes"),
                reply
                    .get("lost")
                    .and_then(serde_json::Value::as_bool)
                    .unwrap_or(false),
            );
        });
        let on_close = Closure::<dyn FnMut(CloseEvent)>::new(|event: CloseEvent| {
            warn!(
                "bridge stream closed: code {} {}",
                event.code(),
                event.reason()
            );
        });
        let on_error = Closure::<dyn FnMut(ErrorEvent)>::new(|event: ErrorEvent| {
            warn!("bridge stream error: {}", event.message());
        });
        socket.set_onmessage(Some(on_message.as_ref().unchecked_ref()));
        socket.set_onclose(Some(on_close.as_ref().unchecked_ref()));
        socket.set_onerror(Some(on_error.as_ref().unchecked_ref()));
        info!("bridge stream: {url}");
        Ok(Self {
            socket,
            scenario,
            pacer: None,
            hello_sent: false,
            frame_id: 0,
            requested: false,
            left: None,
            right: None,
            pending: None,
            status,
            _callbacks: (on_message, on_close, on_error),
        })
    }

    fn is_open(&self) -> bool {
        self.socket.ready_state() == WebSocket::OPEN
    }

    fn send(&self, message: &[u8]) {
        if let Err(why) = self.socket.send_with_u8_array(message) {
            warn!("bridge stream: cannot send: {why:?}");
        }
    }
}

/// An eye readback landed: keep its grey frame until the other eye lands too.
fn on_bridge_eye(
    read: On<ReadbackComplete>,
    eyes: Query<&BridgeEye>,
    rig: Res<CameraProfile>,
    mut stream: NonSendMut<BridgeStream>,
    mut commands: Commands,
) {
    let Ok(eye) = eyes.get(read.entity) else {
        return;
    };
    let pixels = bgra_to_gray8(
        &read.data,
        rig.width,
        rig.height,
        padded_row_bytes(rig.width),
    );
    match eye {
        BridgeEye::Left if stream.left.is_none() => stream.left = Some(pixels),
        BridgeEye::Right if stream.right.is_none() => stream.right = Some(pixels),
        _ => {}
    }
    commands.entity(read.entity).despawn();
}

#[allow(clippy::too_many_arguments)]
fn stream_bridge(
    mut commands: Commands,
    mut stream: NonSendMut<BridgeStream>,
    clock: SimClock,
    scene: Option<Res<SceneState>>,
    assets: Res<AssetServer>,
    pending: Query<(), With<PendingModel>>,
    feeds: Option<Res<StereoFeeds>>,
    rig: Option<Res<CameraProfile>>,
    truth: Res<GroundTruth>,
    active: Option<Res<ActiveDrone>>,
    fleet: Query<(&FleetDrone, &Transform)>,
    legacy: Query<&Transform, With<crate::Drone>>,
    mut status_line: ResMut<MapStatusLine>,
) {
    let latest = stream.status.borrow().clone();
    if status_line.0 != latest {
        status_line.0 = latest;
    }
    if !stream.is_open() {
        return;
    }
    let (Some(feeds), Some(rig)) = (feeds, rig) else {
        return;
    };
    if !stream.hello_sent {
        let Some(scene) = scene else { return };
        if !scene_ready(&scene, &assets, pending.iter().count()) {
            return;
        }
        stream.send(&encode_hello_with_scenario(
            &rig,
            &truth.0,
            stream.scenario.as_deref(),
        ));
        let message_bytes = (rig.width as usize) * (rig.height as usize) * 2 + 256;
        stream.pacer = Some(StreamPacer::new(f64::from(rig.rate_hz), message_bytes));
        stream.hello_sent = true;
        return;
    }
    // A pair is being read back: send it once both eyes have landed.
    if stream.requested {
        if stream.left.is_none() || stream.right.is_none() {
            return;
        }
        let (left, right) = (
            stream.left.take().expect("left eye checked"),
            stream.right.take().expect("right eye checked"),
        );
        stream.requested = false;
        stream.frame_id += 1;
        let Some(pending) = stream.pending.take() else {
            return;
        };
        let header = pending.header(stream.frame_id, rig.width, rig.height);
        stream.send(&encode_pair(&header, &left, &right));
        return;
    }
    let t_ns = (f64::from(clock.now()) * 1e9).round() as u64;
    let buffered = stream.socket.buffered_amount() as usize;
    let Some(pacer) = stream.pacer.as_mut() else {
        return;
    };
    if pacer.decide(t_ns, buffered) != Pace::Send {
        return;
    }
    // The rig pose of the viewed drone, as `record.rs` derives it from the viewed body.
    let active_id = active.as_ref().and_then(|a| a.0.as_deref());
    let body = active_id
        .and_then(|id| {
            fleet
                .iter()
                .find(|(drone, _)| drone.id == id)
                .map(|(_, body)| body)
        })
        .or_else(|| legacy.single().ok());
    let Some(body) = body else { return };
    let rig_translation = body.translation + body.rotation * rig.mount_offset();
    let rig_rotation = body.rotation * rig.mount_rotation();
    let requesting = active.as_ref().map(|a| (**a).clone()).unwrap_or_default();
    stream.pending = Some(PendingPair::requested(
        &requesting,
        t_ns,
        rig_pose_enu(rig_translation, rig_rotation),
    ));
    stream.left = None;
    stream.right = None;
    for (eye, target) in [
        (BridgeEye::Left, feeds.left.clone()),
        (BridgeEye::Right, feeds.right.clone()),
    ] {
        commands
            .spawn((Readback::texture(target), eye))
            .observe(on_bridge_eye);
    }
    stream.requested = true;
}
