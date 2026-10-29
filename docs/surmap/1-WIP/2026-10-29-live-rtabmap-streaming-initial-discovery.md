# Initial Discovery: Live RTAB-Map streaming backend

**Changeset**: [2026-10-29-live-rtabmap-streaming.md](./2026-10-29-live-rtabmap-streaming.md)
**Date**: 2026-10-29
**Passes**: 1

## Combined Conclusions

- Batch backend `SidecarRtabmapBackend` (`src/surmap/slam/sidecar.py`) stages PNGs; poses/cloud only at `flush()` via `rtabmap-euroc_dataset` + `rtabmap-export`. Demo shows map only at end.
- `SlamBackend` protocol (`src/surmap/slam/base.py`): `process_frame`, `trajectory`, `close`; `FrameResult(frame_id, t_ns, pose, static_points)`.
- Pinned image `introlab3it/rtabmap@sha256:14a58ac3…` (RTAB-Map 0.24.2) present locally; headers `Rtabmap.h`, `Odometry.h`, `StereoCameraModel.h`, `SensorData.h`, `util3d.h` verified in-container; CMake config at `/usr/local/lib/rtabmap-0.24/RTABMapConfig.cmake`.
- Demo `DemoPlayer.events` (`src/surmap/demo/server.py`) paces frames server-side, calls `backend.process_frame` per frame, yields `frame`/`detections`, then `status` + `final` after `flush()`. Page draws map only on `final`.
- Ownership model to mirror: exact container names in `live_containers`, `docker rm -f` only those, idempotent `close()`, shared container borrowed never removed. Streaming rejects shared mode.
- Fixture: `tests/fixtures/euroc_v101_rtabmap/` (90 pairs via `scripts/fetch_rtabmap_fixture.py`); gated e2e pattern in `tests/test_survey_cm5_rtabmap_e2e.py`.

## Exploration 1: PRD grounding — 2026-10-29

**Agent**: parent Grep/Glob/Read
**Scope**: slam, demo, CI, fixture

### Sequence

1. Read `src/surmap/slam/base.py`, `sidecar.py`, `rtabmap.py`, `__init__.py` — contracts to stay compatible with.
2. Read `src/surmap/demo/server.py`, `datasets.py`, `scripts/demo.py` — demo wiring and calibration scaling.
3. Read `tests/test_slam_sidecar.py`, `tests/test_demo.py`, `tests/test_survey_cm5_rtabmap_e2e.py` — fake-docker, demo-player, gated-e2e patterns.
4. `docker run` header inspection of pinned image — C++ API surface.

### Inspected files

#### `src/surmap/slam/sidecar.py`

**Why**: batch semantics, ownership/teardown, pose/PLY formats.
**Excerpt**: `PINNED_RTABMAP_IMAGE`, `parse_exported_poses` (`qx qy qz qw`), `_live_containers` exact-name removal.

#### `src/surmap/demo/server.py`

**Why**: `DemoPlayer.events` pacing, SSE shapes, page map drawing.
**Excerpt**: `MAX_MAP_POINTS = 4000`; final event carries `cloud_xy`/`trajectory_xy`.

### Findings

See Combined Conclusions. M0 numbers recorded in the changeset `## Verification` after the spike.
