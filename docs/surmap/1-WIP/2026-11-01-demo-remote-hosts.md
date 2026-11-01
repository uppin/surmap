# Changeset: Demo page on remote CM5 + Station hosts, gated by server capabilities

**Date**: 2026-11-01
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — proto contract on two services, three wire-client adapters, page gating, new deploy target

## Workflow

- [wf 1] ✅ 2026-11-01 `/plan-red` Plan — changeset, initial discovery · this file + companion; decisions recorded below
- [wf 2] ✅ 2026-11-01 `/plan-red` Red — acceptance and failing lower-tier tests ·
  - [x] Capabilities: CM5 + Station report what they were built with (unary RPC)
  - [x] Remote adapters: CM5 backend/detections, Station SAM over real local servers
  - [x] Page: CM5 panes hidden when CM5 unreachable; SAM pane shows provider/device
  - [x] Demo CLI accepts --cm5-host/--station-host; deploy-demo script + unit
- [wf 3] ✅ 2026-11-01 `/green` Green — implement until every red test passes ·
  - [x] Proto `GetCapabilities` on both services + regenerated bindings
  - [x] Demo wire transport + remote adapters behind existing seams
  - [x] make_demo_server hosts wiring, page gating, demo CLI flags
  - [x] scripts/deploy-demo.sh + systemd unit; deploy on Station host
  - [x] Live verify: page on Station, Radxa CM5 map, Station GPU SAM, panes respect capabilities
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [x] `docs/deployment.md` — demo deployment documented

## Initial Discovery

[2026-11-01-demo-remote-hosts-initial-discovery.md](2026-11-01-demo-remote-hosts-initial-discovery.md)

## Decisions

- Full remote pipeline (not overlays-only, not launch-flag features).
- Feature knowledge comes from a new unary `GetCapabilities` RPC on
  both services, filled from each server's actual construction.
- CM5 panes are hidden while the CM5 host does not answer; Station
  panes work independently. The Radxa CM5 (10.88.77.14) is the CM5
  host for now (RTAB-Map only; detector disabled there).

## Prerequisites

Step 2b: no in-scope TODO/code-issue records. Nothing blocks.

## State A → State B

**State A.** The demo page runs every pipeline in its own process:
local RTAB-Map (Docker), local Coral, local SAM. Deployed servers are
not used, and nothing on the page reflects what a deployment actually
has enabled.

**State B.** The demo can be launched with `--cm5-host`/`--station-host`
and then streams the played dataset to those servers: CM5 survey
points/RTAB-Map map and Coral detections from the CM5, SAM analysis
from the Station. At startup it asks each host `GetCapabilities` and
renders only what that host has: e.g. the Radxa CM5 yields the
RTAB-Map pane with no Coral overlay and no object layer; the Station
yields the SAM pane labelled with its provider/device (GPU). A host
that does not answer contributes no panes.

**Delta.** Proto + both servers (capabilities), demo wire clients and
session wiring, page gating, demo CLI, demo deploy script/unit/docs.

## Verification

- `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`
- Live on the Station host: demo page serves, a played run shows the
  Radxa CM5's map growing and Station SAM detections (GPU), with
  Coral/object UI absent per the Radxa's capabilities.

## Verification record (2026-11-01)

- Gates: `uv run ruff check src tests`, `uv run ruff format --check
  src tests`, `uv run mypy` (strict) all pass; full pytest suite
  green (769 passed, 3 skipped).
- Live capabilities: Radxa `10.88.77.14:8080` reports
  `service=cm5, slam=streaming` (detections off); station
  `10.88.77.10:8081` reports `sam_analysis=true,
  provider="SAM 3.1 (PyTorch)", device="cuda:0"`, and
  `scripts/verify_station.py --expect-device gpu` prints
  `DEVICE station: GPU`.
