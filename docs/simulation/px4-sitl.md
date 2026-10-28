# Machine 3: Gazebo + PX4 SITL → SurMap sessions

SurMap is a **passive** survey payload. PX4 SITL (or a human) flies the
vehicle; SurMap only consumes stereo frames, timestamps, and GPS.

This path is the offline bridge for WSL Ubuntu with Gazebo Harmonic +
ROS2 Jazzy + PX4: dump sensors into a capture directory, export EuRoC,
feed the existing demo / RTAB-Map sidecar. No SurMap package may publish
flight commands, offboard setpoints, or mission items.

## Preflight (verified on this WSL host)

| Piece | Status |
|---|---|
| Gazebo Harmonic (`gz`, `gz-sim8`) | Installed |
| PX4 SITL | `~/PX4-Autopilot` (`px4_sitl_default` built) |
| PX4 Gazebo models | `~/src/PX4-gazebo-models` — **mono / depth only** (no stereo) |
| ROS 2 Jazzy | `/opt/ros/jazzy` |
| SurMap stereo for Harmonic | [`docs/simulation/gz/`](gz/) — `surmap_stereo_cam` + `x500_surmap_stereo` |

Stock Harmonic airframes (`x500_mono_cam`, OakD-Lite depth, …) are **not**
enough for SurMap. Use the SurMap stereo models below (baseline **0.07 m**).

## Stereo model setup

```bash
# Once per shell (or add to ~/.bashrc)
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$(pwd)/docs/simulation/gz:$HOME/src/PX4-gazebo-models/models"

# Launch PX4 SITL with the stereo airframe (example — adjust to your PX4 launch style)
cd ~/PX4-Autopilot
PX4_GZ_MODEL=x500_surmap_stereo make px4_sitl gz_x500
# If your tree uses PX4_GZ_MODEL_NAME / world flags, point them at x500_surmap_stereo
# so left_camera + right_camera sensors exist.
```

Confirm in Gazebo that the airframe has **two** camera sensors
(`left_camera`, `right_camera`). Bridge them to ROS 2 with `ros_gz_bridge`
(or your existing bridge). GPS should appear as `sensor_msgs/NavSatFix`
(e.g. MAVROS `/mavros/global_position/global` or a Gazebo GPS bridge).

### Calibration defaults for the SurMap stereo SDF

| Field | Value |
|---|---|
| Resolution | 640 × 480 |
| Horizontal FOV | 1.3962634 rad |
| `fx` / `fy` | ≈ 381.36 |
| `cx` / `cy` | 320 / 240 |
| `baseline_m` | 0.07 |
| Rate | 20 Hz |

Gazebo's link frame is forward-left-up, so the left eye sits at **Y = +0.035**.
The exported `T_BS` uses the EuRoC body frame (+X up, +Y right, +Z forward),
the same sign as the demo fixture and real EuRoC `cam0`, so that eye is
written at **Y = −baseline/2**. The two numbers are one camera. The
rotation block maps the optical frame (+X right, +Y down, +Z forward)
into that body; `load_calibration` ignores it and reads only the translation.

Prefer filling intrinsics from left `CameraInfo` when available
(`dump_sitl_capture.py --left-info …`).

## Capture directory layout

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

## Dump from ROS 2 (operator)

```bash
source /opt/ros/jazzy/setup.bash
# Discover topics while SITL is running:
ros2 topic list | grep -iE 'image|camera|navsat|gps'

python3 scripts/ros2/dump_sitl_capture.py \
  --left <left_image_topic> \
  --right <right_image_topic> \
  --left-info <optional_camera_info> \
  --gps <optional_navsat_topic> \
  --baseline-m 0.07 \
  --seconds 15 \
  --output ~/sitl-runs/hover-01
```

This script **only subscribes** — it never sends PX4 commands.

## Export

```bash
uv run python scripts/export_sitl_session.py \
  --capture ~/sitl-runs/hover-01 \
  --output ~/sitl-runs/hover-01-euroc
```

Produces `…/mav0/{cam0,cam1,imu0,gps0}/` in the shape the demo and
`SidecarRtabmapBackend` already understand.

## Feed SurMap

```bash
# Point CM5 / sidecar tooling at the exported EuRoC root:
#   --calibration-dir ~/sitl-runs/hover-01-euroc
uv run python scripts/demo.py   # registry datasets; or use your export offline
```

## Deferred (later PRs)

Tracked under `src/surmap/docs/todo/`:

- Live ROS2 → ConnectRPC `RawVideoFrame` bridge
- GPS on the survey wire proto
- Demo dataset registry entry for a cached SITL fixture
