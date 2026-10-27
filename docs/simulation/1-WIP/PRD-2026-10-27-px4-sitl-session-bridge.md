# PX4 SITL session bridge — PRD

**Date:** 2026-10-27
**PRD Type:** Technical Improvement (new Machine 3 capability)

## Affected Features

- **Primary Feature:** Machine 3 simulation (new) — offline bridge from
  Gazebo/PX4 SITL sensor dumps into SurMap EuRoC sessions.
- **Related:** Demo / RTAB-Map sidecar — consume exported sessions unchanged.
- **Out of scope:** Base-station ROS2 nodes, CM5 flight interfaces, live
  ConnectRPC bridge, GPS on the survey wire proto.

## Summary

Operators with Gazebo + ROS2 Jazzy + PX4 SITL on WSL can dump stereo + GPS
into a SurMap capture directory and export a EuRoC-style session that the
existing demo and RTAB-Map sidecar already understand.

## Background

Architecture lists Gazebo as an unevaluated Machine 3 candidate. The
developer has a working PX4 SITL stack. SurMap is passive survey only:
PX4 flies; SurMap observes. Without a bridge, the SITL stack cannot feed
the Python scaffold.

## Proposed Changes

### What's Changing

- Add `surmap.simulation`: load a documented SITL capture directory and
  export EuRoC `mav0/` sessions (stereo PNGs, `sensor.yaml`, IMU stub,
  GPS CSV).
- Add `scripts/export_sitl_session.py` and a short runbook under
  `docs/simulation/`.
- Record Gazebo + PX4 SITL as the local/WSL Machine 3 choice for this
  path (architecture open decision, at wrap).

### What's Staying the Same

- No SurMap → PX4 commands.
- No sim-only branches in CM5 or station services.
- Demo, sidecar, and ConnectRPC contracts unchanged.

## Acceptance Criteria

1. Given a capture directory with calibration, paired stereo images, and
   GPS rows, the exporter writes a EuRoC layout SurMap tools can open.
2. L/R frames share `t_ns` filenames; calibration matches image size.
3. Tests cover the exporter with synthetic fixtures (no Gazebo in CI).
4. Docs state the passive-survey boundary clearly.

## Impact Analysis

- New package module + script + docs; no new runtime dependencies
  (Pillow already present). ROS2 stays on the operator machine only.
