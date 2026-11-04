# The simulation never waits on a slow station, and renders only what is seen

**Date:** 2026-11-05
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · PR #152

A peer saw a major lag while the drone flew on a powerful Windows laptop. Every place that
waited on a slow station is gone, and the chat's preview stops rendering cameras nobody sees.

- **Bridge.** A connection's reader never waits on its session (`serve_connection`,
  `BridgeMailbox`): of the pairs waiting, only the newest is processed; a hello is never skipped.
  Before, pairs queued in websockets and TCP and were processed seconds late, in order.
- **Station memory.** `StreamingRtabmapBackend` kept every pair's PNGs for the whole session; it
  keeps `(frame_id, t_ns)` now.
- **FPV.** The live left eye, with RTAB-Map's keypoints as one overlay image while the answer is
  at most 2 frames old. #142's held frames (`HeldFrames`, `FpvFrame`) are retired: the FPV froze
  once the station fell 12 frames behind.
- **Rendering.** Preview: the chase view only in Overview, the left eye only in FPV, both eyes in
  a frame whose pair is read back. Before, both eyes (HDR, MSAA ×4, their own shadow cascades)
  rendered every frame for a 10 Hz stream, and the chase view rendered under the FPV.
- **Dev build.** The dev profile `scripts/dev.sh` serves builds dependencies at `opt-level = 3`
  (they were at 1).

Verified: reproduction tests for the bridge, the backend and the preview decisions failed before
and pass; `cargo test` 402, pytest 2631 passed / 38 skipped; the dev profile's flags recorded
before and after. The in-browser check is not yet run.
