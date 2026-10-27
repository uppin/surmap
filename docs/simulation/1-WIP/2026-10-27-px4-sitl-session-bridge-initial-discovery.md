# Initial discovery — PX4 SITL session bridge

**Changeset slug:** `2026-10-27-px4-sitl-session-bridge`
**Date:** 2026-10-27

## Combined Conclusions

- `feat/PX4_sitl` tip matched `main` at planning time: no PX4/Gazebo code yet.
- Machine 3 must emit sessions indistinguishable from flight
  (`docs/architecture.md` §2.3 / §4.3): `StereoFramePair` + `GpsCheckpoint`
  (+ calibration), no sim-only forks in CM5/station code.
- SurMap already consumes EuRoC `mav0/{cam0,cam1,imu0}/` via the demo and
  `SidecarRtabmapBackend`; that is the offline integration surface.
- ConnectRPC live stream exists for frames; GPS is in `types.py` but not yet
  on the survey proto — offline GPS file is enough for this PR.
- SurMap must not send flight commands (AGENTS.md scope guardrail).
- Gazebo/PX4 stay outside the package: SurMap takes a **SITL capture
  directory** (calibration + stereo images + GPS CSV) and writes EuRoC.

## Exploration 1

### Sequence

1. Read `README.md`, `docs/architecture.md` — Machine 3 contract, roadmap item 2.
2. `git` branch/diff — `feat/PX4_sitl` empty vs `main`.
3. Grep for PX4/Gazebo/SITL — no hits in source.
4. Inspect `src/surmap/demo/datasets.py`, `src/surmap/slam/sidecar.py`,
   `src/surmap/types.py`, `tests/test_demo.py` — EuRoC layout and yaml shape.
5. Inspect `proto/surmap/survey/v1/survey.proto` — no GPS messages yet.

### Findings

- First PR should be an edge exporter: capture dir → EuRoC session.
- Live ROS2 → ConnectRPC deferred.
- No `docs/**/1-WIP/` existed; simulation area is new.
