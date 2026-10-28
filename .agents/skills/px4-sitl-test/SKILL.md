---
name: px4-sitl-test
description: >-
  End-to-end check of Gazebo Harmonic + PX4 SITL stereo capture into a
  SurMap EuRoC session, on the WSL Ubuntu host (ROS 2 Jazzy, PX4 at
  ~/PX4-Autopilot, models at ~/src/PX4-gazebo-models). Use when asked to
  launch x500_surmap_stereo, bridge its cameras and GPS, dump a capture,
  export mav0, or confirm the simulation path in docs/simulation/px4-sitl.md.
---

# PX4 SITL → SurMap host check

Run this on the WSL host that has the simulator. CI does not. The
procedure follows [docs/simulation/px4-sitl.md](../../../docs/simulation/px4-sitl.md).

SurMap stays passive. `dump_sitl_capture.py` and
`export_sitl_session.py` only read. Take off by typing `commander
takeoff` in the PX4 `pxh>` console. Do not add a publisher, offboard
setpoint, or mission item under `src/surmap` or the dump script, and
do not `ros2 topic pub` a flight command.

Anything marked **unverified** has not been executed on this host.
Paste command output into the PR rather than rewriting the skill to
claim a pass you did not see.

Stop at the first failed step. Record the command, the output, and
which fix you tried.

## 0. Where you are

**Pass:** `uname -a` shows WSL, `pwd` is the SurMap repo, and these
exist:

- `~/PX4-Autopilot` (built `px4_sitl_default`)
- `~/src/PX4-gazebo-models`
- `/opt/ros/jazzy/setup.bash`
- `gz sim --versions` prints a version ≥ 8 (Harmonic)

**Fail:** any of those missing. Do not invent a different PX4 path.

The preflight table in the runbook was checked on this host once.
Re-check it; do not trust the table if a binary is gone.

## 1. Resource path and symlink

From the SurMap repo root:

```bash
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$(pwd)/docs/simulation/gz:$HOME/src/PX4-gazebo-models/models"
ln -sfn "$(pwd)/docs/simulation/gz/x500_surmap_stereo" \
  "$HOME/PX4-Autopilot/Tools/simulation/gz/models/x500_surmap_stereo"
```

`gz_env.sh` sets `PX4_GZ_MODELS` to `Tools/simulation/gz/models` and
spawns `file://$PX4_GZ_MODELS/$PX4_SIM_MODEL/model.sdf`. A copy that
lives only under `~/src/PX4-gazebo-models` is not the spawn path.
`model://surmap_stereo_cam` resolves from `docs/simulation/gz` on
`GZ_SIM_RESOURCE_PATH`.

**Pass:** `readlink -f ~/PX4-Autopilot/Tools/simulation/gz/models/x500_surmap_stereo/model.sdf` is the repo file, and `docs/simulation/gz/surmap_stereo_cam/model.sdf` exists.

**Fail / fix:**

- Symlink points at a missing file → rerun `ln -sfn` from the repo root.
- Later, spawn says the model cannot be found → the symlink is not in `Tools/simulation/gz/models`, or `PX4_SIM_MODEL` was not set (step 2).

## 2. Launch

`make px4_sitl gz_x500` is airframe 4001 (stock x500 quadrotor). It is
the right airframe because the stereo model includes `x500`. It does
not select the stereo model. `PX4_GZ_MODEL` is ignored.
`PX4_GZ_MODEL_NAME` only attaches to a model that is already running.
There is no `gz_x500_surmap_stereo` target.

```bash
cd ~/PX4-Autopilot
PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500
```

Leave this terminal open. It owns the `pxh>` prompt.

**Unverified:** this command has been checked against PX4 `main`
(`px4-rc.gzsim`, `gz_env.sh.in`, `4001_gz_x500`) and has not been
launched from this repo.

**Pass:** the PX4 console reaches `pxh>` and does not exit on a
missing model file.

**Fail / fix:**

