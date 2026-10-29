# Live RTAB-Map streaming backend — PRD

**Date**: 2026-10-29
**PRD Type**: Technical Improvement
**Status**: 🚧 In Progress
**Audience**: the implementing agent. Read `AGENTS.md` first and follow
it — TDD (`tdd` skill), fluent tests (`fluent-tests` skill), and the
`pr-lifecycle` flow (changeset + `-initial-discovery.md` companion in
this directory, `[wf]` rows, draft PR as `uppin`, wrap before ready).
This PRD is the requirement input to that flow, not a replacement for it.
Suggested classification: **Feature · adds** (preset *feature*).

## Affected Features

- **Primary**: RTAB-Map SLAM backend — `src/surmap/slam/` (new
  streaming backend beside `SidecarRtabmapBackend`), documented in
  `README.md` (*RTAB-Map note*) and `docs/architecture.md` §4.1
  (`rtabmap` component) and §9 (pose lost).
- **Primary**: Browser demo — `src/surmap/demo/server.py`,
  `scripts/demo.py`, documented in `README.md` § *Demo*.
- **Secondary**: CI — `.github/workflows/ci.yml` gains a real-container
  job for the streaming backend.
- **Not affected (explicitly)**: the CM5 survey server
  (`src/surmap/survey/cm5_server.py`, `cm5_main.py`) keeps the batch
  sidecar. Adopting the streaming backend there is a follow-up (see
  *Out of scope*).

## Summary

**Headline requirement: the RTAB-Map map is built in real time.** As
each stereo pair plays, it is tracked. Each new keyframe's points
appear on the map within **≤ 1 s of that frame being played**
(target; record the measured p50/p95 in `## Verification`), so the
map visibly grows frame by frame through the run. A map that appears
only at the end, or one refreshed by re-running batch tools on a
timer, does **not** meet this PRD.

Build the RTAB-Map map **while frames play**, not after. Add a
long-lived RTAB-Map sidecar process that consumes stereo pairs one at
a time over a pipe and emits, per pair, the visual-odometry pose and —
per new keyframe — that keyframe's local scene points, plus optimized
graph poses whenever RTAB-Map re-optimizes (loop closure / end of
stream). The demo map panel grows live from these updates.

The sensor setup is **a stereo camera only: no wheel odometry, no
IMU input**. All motion comes from RTAB-Map's stereo visual odometry
inside the sidecar.

## Background

Today `SidecarRtabmapBackend` (`src/surmap/slam/sidecar.py`) is batch
by construction: `process_frame` only stages PNGs as a EuRoC dataset,
and `flush()` then runs `rtabmap-euroc_dataset` + `rtabmap-export`
once over the whole run. In the demo
(`DemoPlayer.events`, `src/surmap/demo/server.py`) this means the map
panel shows *"Building the RTAB-Map map from all played frames…"*
for a long time after playback ends (full EuRoC V1_01 = 2,912 pairs,
and the pinned image is `linux/amd64`, so on Apple Silicon it runs
emulated).

RTAB-Map ships no CLI that accepts frames live; its dataset tools are
offline benchmarks. Robots get live I/O either through ROS
(`rtabmap_ros` stereo_odometry → rtabmap nodes over topics) or by
embedding `librtabmap` in-process (camera → odometry → Rtabmap, as
the RTAB-Map desktop app does). ROS 2 was considered and rejected for
now: a large new dependency for a passive surveyor, needing `rclpy`
or a bridge on the host. **Chosen approach: embed librtabmap in a
small C++ program, built inside the already-pinned image, driven over
stdin/stdout.**

Verified facts about the pinned image
(`introlab3it/rtabmap@sha256:14a58ac3…`, RTAB-Map 0.24.2, amd64):

- `/usr/bin/g++`, `/usr/bin/cmake` present.
- Headers under `/usr/local/include/rtabmap-0.24/rtabmap/core/`:
  `Rtabmap.h`, `Odometry.h`, `odometry/OdometryF2M.h`,
  `StereoCameraModel.h`, `SensorData.h`, `util3d.h`, `Parameters.h`.
- CMake package: `/usr/local/lib/rtabmap-0.24/RTABMapConfig.cmake`
  (`find_package(RTABMap)`), `librtabmap_core.so.0.24.2`.
