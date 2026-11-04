# Changeset: The simulation never waits on a slow station, and renders only what is seen

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Bug Fix
**Behaviour**: changes
**Complexity**: 4 — two packages (the Bevy PoC and `surmap.simulation`), concurrency / ordering semantics in the bridge

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + companion
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — reproduction tests, uncommitted (commits wait for the developer) · 3 pytest red (station handled `pair 1, 2, 3, 4`), 9 cargo red (missing fns)
  - [x] `tests/test_bevy_bridge_slow_station.py` red: the bridge stops reading while a pair is processed
  - [x] `preview::tests` red: cameras render only when seen or due; keypoints shown only while fresh, drawn into an overlay
  - [x] `tests/test_slam_streaming.py` red: a pair already written to the sidecar is still held by the backend
- [wf 3] ✅ 2026-11-04 `/green` Green — fix until the reproduction passes · pytest bridge/wire/perception 54 passed; cargo test 402 passed; wasm32 check clean
  - [x] Bridge: a connection's reader never waits on its session; a waiting pair is superseded by a newer one, a hello never is
  - [x] Page: the FPV is the live left eye; the newest fresh answer's keypoints overlay it (one image, not a node per dot)
  - [x] Page: in the preview, the chase view renders only in Overview, the left eye only in FPV, both eyes also in a frame whose pair is due
  - [x] Station: `StreamingRtabmapBackend` keeps each sent pair's `(frame_id, t_ns)`, not its images (memory no longer grows with the flight)
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — the preview's FPV and the bridge's reading
  - [ ] Changelog entry in `docs/simulation/changelog/`

## Initial Discovery

Full codebase exploration that grounded this plan:
[initial-discovery.md](./2026-11-04-sim-never-waits-on-station-initial-discovery.md).

## Summary

A slow station (RTAB-Map, SAM, PNG work on a busy laptop) must never stall anything: the bridge
keeps reading the page's socket and works on the newest pair, and the page's FPV shows the live
camera with RTAB-Map's keypoints over it while they are fresh. The page also stops rendering
cameras nobody sees.

## Technical Changes

### State A (Current)

- `serve_bevy_bridge` reads one message, processes it on a worker thread, answers, then reads the
  next; a slow session queues pairs in websockets and TCP and processes each one late.
- The preview's FPV shows a held frame only once RTAB-Map answered it (`HeldFrames`, 12); a queue
  deeper than that freezes the FPV. Keypoints are one UI `Node` each, respawned per answer.
- Both eyes render every frame; the chase view renders under the opaque FPV.

### State B (Target)

- **Bridge.** `serve_connection` runs a connection's reader and worker apart, joined by a
  `BridgeMailbox`: every hello is kept in order, a pair still waiting when a newer one arrives is
  skipped, and the worker always takes the newest. The reader never waits on `handle`; the
  connection ends once the reader ends and what was waiting is processed.
- **FPV.** The live left eye, always. `fresh_keypoints` keeps the newest answer's keypoints while
  its frame is at most `FRESH_FRAMES` behind the last frame sent; `keypoint_overlay` draws them
  into one transparent image over the eye. `HeldFrames` and the RGBA readback retire.
- **Rendering.** `preview_renders(view, pair_due)`: Overview renders the chase view, FPV the left
  eye, and a frame whose pair is due both eyes too. The full page and unattended runs keep every
  camera on.

### Delta

- `src/surmap/simulation/bevy_bridge.py`: `BridgeMailbox`, `serve_connection`;
  `bevy_wire.is_pair_message`.
- `examples/bevy-sitl-poc/src/preview.rs`: `preview_renders`, `fresh_keypoints`,
  `keypoint_overlay`, `PairDue`, the gating system; `HeldFrames`, `bgra_to_rgba`, `FpvFrame`
  retire.
- `src/surmap/slam/streaming.py`: `_frames` holds `(frame_id, t_ns)` per sent pair.
- `examples/bevy-sitl-poc/src/fleet/bridge_wasm.rs`: no RGBA copy; the latest answer and the
  last sent frame id feed the overlay; `PairDue` set in the frame the eyes are requested.

## Verification

**Method:** V1-fail→pass for the bridge and the pure page decisions; V4 for the page in a browser
**Command:** `uv run pytest -q tests/test_bevy_bridge_slow_station.py` and
`cd examples/bevy-sitl-poc && cargo test preview::`
**Before:** the bridge test fails — the station handles every pair in order (`pair 1, 2, 3, 4`);
the preview tests fail to compile (`preview_renders`, `fresh_keypoints`, `keypoint_overlay` missing)
**After:** both green.

V4 (needs the developer's consent; no harness renders the WASM page): `scripts/dev.sh --bridge`,
open the chat's simulation preview, take off — the FPV moves with the drone at the display rate
while keypoints arrive; throttle the station (stop the RTAB-Map container) — the FPV keeps
moving and the dots disappear instead of the view freezing.

## Decisions & Trade-offs

- **Live FPV over aligned dots.** #142 held frames so a dot never sat on another frame. Holding
  makes the view as slow as the station; the live eye with dots only while fresh (`FRESH_FRAMES`
  = 2, ≤ 200 ms at 10 Hz) trades a small misalignment in fast motion for a view that never stalls.
- **Skipped pairs are not counted in `dropped`.** `dropped` stays the backend's own count; the
  mailbox counts what it superseded for diagnosis only.
- **Out of scope** (initial discovery): the gray8 → PNG → gray8 round trip, `/sim/map`'s
  whole-map re-render.