- Gazebo GUI / OpenGL dies on WSL → stop, rerun with `HEADLESS=1` in front of `make`. That flag is from the PX4 Gazebo guide; the stereo model under `HEADLESS=1` is **unverified**.
- Console spawns plain `x500` → `PX4_SIM_MODEL` was unset or overridden. Quit and relaunch with the variable on the same line as `make`.
- Include of `x500` fails → stock x500 is missing from `PX4_GZ_MODELS`, or the `<uri>x500</uri>` include needs a `model://` prefix. Do not edit the SDF until the error text says the URI failed. Record the text.
- `surmap_stereo_cam` fails to resolve → step 1 resource path was not exported in the shell that launched PX4. `gz_env.sh` appends to `GZ_SIM_RESOURCE_PATH`; it does not drop a value you exported first.

## 3. Confirm the spawned model and both cameras

In a second terminal. Do not hardcode a world name. Discover it.

```bash
gz model --list
gz topic -l | grep -E 'x500_surmap_stereo_0|left_camera|right_camera'
```

**Unverified:** the `gz model` flag spelling (`--list` vs `-l`) was
not run here. If `--list` errors, run `gz model --help` and use the
list option it prints. Paste both the help text and the working
command into the PR.

**Pass:**

- The model list contains `x500_surmap_stereo_0` (PX4 appends the instance).
- `gz topic -l` shows two image topics whose paths contain `left_camera` and `right_camera` and the same model name. The SDF comment expects a shape like `/world/<world>/model/x500_surmap_stereo_0/link/camera_link/sensor/left_camera/image`. Treat that as a hint. The pass is the two names on the spawned model, not a guessed world string.

**Fail / fix:**

- Model is `x500_0` → step 2 launched stock x500. Stop SITL and relaunch with `PX4_SIM_MODEL`.
- Model name is right but only one camera topic → the `surmap_stereo_cam` include did not merge. Check the launch log for the include error before changing SDF.

Write down the two full image topic strings. You need them for the bridge.

## 4. Bridge cameras and GPS

PX4's own gz bridge does not publish these stereo cameras onto ROS.
Topic names come from step 3 and from `ros2 topic list`. The examples
in `dump_sitl_capture.py` (`/cam_left/image_raw`,
`/mavros/global_position/global`) are placeholders. Use one only if it
actually appears.

```bash
source /opt/ros/jazzy/setup.bash
gz topic -l | grep -iE 'left_camera|right_camera|navsat|gps'
ros2 topic list | grep -iE 'image|camera|navsat|gps'
```

If the image topics are only on the `gz` side, bridge the discovered
full names. Usual type pair, **unverified until an echo succeeds**:

```bash
ros2 run ros_gz_bridge parameter_bridge \
  "<left_image_gz_topic>@sensor_msgs/msg/Image@gz.msgs.Image" \
  "<right_image_gz_topic>@sensor_msgs/msg/Image@gz.msgs.Image"
```

Add the left `camera_info` topic the same way when `gz topic -l`
shows one (`sensor_msgs/msg/CameraInfo` / `gz.msgs.CameraInfo`). Add
GPS only for a topic `gz topic -l` actually prints
(`sensor_msgs/msg/NavSatFix` / `gz.msgs.NavSat` is the usual pair for
a Gazebo navsat). If `parameter_bridge` rejects the types, run
`ros2 run ros_gz_bridge parameter_bridge --help` and, for images,
`ros2 run ros_gz_image image_bridge --help`. Use what those print.
Do not guess a second topic name.

**Pass:**

- `ros2 topic info <left>` and `<right>` show `sensor_msgs/msg/Image`, and `ros2 topic hz` on each is near 20 Hz (the SDF `update_rate`) within a few hertz.
- `ros2 topic echo --once <left>` prints a frame with width 640 and height 480, unless a different `CameraInfo` is what you will pass to the dumper.
- GPS: either `ros2 topic echo --once` on the NavSatFix topic prints finite latitude and longitude, or you record "no GPS topic" and continue without `--gps`. A missing GPS topic is a failed GPS check, not a failed capture.

**Fail / fix:**