- Not yet measured: per-frame odometry/SLAM cost under emulation.
  That is milestone M0 below.

Related open work this unblocks later:
`src/surmap/docs/todo/2026-10-27-moving-runtime-vo-increments.md`
(the CM5 path has no runtime VO; poses exist only at flush).

## Proposed Changes

### What's Changing

**1. C++ streaming tool — `surmap-rtabmap-stream`**

- Source in the repo, e.g. `deploy/rtabmap-stream/` (`main.cpp`,
  `CMakeLists.txt`, `Dockerfile`).
- Built into a derived image
  `FROM introlab3it/rtabmap@sha256:14a58ac3…` (the same digest as
  `PINNED_RTABMAP_IMAGE`; the Dockerfile must reference that constant's
  value, and a unit test asserts the two agree). Tag the derived image
  by a content hash of the tool's sources
  (`surmap/rtabmap-stream:<sha12>`) so a source change forces a
  rebuild and an unchanged source never rebuilds.
- Build entry point: `scripts/build_rtabmap_stream.py` (idempotent;
  `docker image inspect` the tag, `docker build` only if missing).
  The demo and the e2e fixture script call it. Nothing is installed
  on the host — the "no host RTAB-Map" rule in `README.md` holds.
- Inside, per input pair:
  1. Rectify left/right with a `StereoCameraModel` built from the two
     EuRoC `sensor.yaml` calibrations (intrinsics, radtan distortion,
     `T_BS` extrinsics → left→right transform), at the streamed
     resolution (the demo streams 376×240; calibrations already
     scaled by `scaled_sensor_yaml`). Rectification maps are built
     once at startup.
  2. Stereo visual odometry: `OdometryF2M` (`Odom/Strategy=0`) on
     `SensorData(left_rect, right_rect, stereoModel, id, stamp)`. **No
     IMU and no external odometry** are given to it.
  3. Feed odometry output into `Rtabmap::process(data, odomPose,
     covariance)`; respect `Rtabmap/DetectionRate` (start at 1–2 Hz;
     keyframes, not every frame, enter the map).
  4. For each **new keyframe** (new node id): compute its stereo cloud
     in the node's local frame (`util3d::cloudFromStereoImages` or
     `cloudFromSensorData`), voxel-downsample (`~5 cm`, tunable), drop
     non-finite points.
- Lost tracking: when odometry returns a null pose, emit `lost: true`
  with no pose; never guess (architecture §9). Let
  `Odom/ResetCountdown` re-initialize; a reset starts a new map
  session — emit it explicitly.
- Shutdown: on stdin EOF, run a final graph optimization, emit the
  final optimized poses of every node, then exit 0.
- Parameters passed as `--Param value` on the command line (RTAB-Map
  convention) so Python owns the tuning; defaults chosen in M0.

**2. Wire protocol (stdin/stdout, binary-safe, versioned)**

- Container started as `docker run -i --rm --name <owned-name> …`;
  stdin = requests, stdout = responses, stderr = logs (surfaced on
  error, last 2 KB, like `_subprocess_runner`).
- Startup: one `hello` request carrying protocol version, both
  sensor YAML texts, width/height, and parameter overrides; the tool
  answers `ready` (or an error and exits non-zero).
- Request per pair: 4-byte little-endian length + JSON header
  (`{"type":"pair","frame_id","t_ns","width","height","encoding"}`)
  followed by the two image payloads, each length-prefixed. Encoding
  `gray8` (raw) is the default; `png` optional. Decide in M0 which is
  cheaper end-to-end.
- Responses are **JSON lines** (one object per line, flushed per
  line):
  - `{"type":"odom","frame_id","t_ns","pose":[x,y,z,qx,qy,qz,qw]|null,"lost":bool,"ms":float}`
    — one per input pair, in input order.
  - `{"type":"keyframe","node_id","frame_id","t_ns","pose":[…],"points_local":[[x,y,z],…]}`
    — local-frame points; the pose is the node's current map-frame
    pose.
  - `{"type":"graph","poses":[{"node_id","pose":[…]},…],"final":bool}`
    — whenever the optimized graph changes (loop closure) and once
    with `final: true` at EOF.
  - `{"type":"error","message"}`.
