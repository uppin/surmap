# 2026-10-27 — Live ROS2 → ConnectRPC RawVideoFrame bridge

**Category:** Future enhancement
**Source:** `docs/simulation/1-WIP/2026-10-27-px4-sitl-session-bridge.md` (PR #18); plan §5
**Packages:** surmap
**Consent:** n/a — future enhancement (explicitly deferred from first Machine 3 PR)
**Status:** Open

## What is left

A long-running ROS2 node that subscribes to stereo Image topics and
streams `StereoCalibration` + `RawVideoFrame` into `Cm5SurveyService`
over ConnectRPC (live path), without a capture-directory round trip.

## Why it could not be done now

First PR proves the offline EuRoC contract. Live bridging needs a stable
topic map from the operator's Gazebo/ros_gz_bridge setup and must not
land before offline dump → export → demo/sidecar works on real SITL.

## What was done instead

Offline capture layout + `scripts/ros2/dump_sitl_capture.py` +
`export_sitl_session.py` → EuRoC.

## When it becomes possible

After one real Gazebo stereo+GPS dump exports cleanly and the demo /
sidecar produce a sane map from that session.
