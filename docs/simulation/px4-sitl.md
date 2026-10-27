# Machine 3: Gazebo + PX4 SITL → SurMap sessions

SurMap is a **passive** survey payload. PX4 SITL (or a human) flies the
vehicle; SurMap only consumes stereo frames, timestamps, and GPS.

This path is the offline bridge for WSL Ubuntu with Gazebo + ROS2 Jazzy +
PX4: dump sensors into a capture directory, export EuRoC, feed the
existing demo / RTAB-Map sidecar. No SurMap package may publish flight
commands, offboard setpoints, or mission items.

## Prerequisites (operator machine)

- Working PX4 SITL + Gazebo (your WSL stack)
- A **stereo** (or dual synchronized) camera on the airframe/world —
  default PX4 models are often monocular; add left/right cameras with a
  known baseline before trusting depth
- GPS / `NavSatFix` (or Gazebo GPS plugin) on a shared time base

## Capture directory layout

Fill this from ROS2 topics, a bag extract, or any script you own.
SurMap does **not** depend on `rclpy` / rosbag2.

```text
capture/
  calibration.json
  frames.jsonl
  gps.csv                 # optional
  images/
    left_000.png
    right_000.png
    …
```

`calibration.json` fields: `calibration_id`, `width`, `height`, `fx`,
`fy`, `cx`, `cy`, `baseline_m`, optional `rate_hz` (default 20).

`frames.jsonl` — one JSON object per line:

```json
{"frame_id": 0, "t_ns": 1000000000, "left": "images/left_000.png", "right": "images/right_000.png"}
```

`gps.csv` header: `t_ns,lat,lon,alt,accuracy_m`.

A checked-in example lives at `tests/fixtures/sitl_capture_tiny/`.

## Export

```bash
uv run python scripts/export_sitl_session.py \
  --capture /path/to/capture \
  --output /path/to/session-euroc
```

Produces `session-euroc/mav0/{cam0,cam1,imu0,gps0}/` in the shape the
demo and `SidecarRtabmapBackend` already understand.

## Feed SurMap

```bash
# Browser demo (registry datasets) or point tooling at the exported mav0/
uv run python scripts/demo.py
# CM5 / sidecar paths that accept --calibration-dir <euroc-root>
```

## Deferred (later PRs)

- Live ROS2 → ConnectRPC `RawVideoFrame` bridge
- GPS on the survey wire proto
- Register a cached SITL fixture as a demo dataset entry