- Frames: RTAB-Map's map frame, metres, same quaternion order as
  `parse_exported_poses` (`qx qy qz qw`). The same frame conventions
  as the batch sidecar, so downstream code does not branch.
- A protocol codec module in Python (pure functions, fully unit
  tested) encodes requests and decodes responses into typed frozen
  dataclasses. No `Any` leaves it (mypy strict).

**3. Python backend — `surmap.slam.StreamingRtabmapBackend`**

- Implements the `SlamBackend` protocol (`src/surmap/slam/base.py`).
- `process_frame(frame)` is **non-blocking**: it enqueues the pair
  for a writer thread and returns a `FrameResult` with the newest
  odometry pose already known for that frame, else `pose=None`. It
  never waits on RTAB-Map.
- **Backpressure, never a stall**: a bounded input queue (e.g. 4
  pairs). When full, the oldest unsent pair is dropped and counted
  (`dropped_frames`). The playback rate is never reduced by SLAM
  speed. Dropped pairs have no pose, which is honest.
- A reader thread parses stdout into an update queue. New method
  `poll_updates() -> list[MapUpdate]` drains it without blocking.
  `MapUpdate` is a typed union of `OdomUpdate`, `KeyframeUpdate` and
  `GraphUpdate`.
- `map_snapshot()` returns the current map assembled host-side: per
  keyframe, its local points transformed by that node's **latest**
  optimized pose. A loop closure therefore re-places old points
  correctly. Keep point counts bounded, as the demo does with
  `MAX_MAP_POINTS`.
- `flush()` closes stdin, waits (with a timeout) for the `final`
  graph, and returns `FrameResult`s in the same shape the batch
  backend returns: posed results in timestamp order, with the
  assembled cloud attached to the last one. Existing callers of
  `flush()` therefore keep working.
- `trajectory()` returns the current optimized keyframe poses
  (falling back to odometry poses before the first graph).
- Ownership and teardown are the same as the batch sidecar: one
  owned container name recorded in `live_containers`. `close()`
  terminates the process, `docker rm -f`s only that exact name,
  joins its threads, and is idempotent. It never sweeps by prefix or
  image. Shared-container mode (`SURMAP_RTABMAP_SHARED_CONTAINER`)
  is **out of scope** for streaming. If the variable is set,
  construction raises a clear `SidecarError` saying so; it never
  silently falls back.
- The process boundary goes behind a typed `Protocol` (as
  `CommandRunner` / `src/surmap/slam/rtabmap.py` do), so unit tests
  inject a fake process with scripted stdout and never need Docker.

**4. Demo — live map**

- `DemoPlayer` uses `StreamingRtabmapBackend` by default. A new flag
  `scripts/demo.py --rtabmap-mode {live,batch}` (default `live`)
  keeps the batch path selectable; `--no-rtabmap` is unchanged.
- During playback, after each frame, the player drains
  `poll_updates()` and emits a new SSE event **`map`**, throttled to
  about 2–4 Hz. Each event carries the sampled cloud XY, the
  trajectory XY, keyframe count, latest odometry state
  (`tracking` / `lost`), SLAM lag in frames (last input frame minus
  last odometry frame), and `dropped_frames`.
- The page redraws the map canvas on each `map` event. The fixed
  extent is replaced by an auto-fit that expands, not jitters: the
  extent only grows. The panel shows the live stats. Odometry is
  drawn amber and the optimized graph overlays it once one exists.
- At end of playback, the status reads *"Finalizing RTAB-Map
  graph…"*. Then `flush()` runs and the existing `final` event is
  sent, with the payload shape unchanged. The page copy changes from
  *"shown at the end"* to *"built live"*.
- Pacing is untouched: the server-side frame pacing in
  `DemoPlayer.events` still governs, and SLAM work happens on the
  backend's threads, never on the pacing loop.

### What's Staying the Same

- `SidecarRtabmapBackend` (batch) and all its tests, unchanged. The
  CM5 server keeps using it.
- `PINNED_RTABMAP_IMAGE` digest: no new upstream image.
- The scope guardrail: passive survey only. Object points are never
  fed into RTAB-Map, and nothing here steers anything.
- The SSE `frame` / `detections` / `final` event shapes.
- No new Python dependencies. No ROS.

