# Initial Discovery: Trackpad PTZ for the simulation chase view

**Changeset**: [2026-11-04-sim-trackpad-ptz.md](./2026-11-04-sim-trackpad-ptz.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

- The sim has no pointer camera control at all. `chase_camera`
  (`examples/bevy-sitl-poc/src/main.rs`) hard-codes the view behind the drone
  (`body.rotation * Vec3::new(5.0, 2.6, 7.5)`, `look_at` the drone) and flight input
  is keyboard-only (`read_controls`, `apply_thrust`: Space, Q/E, WASD, R/F).
- The developer chose the PTZ target: orbit the chase view around the drone —
  two-finger scroll pans/tilts the orbit, pinch zooms — with keyboard flight unchanged.
- Bevy 0.18 input seam: `MouseWheel` messages (`unit: Line|Pixel`, `x`, `y`) and
  `PinchGesture(f32)` messages (positive = magnify; macOS/iOS native, and the winit
  web backend surfaces trackpad input as wheel messages). Handling both covers
  native and browser builds.
- The orbit math is pure and belongs in its own module (`view_orbit.rs`) with unit
  tests, following `flight.rs`'s pattern of pure geometry + `#[cfg(test)] mod tests`.
  Default orbit must reproduce today's chase offset exactly so screenshot/record
  modes (which run unattended, no input) are unchanged.
- On-screen hint lives in `src/ui.rs` (`update_status`), page hint in
  `examples/bevy-sitl-poc/index.html`.

## Exploration 1: Current camera/input wiring — 2026-11-04

**Agent**: parent Grep/Read
**Scope**: `examples/bevy-sitl-poc/src/main.rs`, `ui.rs`, `flight.rs`, Bevy 0.18 input API

### Sequence

1. Grep `MouseWheel|Pinch|scroll|zoom|orbit` in the crate — no pointer input exists.
2. Read `main.rs` system wiring, `read_controls`, `apply_thrust`, `chase_camera`.
3. Read `ui.rs` `update_status` — the hint text to extend.
4. Read Bevy 0.18 `gestures.rs` / `mouse.rs` in the cargo registry — message shapes.

### Inspected files

#### `examples/bevy-sitl-poc/src/main.rs`

**Why**: where the chase view and input systems are wired.
**Excerpt**: `let back = body.rotation * Vec3::new(5.0, 2.6, 7.5);` in `chase_camera`;
Update systems list includes `read_controls` and `chase_camera.after(fly_scripted)`.

#### `bevy_input-0.18.1/src/gestures.rs`

**Why**: pinch semantics.
**Excerpt**: `pub struct PinchGesture(pub f32)` — "Positive delta values indicate
magnification (zooming in)".
