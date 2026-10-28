# Machine 3: Gazebo + PX4 SITL → SurMap sessions

SurMap is a **passive** survey payload. PX4 SITL (or a human) flies the
vehicle; SurMap only consumes stereo frames, timestamps, and GPS.

This path is the offline bridge for WSL Ubuntu with Gazebo Harmonic +
ROS2 Jazzy + PX4: dump sensors into a capture directory, export EuRoC,
feed the existing demo / RTAB-Map sidecar. No SurMap package may publish
flight commands, offboard setpoints, or mission items.

The host checklist (launch, bridge, dump, export, what to paste back)
is [.agents/skills/px4-sitl-test/SKILL.md](../../.agents/skills/px4-sitl-test/SKILL.md).

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

`make px4_sitl gz_x500` is the stock x500 quadrotor airframe (autostart
4001). It is the right airframe — `x500_surmap_stereo` includes that
x500 — but it is not the stereo model. Current PX4 (`px4-rc.gzsim` on
`main`) spawns `file://$PX4_GZ_MODELS/$PX4_SIM_MODEL/model.sdf`, and
`gz_env.sh` sets `PX4_GZ_MODELS` to `Tools/simulation/gz/models`.
`PX4_GZ_MODEL` is not read. `PX4_GZ_MODEL_NAME` only attaches to a
model that is already in the world. There is no
`gz_x500_surmap_stereo` make target.

Checked against those two PX4 files. Not launched from this repo.

```bash
# From the SurMap repo root, once per shell (or add to ~/.bashrc).
# model://surmap_stereo_cam resolves from this path. x500 resolves from
# PX4's own models directory, which gz_env.sh appends.
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$(pwd)/docs/simulation/gz:$HOME/src/PX4-gazebo-models/models"

# The spawn path is inside the PX4 tree, not GZ_SIM_RESOURCE_PATH.
ln -sfn "$(pwd)/docs/simulation/gz/x500_surmap_stereo" \
  "$HOME/PX4-Autopilot/Tools/simulation/gz/models/x500_surmap_stereo"

cd ~/PX4-Autopilot
PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500
```

The airframe script keeps a `PX4_SIM_MODEL` you already set
(`PX4_SIM_MODEL=${PX4_SIM_MODEL:=x500}`). PX4 names the spawned model
`x500_surmap_stereo_0`.

After launch, confirm Gazebo has **two** camera sensors
(`left_camera`, `right_camera`) on that model. If the include of
`x500` fails, the stock model is missing from `PX4_GZ_MODELS` or the
URI needs a `model://` prefix. Bridge the cameras to ROS 2 with
`ros_gz_bridge` (or your existing bridge). GPS should appear as `sensor_msgs/NavSatFix`
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