## Impact Analysis

### Technical Impact

- New code: the C++ tool (about 200–400 lines), the protocol codec,
  `StreamingRtabmapBackend`, the image build script, and demo
  wiring. Existing modules only gain exports (`surmap.slam.__init__`)
  and the demo option.
- **Performance risk (primary).** The image is amd64-only. On Apple
  Silicon it runs under emulation. Stereo F2M at 376×240 is roughly
  10–30 ms/frame natively, and emulated it may be 2–5× slower.
  Mitigations, in order: the drop-oldest queue (stays live, loses
  frames), a lower `Rtabmap/DetectionRate`, `Vis/MaxFeatures`, odometry
  on every Nth frame (`--slam-stride`). An arm64 image build is
  noted as a follow-up, not this PR.
- Docker build time on first run (CMake build against the image's
  libs): about 1–3 min, once per source hash. The demo prints
  progress.
- Threads: one writer thread and one reader thread per backend. Both
  are daemons, and both are joined in `close()`.

### User Impact

- The demo map panel fills in during playback. The end-of-run wait
  shrinks to the final optimization (seconds).
- On a slow host the panel shows lag and dropped-frame counts rather
  than freezing.
- The first demo run after a source change builds the derived image
  first.

## Implementation Plan

Milestones map to TODOs under the changeset's Green row. M0 is a
gate: record its numbers in the changeset's `## Initial Discovery`
before writing the red tests that depend on them.

- **M0 — Spike (gate).** Build a minimal tool in the derived image.
  Feed it the 90-pair fixture (`scripts/fetch_rtabmap_fixture.py` →
  `tests/fixtures/euroc_v101_rtabmap/`) and the cached full V1_01
  (`~/.cache/surmap/demo-datasets/euroc-v1-01-easy/`). Record:
  - median and p95 ms/frame for odometry, and for odometry + SLAM;
  - keyframes created;
  - whether tracking holds through the sequence with stereo-only VO;
  - stdout throughput for keyframe point payloads.

  Go means tracking holds on the 90-pair fixture, the median is
  ≤ 100 ms/frame emulated (or the drop policy keeps lag bounded), and
  frame-to-map latency is on track for the ≤ 1 s real-time target. If
  not, **halt ⛔** per `pr-lifecycle` with the numbers and the
  mitigation options above.
- **M1 — Protocol codec.** Pure encode/decode with typed
  dataclasses. Unit tests: round-trips, malformed lines, version
  mismatch, partial reads.
- **M2 — C++ tool** to the protocol (hello/ready, odom per pair,
  keyframe, graph, final on EOF, lost tracking, errors to stderr
  with a non-zero exit).
- **M3 — `StreamingRtabmapBackend`** with a fake process.
  Unit-tested behaviours:
  - `process_frame` never blocks, even when the fake is stalled;
  - drop-oldest with `dropped_frames`;
  - `poll_updates` ordering;
  - `map_snapshot` re-places points after a `graph` update;
  - the `flush()` result shape matches the batch backend;
  - `close()` removes only its own container and is idempotent,
    including after a crashed process;
  - the shared-container variable is rejected;
  - the Dockerfile digest equals `PINNED_RTABMAP_IMAGE`.
- **M4 — Demo wiring.** Unit tests with a fake streaming backend:
  - `map` events are emitted *before* the last frame event;
  - they are throttled;
  - `final` still arrives;
  - the backend is closed on completion, on disconnect and on error
    (extend `tests/test_demo.py`);
  - `--rtabmap-mode batch` still yields the old sequence.
- **M5 — Real-container e2e.** `tests/test_slam_streaming_e2e.py`
  runs the real derived image over the 90-pair fixture. It is gated
  like `tests/test_survey_cm5_rtabmap_e2e.py`: it skips when the
  build or fixture is absent, and fails when
  `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`. It asserts that:
  - at least one odometry pose arrives before stdin is closed (live,
    not batch);
  - the trajectory travels more than 0.3 m;
  - the final cloud has more than 5k points;
  - no owned container survives `close()`.

  Add the CI job (copy the `rtabmap-e2e` job shape: fetch fixture,
  build the derived image, run the test).
