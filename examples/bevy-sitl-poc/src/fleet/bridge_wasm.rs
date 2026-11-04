//! The page's stereo stream (wasm only): with `?bridge=ws://host:port`, a binary
//! `web_sys::WebSocket` to the station's stereo bridge. At scene ready it sends the `hello`
//! (camera profile, ground truth, scenario); then, on each tick `stream::StreamPacer` says is
//! due, it reads the eyes back (`Readback`, as `record.rs` does) and sends `wire::encode_pair`
//! labelled with `ActiveDrone`'s id, dropping the pair when the socket is backed up. The bridge's
//! status replies feed the map status line under the feed panel. Natively nothing streams.

use bevy::prelude::*;

/// The bridge socket the page URL names (`?bridge=`, via `stream::bridge_url`), if any.
pub fn page_bridge_url() -> Option<String> {
    // TODO(pr-5): implement
    todo!("pr-5: implement")
}

/// Opens the bridge socket once the scene is built and streams the active drone's eyes. Not
/// added to the app until it is implemented.
pub struct BridgeStreamPlugin {
    /// The bridge socket (`?bridge=`).
    pub url: String,
    /// The scenario the page runs (`?scenario=`), sent in the `hello`.
    pub scenario: Option<String>,
}

impl Plugin for BridgeStreamPlugin {
    fn build(&self, _app: &mut App) {
        // TODO(pr-5): implement
        todo!("pr-5: implement")
    }
}