- `ros2` not found → source `/opt/ros/jazzy/setup.bash` in that shell.
- Bridge exits immediately → the gz topic string does not match `gz topic -l`. Copy it again.
- Hz stays 0 → SITL is paused or the bridge direction is reversed. Check `parameter_bridge --help` for the gz-to-ROS direction. Do not publish into Gazebo.

## 5. Take off (PX4 console only)

In the `pxh>` terminal from step 2:

```text
commander takeoff
```

**Unverified:** the exact console wording. **Pass** if a follow-up
`commander status` in that same console shows the vehicle armed and
in an auto takeoff or loiter state, or the console reports takeoff
detected. **Fail** if it stays disarmed.

**Fail / fix:** not on the ground / preflight failure → read the
`commander status` text (often local position or home). Do not bypass
it by publishing setpoints from ROS.

This command is PX4's. It is not a SurMap feature.

## 6. Dump

The dumper runs under the ROS interpreter, not `uv run`. It adds the
repo `src/` to `sys.path` itself. From the SurMap repo root, with
Jazzy sourced:

```bash
python3 -c "import rclpy, PIL"
python3 scripts/ros2/dump_sitl_capture.py \
  --left "<ros_left_image>" \
  --right "<ros_right_image>" \
  --left-info "<ros_left_camera_info_or_omit>" \
  --gps "<ros_navsat_or_omit>" \
  --baseline-m 0.07 \
  --seconds 15 \
  --output ~/sitl-runs/hover-01
```

Omit `--left-info` or `--gps` when step 4 did not find that topic.
`--left-info` fills intrinsics from `CameraInfo`. Without it the dump
uses the SDF defaults (640×480, fx=fy≈381.36, cx=320, cy=240).

**Pass:** exit code 0 and a final line `wrote N pairs (+ M GPS) → …`
with N ≥ 1. `~/sitl-runs/hover-01` contains `calibration.json`,
`frames.jsonl`, `images/left_*.png`, `images/right_*.png`, and
`gps.csv` when M ≥ 1.

**Fail / fix:**

- Exit text says to source Jazzy → step 4 shell setup.
- `No module named 'PIL'` → the ROS `python3` has no Pillow. Install Pillow for that interpreter. Do not switch the dump to `uv run`; that interpreter has no `rclpy`. **Unverified** whether this host's Jazzy python already has Pillow.
- `no stereo pairs captured` → topics were wrong, or stamps are farther apart than `--pair-slop-ns` (default 20 ms). Confirm `ros2 topic hz` on both images, then retry once with `--pair-slop-ns 50000000`. Report which value worked.
- `unsupported image encoding` → paste the encoding from `ros2 topic echo --once`. The dumper accepts `rgb8`, `bgr8`, and `mono8`.

## 7. Export

```bash
cd <surmap-repo>
uv run python scripts/export_sitl_session.py \
  --capture ~/sitl-runs/hover-01 \
  --output ~/sitl-runs/hover-01-euroc
```

An existing `mav0/` under the output directory is replaced.

**Pass:** exit code 0 and `exported N stereo pairs and M GPS checkpoints → …/mav0`, with the same N and M as the dump.

**Fail / fix:** missing `calibration.json` or `frames.jsonl` → step 6 did not write the capture. A non-zero exit that names a missing image file → the `frames.jsonl` path does not match `images/`.

## 8. Check `mav0`

```bash
uv run python - <<'PY'
import re
from pathlib import Path
root = Path.home() / "sitl-runs/hover-01-euroc/mav0"
for cam in ("cam0", "cam1"):
    text = (root / cam / "sensor.yaml").read_text()
    data = [float(x) for x in re.search(r"data: \[([^\]]+)\]", text).group(1).split(",")]
    pngs = sorted(p.name for p in (root / cam / "data").glob("*.png"))
    print(cam, "ty", data[7], "pngs", len(pngs), "first", pngs[:1])
imu = [ln for ln in (root / "imu0/data.csv").read_text().splitlines() if ln and not ln.startswith("#")]
print("imu_rows", len(imu), "first", imu[0])
print("gps", (root / "gps0/data.csv").is_file())
PY
```

**Pass:**