- **M6 — Manual verification.** Run
  `uv run python scripts/demo.py --coral-model-dir tests/fixtures/coral_model`
  on the full sequence. Record in the changeset `## Verification`
  that the map grew during playback, plus the final keyframe count,
  the lag, the dropped frames, and a screenshot path.
- **Wrap.** Fold State B into `README.md` (*Demo*, *RTAB-Map note*)
  and `docs/architecture.md` §4.1 / §9. Write the changelog entry in
  `docs/surmap/changelog/`. Delete this PRD, the changeset and the
  discovery companion from `1-WIP/`. Then ready the PR.

All four gates (`ruff format --check`, `ruff check`, `mypy` strict,
`pytest -q`) must be green before every commit and push (`AGENTS.md`).
No new `# noqa` / `# type: ignore`.

## Acceptance Criteria

- [ ] M0 numbers recorded. Stereo-only VO tracks the 90-pair EuRoC
      fixture with no IMU or wheel odometry input.
- [ ] `surmap-rtabmap-stream` builds from repo sources into
      `surmap/rtabmap-stream:<hash>` `FROM` the pinned digest, with
      nothing installed on the host.
- [ ] `StreamingRtabmapBackend` satisfies `SlamBackend`.
      `process_frame` never blocks, overload drops the oldest pairs
      and counts them, and `flush()` returns the batch-compatible
      shape.
- [ ] Loop-closure `graph` updates re-place previously emitted
      keyframe points in `map_snapshot()`.
- [ ] Lost tracking yields `pose=None` / `lost: true`, never a
      guessed pose.
- [ ] `close()` removes only its own container, on success, error
      and disconnect, and is idempotent. Shared-container mode is
      rejected explicitly.
- [ ] **Real-time map:** keyframe points reach the demo map panel
      within ≤ 1 s of their frame playing (p50 and p95 measured and
      recorded). The map grows continuously through playback, not
      only at the end.
- [ ] Demo: the map panel updates during playback (`map` SSE
      events) and `final` still arrives. `--rtabmap-mode batch`
      preserves the old behaviour.
- [ ] Real-container e2e passes locally and in a new CI job.
- [ ] Full-sequence demo verified manually, with results recorded.
- [ ] All four lint/type/test gates green. The docs are wrapped and
      no `1-WIP/` files remain in the ready PR.

## Out of scope

- Switching the CM5 survey server (`cm5_server.py`'s `flush` path)
  or the moving-object observation buffer to live poses. The
  backend is designed to allow it, as a follow-up that closes
  `src/surmap/docs/todo/2026-10-27-moving-runtime-vo-increments.md`.
- ROS / ROS 2 integration.
- A native arm64 RTAB-Map image.
- IMU fusion (EuRoC has an IMU, but the target rig is stereo-only).
- Streaming in shared-container mode.
- Feeding dynamic-object masks to RTAB-Map (architecture §12 open
  decision).

## References

- `src/surmap/slam/sidecar.py`: the batch backend, ownership/teardown
  model and pose/PLY formats to stay compatible with.
- `src/surmap/slam/base.py`: the `SlamBackend` / `FrameResult`
  contract.
- `src/surmap/slam/rtabmap.py`: the typed-protocol pattern for
  native boundaries.
- `src/surmap/demo/server.py`: `DemoPlayer.events`, the SSE handler
  and the page.
- `src/surmap/demo/datasets.py`: `scaled_sensor_yaml` and
  calibration loading.
- `tests/test_slam_sidecar.py`, `tests/test_demo.py`,
  `tests/test_survey_cm5_rtabmap_e2e.py`: the fake-docker,
  demo-player and gated-e2e patterns to mirror.
- `scripts/fetch_rtabmap_fixture.py`, `tests/fixtures/euroc_v101_rtabmap.md`:
  the fixture.
- `.github/workflows/ci.yml` (`rtabmap-e2e` job): the CI job template.
- `docs/architecture.md` §1 (scope), §4.1, §7 (frames), §9 (failure
  modes).
- RTAB-Map 0.24.2 headers in the pinned image:
  `/usr/local/include/rtabmap-0.24/rtabmap/core/`. Its CMake
  config is at `/usr/local/lib/rtabmap-0.24/RTABMapConfig.cmake`.
