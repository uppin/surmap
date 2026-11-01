# PX4 SITL → EuRoC session bridge

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `surmap.simulation`: load a documented SITL capture directory
(`calibration.json`, `frames.jsonl`, optional `gps.csv`, paired stereo
PNGs) and export a EuRoC `mav0/` session plus GPS CSV that the demo and
`SidecarRtabmapBackend` already understand. CLI:
`scripts/export_sitl_session.py`. Operator dump helper:
`scripts/ros2/dump_sitl_capture.py` (subscribe-only). Harmonic models
under `docs/simulation/gz/` provide stereo where stock PX4 models are
mono/depth-only. Runbook: `docs/simulation/px4-sitl.md`.

Verification: `tests/test_simulation_euroc_export.py` with
`tests/fixtures/sitl_capture_tiny/` (no Gazebo in CI). Deferred:
live ROS2 → ConnectRPC bridge and GPS on the survey wire proto
(`src/surmap/docs/todo/`).