- `cam0` and `cam1` have the same PNG count, equal to N from the export, and the same filenames.
- `cam0` translation Y is negative, `cam1` Y is positive, and `cam1.Y - cam0.Y` is about `0.07` (the `--baseline-m`). Gazebo's left eye is at +Y; the export stores that eye at −Y because EuRoC body +Y points right.
- Rotation on both cameras is optical → EuRoC body: first row `0, -1, 0`.
- `imu0/sensor.yaml` exists. The first IMU data row ends with `9.81,0.0,0.0`. Row count covers the capture at 200 Hz (5_000_000 ns), not one row per frame.
- `gps0/data.csv` exists when the dump reported GPS, with header `t_ns,lat,lon,alt,accuracy_m`. `accuracy_m` is metres (square root of NavSat variance). A value of `1.0` is the fallback for a non-positive covariance, which is still a pass if latitude and longitude match the dump.
- There is no `cam0/data.csv` or `cam1/data.csv`. Readers use the PNG filenames. That absence is a pass.

**Fail / fix:** stale PNG names that are not in this capture → export again; the tool deletes `mav0/` first. If old names survive, say so; that is a regression. Wrong gravity axis (`…,0.0,0.0,9.81`) means the export is not using `stationary_imu_csv`.

## 9. Hand the session to SurMap

Two different tools. Do not treat a registry playback as this capture.

**Calibration load (required).** From the repo:

```bash
uv run python - <<'PY'
import re
from pathlib import Path
from surmap.demo.datasets import DatasetSpec, PreparedDataset, load_calibration
root = Path.home() / "sitl-runs/hover-01-euroc"
text = (root / "mav0/cam0/sensor.yaml").read_text()
res = re.search(r"resolution: \[(\d+), (\d+)\]", text)
stamps = tuple(sorted(int(p.stem) for p in (root / "mav0/cam0/data").glob("*.png")))
prepared = PreparedDataset(
    spec=DatasetSpec("sitl", "sitl", "", "", 1, "0" * 64, ""),
    root=root,
    timestamps_ns=stamps,
)
cal = load_calibration(prepared)
print(cal.width, cal.height, cal.fx, cal.baseline_m, "frames", len(stamps))
PY
```

**Pass:** width/height match the dump's `calibration.json`, `baseline_m` is about `0.07`, frame count is N. This is the loader `scripts/demo.py` uses. It does not start the demo.

**Demo playback of this export: not available.** `scripts/demo.py --dataset` only accepts registry ids (`euroc-v1-01-easy`). A SITL export is not a registry entry (deferred in the runbook). Playing V1_01 does not pass this step. `uv run python scripts/demo.py --list-datasets` is optional and only shows the registry.

**Sidecar calibration directory (optional, docker).** This starts a server; it does not replay the PNGs. Frames enter through the survey stream, which is the deferred live bridge.

```bash
uv run python -m surmap.survey.cm5_main \
  --slam-backend sidecar \
  --calibration-dir ~/sitl-runs/hover-01-euroc
```

**Pass:** the process stays up and does not exit on a missing `sensor.yaml` or `imu0/data.csv`. Stop it with Ctrl-C. **Fail:** immediate `SidecarError` or a missing-file traceback → step 8 is incomplete, or the pinned RTAB-Map image is not pulled (`scripts/fetch_rtabmap_fixture.py`). A running server with no map yet is a pass for this step. "RTAB-Map tracked these frames" is **unverified** here because this command does not read `cam0/data/*.png`.

## 10. Report back

Comment on the PR with:

- Pass or fail per step above.
- Model-list line that shows `x500_surmap_stereo_0`.
- The two `gz topic -l` image lines, and the ROS topic names you bridged and passed to the dumper (copied from the tools, not from this skill).
- Dump line `wrote N pairs …` and export line `exported N stereo pairs …`.
- The step 8 printout (`ty`, imu first row, gps).
- The step 9 calibration printout.
- Any step you did not run, marked unverified, with the reason.
- Any SDF or code change you were tempted to make. Do not make it on this checklist unless the failure is a repo bug and the PR owner asked for a fix.
