# Bevy WASM disaster simulation PoC

**Date:** 2026-11-02
**Feature:** Simulation

Added a browser-only proof of concept under `examples/bevy-sitl-poc`:
Bevy 0.18 (WebGPU) renders a simplified disaster block, Rapier flies
a quadcopter through it, Feronia scatters ground debris, and a stereo
rig on the drone renders real 640×480 left/right targets while the
page prints the calibration the rig itself produces (fx = fy =
381.36 px, baseline 0.07 m, FOV derived from the intrinsics). Frames
stay in the page — nothing is sent to a backend. A GitHub Actions
workflow (`.github/workflows/bevy-wasm.yml`) compiles the bundle and
runs the calibration tests on every change to the PoC. Verified in
Chrome on this Mac: takeoff, climb, translation, yaw, and landing,
with the stereo feeds tracking the flight.