- Live page on the station host (`surmap-demo`, port 8770 because
  8765/8766 are held by the user's older demo processes): HTTP 200
  with the cloud pane and RTAB-Map stat present, and the SAM pane
  labelled `SAM (GPU · SAM 3.1 (PyTorch) · cuda:0)`.
- Live bounded run (60 frames, `--frames 60` instance): 60 frame
  events, 60 SAM events, final event with `cloud_points: 1000` from
  the Radxa CM5. SAM `objects` were empty for the EuRoC `box`
  prompt (transport verified; content caveat known from the
  station deployment).
- Note: the Connect sync/async clients cannot stream a request
  body against the Hypercorn host, so `StreamSurvey` uses a small
  HTTP/2 (h2c) client in `surmap.demo.remote`; short exchanges and
  the unary capabilities call use plain HTTP/1.1.

## Follow-up fix (2026-11-01): RTAB-Map points on video + both panes

- Bug: with the remote CM5 the video showed no RTAB-Map points and
  both 3D reconstructions (cloud pane, floor plan) stayed empty
  during playback; the cloud only arrived at flush.
- Cause: the survey wire carried no odometry (the demo's video
  overlay is per-frame RTAB keypoints + pose), and the survey
  handler only emitted the streaming backend's points at flush
  (its per-pair result has no pose).
- Fix: `Cm5Response` gained an `odom` kind (`OdomUpdateOut`: pose,
  map-corrected pose, tracked keypoints, and the backend's
  rectification on first send). The survey handler drains landed
  odometry and the live `map_snapshot()` after every pair (and
  again after flush); `RemoteCm5Backend` stores them, so
  `frame_odometry`, `trajectory`, `rectification` and the live
  cloud behave like the local streaming backend.
- Red test first:
  `test_the_remote_backend_receives_odometry_and_live_points_before_flush`
  (stub-SLAM server); gates green (770 passed, 3 skipped).
- Live after redeploy (Radxa + demo): in a 100 s window, 300/302
  frame events carried keypoint overlays (up to 262 points/frame),
  and map events reached `cloud_points: 90000` with `keyframes: 28`
  during playback; both `cloud_png` and `floor_png` present.

## Follow-up fix (2026-11-01): wrong (stale) map on other datasets

- Bug: opening another dataset (KITTI) showed a static RTAB-Map
  cloud unrelated to it — the previous EuRoC run's map — and
  playback stalled.
- Cause: the CM5 server served every survey stream on one shared
  EuRoC-calibrated (376x240) streaming backend. The new live
  snapshot/odometry emission faithfully forwarded that backend's
  existing map and old odometry (frame_id collisions) into the new
  stream, and KITTI frames never matched the backend's calibration.
- Fix: `Cm5StreamConfig` carries the stream's own `cam0_yaml` /
  `cam1_yaml`. The demo sends its prepared dataset's scaled sensor
  YAMLs; the CM5 builds a fresh streaming backend per such stream
  and closes it with the stream (the local demo's per-dataset
  backend pattern, moved server-side). Streams without YAMLs (the
  verify scripts) keep the configured backend, but the handler now
  primes the point emitter with the pre-existing snapshot and drops
  odometry whose `t_ns` does not match the stream's pair, so a
  shared backend cannot leak a previous run's map or odometry.
- Red tests first:
  `test_each_survey_stream_gets_its_own_slam_built_from_the_stream_config`,
  `test_a_shared_slam_never_leaks_its_previous_map_or_odometry_into_a_stream`;
  gates green (772 passed, 3 skipped).
- Live after redeploy: KITTI stream — 202 frames in 110 s, 200 with
  keypoint overlays, cloud growing to 165k points, 169 keyframes,
  trajectory of 205 poses over a ~190 m extent (its own driving
  map); EuRoC regression stream — cloud to 85k as before.

## Follow-up fix (2026-11-01): 3D cloud cut to a 6 m streak outdoors

- Bug (from a user screenshot): KITTI played with overlay and floor
  plan working, but the 3D cloud was a thin near-road streak,
  unlike the local demo on main.
- Cause: the local demo builds its backend with the dataset's
  `max_map_depth_m` (KITTI 30 m); the CM5's per-stream factory did
  not pass one, so the backend kept its 6 m indoor default and
  dropped every deeper keyframe point.
- Fix: `Cm5StreamConfig.max_depth_m`; the demo sends the scene's
  `StreamBackendOptions.max_depth_m` (the same value the local
  backend gets) and the CM5 factory builds with it.
- Red test first: the per-stream factory test now asserts the
  config's `max_depth_m`; gates green (772 passed, 3 skipped).
- Live after redeploy: KITTI cloud bounding box 40 x 12.7 x 198 m
  (was a ~6 m-deep corridor), 185 frames with overlays in 110 s.

## Follow-up (2026-11-01): RTAB-Map frame rate on the page

- The RTAB-Map stat line now also shows the RTAB processing rate:
  a sliding-window (10 s) meter over the backend's newest odometry
  frame, emitted as `rtab_fps` on every map event and rendered next
  to Odometry/lag/dropped. It measures posed frames per second, so
  local and remote backends report the same quantity.
- Tests: `_RateMeter` unit test (25 fps over a 4 s advance, decay
  to 0 on stall) + map events carry `rtab_fps`; gates green
  (774 passed, 3 skipped). Live on KITTI: 1.6-3.0 fps reported by
  the Radxa during playback.

## Follow-up (2026-11-01): server-side runs; RTAB rate

- Architecture: playback no longer lives in a browser request.
  `_RunEngine` runs the player in its own thread on the Station —
  all frame exchange is CM5 <-> Station server-side — records
  history there, and publishes events; `/stream` only subscribes
  and renders, dropping intermediates for slow subscribers. A
  viewer disconnect (RST) no longer interrupts the run (new test
  `test_the_run_keeps_playing_server_side_after_the_viewer_leaves`);
  takeover, pause/resume and history contracts unchanged.
- RTAB rate: the CM5 handler was re-scanning the whole map
  snapshot per pair; it now emits only new keyframe points
  (vectorized placement, capped at the local backend's 1000
  points/keyframe). py-spy on the Radxa showed the handler's
  per-point Python placement as the top cost; after the fix the
  RTAB subprocess itself is the busy side (61% CPU).
- Live KITTI after redeploy: 208 frames/100 s, `rtab_fps` mostly
  4-6 (dips ~1.4 in a hard segment), vs 2-3 before and vs the
  ~17 fps on-device burst estimate for EuRoC-sized frames with
  drops allowed and nothing downstream. Disconnect test live:
  run timeline kept growing 66 -> 91 -> 109 after the viewer left.

## Follow-up (2026-11-01): SAM detections never displayed

- Cause 1: `StreamAnalysis` ignored the stream config's
  `concept_prompts`; the detector always used its build-time label
  (`object`, which grounds nothing in these scenes). Now the
  handler resets a re-promptable detector (`set_prompt`, added to
  `Sam31TorchDetector`) to the stream's first concept.
- Cause 2: mask polygons were garbage: the vendor masks are
  `(N, 1, H, W)` binary, and the detector outlined them without
  squeezing the channel dim (all y = 0) and without scaling the
  mask grid onto the frame. Both fixed in `Sam31TorchDetector`.
- Also fixed en route: a takeover could join a registered but
  not-yet-started run-engine thread (RuntimeError, empty reply),
  and the demo's dataset cache/history moved to a systemd
  `StateDirectory` (`/var/lib/surmap-demo`) after a station
  redeploy's `rsync --delete` wiped them from the shared home.
- Tests: stream-prompt, per-stream re-prompt, polygon scaling with
  channel-first masks, unstarted-engine join, demo unit state dir;
  gates green (780 passed, 3 skipped).
- Live: direct probe returns 11 cars with polygons inside their
  boxes; the page stream's SAM events carry objects throughout.
