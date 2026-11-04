//! The page's end of the fleet link (wasm only): with `?fleet=1`, a `web_sys::WebSocket` to the
//! station's `/sim/fleet?scenario=<id>` on the page's own origin. Inbound commands are queued and
//! drained each frame into `FleetLog::push` at `SimClock::now()`, answered `applied` / `refused`;
//! telemetry goes out every `TELEMETRY_PERIOD_S`. Natively there is no link (`--fleet-log` is the
//! native input).

use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;

use bevy::prelude::*;
use wasm_bindgen::closure::Closure;
use wasm_bindgen::JsCast;
use web_sys::{CloseEvent, ErrorEvent, MessageEvent, WebSocket};

use super::link::{decode_station, drone_telemetry, encode_applied, encode_hello, encode_refused, encode_telemetry, fleet_enabled, fleet_socket_url, refusal_text, StationMessage, TELEMETRY_PERIOD_S};
use super::log::FleetCommand;
use super::{fly_fleet, ActiveDrone, Fleet};
use crate::wildfire::SimClock;

/// Whether the page URL asks for the link (`?fleet=1`, via `link::fleet_enabled`).
pub fn page_fleet_enabled() -> bool {
    web_sys::window().and_then(|window| window.location().search().ok()).is_some_and(|search| fleet_enabled(&search))
}

/// Opens the link once the scene is built and runs it.
pub struct FleetLinkPlugin {
    /// The scenario the page runs (`?scenario=`).
    pub scenario: String,
}

impl Plugin for FleetLinkPlugin {
    fn build(&self, app: &mut App) {
        match FleetLink::open(&self.scenario) {
            Ok(link) => {
                app.insert_non_send_resource(link);
                app.add_systems(Update, (apply_station_commands.before(fly_fleet), send_telemetry.after(fly_fleet)));
            }
            Err(why) => warn!("fleet link: {why}"),
        }
    }
}

/// Commands the station sent, waiting for the next frame.
type Inbox = Rc<RefCell<VecDeque<(u64, FleetCommand)>>>;

/// The open socket, what it has received and the callbacks that feed it (kept alive with it).
struct FleetLink {
    socket: WebSocket,
    scenario: String,
    inbox: Inbox,
    said_hello: bool,
    since_telemetry_s: f32,
    _callbacks: (Closure<dyn FnMut(MessageEvent)>, Closure<dyn FnMut(CloseEvent)>, Closure<dyn FnMut(ErrorEvent)>),
}

impl FleetLink {
    fn open(scenario: &str) -> Result<Self, String> {
        let location = web_sys::window().ok_or("no window")?.location();
        let protocol = location.protocol().map_err(|_| "no page protocol")?;
        let host = location.host().map_err(|_| "no page host")?;
        let url = fleet_socket_url(&protocol, &host, scenario);
        let socket = WebSocket::new(&url).map_err(|_| format!("cannot open {url}"))?;

        let inbox: Inbox = Rc::default();
        let queue = Rc::clone(&inbox);
        let on_message = Closure::<dyn FnMut(MessageEvent)>::new(move |event: MessageEvent| {
            let Some(text) = event.data().as_string() else {
                warn!("fleet link: ignoring a binary frame");
                return;
            };
            match decode_station(&text) {
                Ok(StationMessage::Command { request, command }) => queue.borrow_mut().push_back((request, command)),
                Err(why) => warn!("fleet link: ignoring a station frame: {why:?}"),
            }
        });
        let on_close = Closure::<dyn FnMut(CloseEvent)>::new(|event: CloseEvent| {
            warn!("fleet link closed: code {} {}", event.code(), event.reason());
        });
        let on_error = Closure::<dyn FnMut(ErrorEvent)>::new(|event: ErrorEvent| warn!("fleet link error: {}", event.message()));
        socket.set_onmessage(Some(on_message.as_ref().unchecked_ref()));
        socket.set_onclose(Some(on_close.as_ref().unchecked_ref()));
        socket.set_onerror(Some(on_error.as_ref().unchecked_ref()));
        info!("fleet link: {url}");
        Ok(Self { socket, scenario: scenario.to_owned(), inbox, said_hello: false, since_telemetry_s: 0.0, _callbacks: (on_message, on_close, on_error) })
    }

    fn is_open(&self) -> bool {
        self.socket.ready_state() == WebSocket::OPEN
    }

    fn send(&self, frame: &str) {
        if let Err(why) = self.socket.send_with_str(frame) {
            warn!("fleet link: cannot send: {why:?}");
        }
    }
}

/// Says hello once the socket is open and the fleet is built, then pushes each queued command
/// into the fleet log at the simulation time and answers it.
fn apply_station_commands(mut link: NonSendMut<FleetLink>, clock: SimClock, fleet: Option<ResMut<Fleet>>) {
    let Some(mut fleet) = fleet else { return };
    if !link.is_open() {
        return;
    }
    let now = clock.now();
    if !link.said_hello {
        let drones: Vec<String> = fleet.log.drones().iter().map(|(id, _)| id.clone()).collect();
        link.send(&encode_hello(&link.scenario, now, &drones));
        link.said_hello = true;
    }
    let commands: Vec<(u64, FleetCommand)> = link.inbox.borrow_mut().drain(..).collect();
    for (request, command) in commands {
        let answer = match fleet.log.push(now, command.clone()) {
            Ok(seq) => encode_applied(request, seq, now),
            Err(refusal) => encode_refused(request, now, &refusal_text(&command, &refusal.reason)),
        };
        link.send(&answer);
    }
}

/// Reports every drone's phase and pose each `TELEMETRY_PERIOD_S`.
fn send_telemetry(mut link: NonSendMut<FleetLink>, time: Res<Time>, clock: SimClock, fleet: Option<Res<Fleet>>, active: Option<Res<ActiveDrone>>) {
    let Some(fleet) = fleet else { return };
    if !link.said_hello {
        return;
    }
    link.since_telemetry_s += time.delta_secs();
    if link.since_telemetry_s < TELEMETRY_PERIOD_S {
        return;
    }
    link.since_telemetry_s = 0.0;
    let drones: Vec<_> = fleet.log.drones().iter().filter_map(|(id, _)| fleet.state_of(id).map(|state| drone_telemetry(id, &state))).collect();
    let active = active.as_ref().and_then(|active| active.0.as_deref());
    link.send(&encode_telemetry(clock.now(), active, &drones));
}
