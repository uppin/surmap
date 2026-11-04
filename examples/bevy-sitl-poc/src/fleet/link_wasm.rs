//! The page's end of the fleet link (wasm only): with `?fleet=1`, a `web_sys::WebSocket` to the
//! station's `/sim/fleet?scenario=<id>` on the page's own origin. Inbound commands are queued and
//! drained each frame into `FleetLog::push` at `SimClock::now()`, answered `applied` / `refused`;
//! telemetry goes out every `TELEMETRY_PERIOD_S`. Natively there is no link (`--fleet-log` is the
//! native input).

use bevy::prelude::*;

/// Whether the page URL asks for the link (`?fleet=1`, via `link::fleet_enabled`).
pub fn page_fleet_enabled() -> bool {
    // TODO(pr-3): implement
    todo!("pr-3: implement")
}

/// Opens the link once the scene is built and runs it. Not added to the app until it is
/// implemented.
pub struct FleetLinkPlugin {
    /// The scenario the page runs (`?scenario=`).
    pub scenario: String,
}

impl Plugin for FleetLinkPlugin {
    fn build(&self, _app: &mut App) {
        // TODO(pr-3): implement
        todo!("pr-3: implement")
    }
}
