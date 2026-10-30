# SurMap — passive drone surveyor

[![CI](https://github.com/uppin/surmap/actions/workflows/ci.yml/badge.svg)](https://github.com/uppin/surmap/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue)](tests/)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue)](pyproject.toml)

A drone-mounted survey system that builds a semantic map of an area from
stereo video and GPS while the drone is flown by someone (or something) else.
Hackathon scope (civilian search-and-rescue mapping, credits, third-party
building blocks): [HACKATHON.md](HACKATHON.md).

**Current scope: passive survey only.**
SurMap observes and maps. It does not fly the drone.

Design: [docs/architecture.md](docs/architecture.md).
Code: a Python scaffold (data contracts, geometry, motion
classification, SLAM backend interface with an RTAB-Map adapter)
under `src/surmap/`, with tests under `tests/`.

## Development

Requires [uv](https://github.com/astral-sh/uv). The environment is
project-local (`.venv`), managed by uv:

```bash
uv sync --group dev   # create .venv and install dev tools
uv run pytest -q      # run the test suite
uv run ruff check src tests
uv run mypy           # strict type check (src and tests)
```

The project uses strong types: all code must pass `mypy` in strict
mode (configured in `pyproject.toml`). Untyped definitions, implicit
`Any` returns, and unreachable code are CI failures, not warnings.

CI (`.github/workflows/ci.yml`) runs ruff, mypy (strict), and pytest
on Python 3.11 and 3.12 for every push to `main` and every pull
request.

## Demo

```bash
uv run python scripts/demo.py            # serves the demo; downloads nothing at start
# open http://127.0.0.1:8765/ in a browser
```

The page has a scene picker with every registered scene. A scene not yet
in the cache is downloaded, verified and converted the first time it is
picked, with a progress bar on the page (MB downloaded, checksum, frames
extracted); later picks and launches are cache hits. Pause/Resume stops
feeding RTAB-Map as well as the video, so the map stays consistent;
Restart replays the scene. A new viewer takes the stream over (the
running one stops and its sidecar is removed).

The demo plays a recorded dataset as real-time video and builds the
RTAB-Map map live from the same frames as they play. Each frame is
shown once its own odometry has arrived, overlaid with the features
RTAB-Map tracked in that frame — rectified keypoints mapped back onto
the raw image through the rectification and lens distortion — coloured
by depth (red near, orange mid, teal far; without RTAB-Map the numpy
stereo matcher's points are shown instead). The map panel is a
top-down floor plan of the keyframes RTAB-Map's graph keeps, rendered
server-side from every map point into one image (each pixel the mean
camera intensity of its points, more opaque where points pile up, so
walls and edges read as lines) inside an extent that only grows, and
re-rendered whenever the graph is re-optimised;
a final optimized graph is drawn when playback ends. A yellow wedge on
the floor plan marks the camera for the frame on screen — its position
after RTAB-Map's map correction (so it stays on its trajectory after
loop closures), heading and horizontal field of view. The detector runs
on its own worker thread, so it never stalls playback. Datasets are registry entries in `surmap.demo.datasets`
(`--list-datasets`): the first pick downloads and SHA-256-verifies
the zip into the cache (`~/.cache/surmap/demo-datasets`, override
`--cache-dir`/`$SURMAP_DEMO_CACHE_DIR`); later runs download nothing.
Useful flags: `--frames N`, `--start I`, `--fps F`, `--no-rtabmap`,
`--rtabmap-mode live|batch` (default `live`; `batch` builds the map
at the end instead), `--prepare-only`. The live panel shows keyframe
count, cloud size, odometry state, SLAM lag in frames and dropped
frames. Add a dataset by adding one registry entry.

Scenes: `euroc-v1-01-easy` (indoor drone flight, ETH Vicon room),
`kitti-2011-09-26-drive-0009` (outdoor, a Karlsruhe city drive from a
car) and `ntu-viral-sbs-01` (outdoor drone flight over NTU Singapore's
Biological Sciences plaza). Each scene sets its own display size, playback rate, overlay
depth stops and keyframe depth cap (EuRoC 376×240, 20 Hz, 1/3/6 m;
KITTI 620×188, 10 Hz, 5/15/40 m, 30 m). KITTI raw is fetched from
KITTI's own host and converted locally into the EuRoC layout (grey
rectified `image_00`/`image_01`, calibration from `calib_cam_to_cam.txt`)
and never re-hosted. It is licensed CC BY-NC-SA 3.0 for academic,
non-commercial use; the page credits it. NTU VIRAL ships its stereo
images in a ROS 1 bag, read once with `rosbags` into the same layout;
its intrinsics are the dataset authors', its extrinsics come from
`cv2.stereoCalibrate` on the authors' own checkerboard pairs (the
published VINS-Fusion extrinsics reverse the rig). It is CC BY-NC-SA
4.0, non-commercial use; the page credits it. The streaming sidecar
resets lost odometry after one frame (`Odom/ResetCountdown=1`):
RTAB-Map's default never recovers.

The pinned RTAB-Map image is published for amd64 only: `docker build`,
`run` and `pull` pin `--platform linux/amd64`, so on Apple Silicon the
sidecar builds and runs under emulation with no extra setup.

RTAB-Map note: RTAB-Map has no official PyPI package, and no host —
local or CI — may install it. Two Docker backends exist. The demo's
default is `surmap.slam.StreamingRtabmapBackend`: a long-lived
`surmap-rtabmap-stream` process (librtabmap embedded in a small C++
tool, built into a derived image `surmap/rtabmap-stream:<hash>` FROM
the pinned image by `scripts/build_rtabmap_stream.py`) consumes
stereo pairs over stdin and emits the odometry pose per pair,
keyframe points per new keyframe, and optimized graph poses whenever
RTAB-Map re-optimizes and once at end of stream. It is stereo-only
(no IMU, no wheel odometry), never blocks playback (a bounded queue
drops the oldest pairs and counts them), and its `flush()` returns
the same shape as the batch backend. The batch backend is
`surmap.slam.SidecarRtabmapBackend`: it stages streamed stereo pairs
as a EuRoC-style dataset and runs the pinned RTAB-Map Docker image
(`rtabmap-euroc_dataset` + `rtabmap-export`) over it, returning
RTAB-Map's optimized poses and assembled cloud at end of stream. Run
`uv run python scripts/fetch_rtabmap_fixture.py` to pull the pinned
image and cut the EuRoC V1_01 test subset; the CM5 server selects the
sidecar with `--slam-backend sidecar --calibration-dir <dataset>`.
Teardown is ownership-based: the backend removes only the containers
it started (exact names, never a prefix/image sweep). To borrow a
reusable already-running container instead, set
`SURMAP_RTABMAP_SHARED_CONTAINER=<name>` (or
`--rtabmap-shared-container`): it is driven via `docker exec`/`cp`
and is never started, stopped, or removed by SurMap.
`surmap.slam.RtabmapBackend` remains for a host that does provide
native bindings, and tests/simulation otherwise use
`surmap.slam.InMemorySlamBackend`.

Object detection note: the on-board detector is a Coral Edge TPU
model behind `surmap.detection` — a Meta model was spiked first and
rejected on evidence (`docs/coral-edge-tpu-model-spike.md`), so the
detector is Coral-native EfficientDet-Lite0 INT8 by default, with
`ssd-mobilenet-v2` and `ssdlite-mobiledet` as alternative profiles
(`surmap.detection.MODEL_PROFILES`). Prepare artifacts with
`uv run python scripts/fetch_coral_model.py` (pinned SHA-256; the
Edge-TPU artifact runs on the CM5's Coral board, its CPU twin proves
the same network in CI). Detections travel on their own wire stream
(`Cm5SurveyService.StreamDetections`, keyed by `frame_id`, never
attached to survey frames); tracked objects also surface as survey
object points (designations ≥ 100). Choose the model at deploy time:

```bash
scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] \
    --model ssdlite-mobiledet [--coral-cpu]
```

or at process level with `--detector coral --coral-model <profile>
--coral-model-dir <dir> [--coral-edgetpu]`.

Station SAM note: the station's SAM 3.1 segmentation runs through
ONNX Runtime behind the `SamDetector` port
(`surmap.survey.sam3`): CUDA execution provider on the station GPU,
CPU provider in tests — the same session and adapter code, with a
tiny fake SAM3 ONNX model standing in for the weights in CI, so
tests have no separate path. Select it with
`python -m surmap.survey.station_main --detector sam3
--sam3-model <sam3.1.onnx>`. The real checkpoint is license-gated;
exporting it to the documented ONNX contract is a station
provisioning step.

## In scope now

- Capture synchronized stereo frames and GPS checkpoints on-board.
- Detect and track labeled objects on-board in real time: the Coral
  Edge TPU pipeline takes the camera input and returns labeled boxes
  with track IDs, including for moving objects.
- Estimate the camera trajectory with RTAB-Map — for map registration
  only, never for steering. RTAB-Map provides the points of the static
  scene.
- On-board, reconstruct the 3D points of detected objects from the
  stereo pair and add them to RTAB-Map's output as separate object
  layers: static objects merge into the map, moving objects stay as
  timestamped tracks and are never baked into the static scene.
- Segment objects with Meta's SAM 3.1 on the base station and project
  those regions onto the point cloud.
- Assign semantic labels to mapped objects, and a short scene note for
  the mapped area, with Meta's Muse Spark (see Model policy).
- Continuously update one semantic map tied to GPS coordinates.

## Explicitly deferred

- Autonomous navigation, path planning, and obstacle avoidance.
- Any interface to a flight controller — SurMap sends no flight commands.
- Mission orchestration and tasking of one or more drones.
- Route replanning based on the map.
- V-JEPA and other video-representation models.

Navigation may be revisited only after the passive survey pipeline works
end to end on real footage.

## Hardware — three machines

| # | Machine | Role |
|---|---|---|
| 1 | Raspberry Pi CM5 + Coral Edge TPU + stereo camera (candidate: ELP dual-lens module, see [docs/camera-elp-stereo.md](docs/camera-elp-stereo.md)) | On-board: stereo capture, labeled object detection and tracking on the Edge TPU, 3D reconstruction of detected objects layered onto RTAB-Map's static-scene output, GPS logging, recording and forwarding |
| 2 | ROS2 base station with NVIDIA RTX 5060 Ti | Ground processing: SAM segmentation, point-cloud/segment fusion, semantic map building, semantic labelling |
| 3 | Simulation machine: WSL Ubuntu + Gazebo Harmonic + PX4 SITL + ROS 2 Jazzy (see [docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md)). Other hardware still open | Synthetic stereo/GPS and replay of recorded sessions, so the pipeline can be developed and tested without flying |

The base station is a consumer of survey data only.
It issues no tasks or commands to the drone in this phase.

### Optional: Raspberry Pi AI Camera

Not part of the baseline build.
The stereo camera plus Coral already cover capture and detection, and a
third, monocular, uncalibrated camera would add no depth and a second
calibration problem.
Possible later uses, only if a concrete need appears: a low-power
wake-up/trigger sensor, or an independent downward view for experiments.
Do not design any pipeline stage around it for now.

## Model policy: Meta first

Use a Meta model wherever Meta offers one that fits the job.
Use a non-Meta model only where Meta has no suitable model, and record
that reason in [docs/architecture.md](docs/architecture.md).

| Job | Where | Model | Meta? |
|---|---|---|---|
| Object detection + tracking | Pi CM5 + Coral Edge TPU | Edge TPU detector (e.g. SSD MobileNet V2 / EfficientDet-Lite, Edge TPU-compiled) plus a lightweight box tracker | No — Meta has no Edge TPU detector; this is the documented exception |
| Segmentation + video tracking | Base station, RTX 5060 Ti | **SAM 3.1** | Yes |
| Semantic labelling and scene reasoning | Base station, via an API | **Muse Spark** | Yes |
| Pose / mapping | Pi CM5 | RTAB-Map | No — not a learned model; no Meta equivalent |
| Video representations | — | V-JEPA | Deferred |

SAM 3.1 notes: it detects, segments, and tracks objects in images and
video from text, exemplar, and visual prompts (Promptable Concept
Segmentation), and 3.1 adds object multiplexing for faster video
processing. Meta's published throughput figures are for an H100, so
throughput and VRAM on the RTX 5060 Ti must be measured, not assumed —
see the open decisions in the architecture doc.
Sources: [Meta SAM 3 announcement](https://ai.meta.com/blog/segment-anything-model-3/),
[SAM 3 paper page](https://ai.meta.com/research/publications/sam-3-segment-anything-with-concepts/).
Hackathon model ids and endpoints: [HACKATHON.md](HACKATHON.md).

## Data flow

```text
ON-BOARD (Pi CM5 + Coral Edge TPU)
  stereo frames (L/R) + GPS checkpoints + timestamps
        ├──► RTAB-Map (passive): trajectory + static-scene points only
        └──► Coral detector + tracker (left channel): labeled boxes,
             track IDs ─► Pi reconstructs each object's 3D points from
             the stereo pair, classifies it static vs moving against
             the RTAB-Map pose, and layers its points onto RTAB-Map's
             output (moving objects as timestamped tracks, never fused
             into the static scene)
        │
        ▼  recorded session / live stream (no flight commands, ever)
BASE STATION (ROS2, RTX 5060 Ti)
  stereo ─► depth ─► 3D point cloud (each point ↔ 2D pixel ↔ frame)
  SAM 3.1 segments and tracks objects in one video channel
        │   masks projected onto the point cloud, registered by RTAB-Map pose
        ▼
  objects / landmarks in 3D, anchored to GPS checkpoints
        │
        ▼
  Muse Spark assigns semantic labels and a scene note
        │
        ▼
  semantic map, updated as new survey data arrives
```

Details, ROS2 layout, interfaces, and data contracts:
[docs/architecture.md](docs/architecture.md).

## Roadmap

1. **Design** (now) — this document and the architecture doc.
2. **Simulation / offline pipeline** — stereo → point cloud → SAM 3.1 →
   map fusion on synthetic or recorded footage, developed on machine 3
   and machine 2 without flying. Machine 3's local path is WSL Ubuntu
   with Gazebo Harmonic, PX4 SITL, and ROS 2 Jazzy
   ([docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md)).
3. **On-board capture and detection** — CM5 + stereo camera + Coral:
   synchronized frames, detection/tracking, RTAB-Map trajectory, GPS,
   store-and-forward to the base station.
4. **Base station** — ROS2 nodes for ingest, SAM 3.1, fusion, map
   building, and Muse Spark labelling; one drone's footage at a time.
5. **Later, if at all** — multi-drone map merging, then navigation.

## Open decisions

- Stereo camera: ELP dual-lens module is the candidate; commit only
  after the bench tests in [docs/camera-elp-stereo.md](docs/camera-elp-stereo.md)
  pass (baseline measurement, L/R sync, depth range, CM5 sustained load).
- Which Edge TPU detector (SSD MobileNet V2 vs. EfficientDet-Lite) and
  which box tracker — to be settled by on-device benchmarks.
- SAM 3.1 on the RTX 5060 Ti: measured VRAM, resolution, keyframe rate,
  and whether video-mode tracking or per-image segmentation is used.
- Labelling cost and latency per session. Model ids and endpoints are
  in [HACKATHON.md](HACKATHON.md).
- Link between drone and base station (Wi-Fi / LTE / other), and
  therefore how much is processed live vs. store-and-forward.
- Simulation machine: dedicated hardware is still open. The local/WSL
  software path is Gazebo Harmonic + PX4 SITL + ROS 2 Jazzy
  ([docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md)).
- Exact GPS checkpoint format and frame↔GPS time synchronization.
- Map export format (GeoJSON-flavoured JSON is the current leaning,
  unconfirmed).

## From the original conversation

- Exposing the board and GPU APIs for external access — Mantas.
- Passive survey pipeline (stereo → cloud → SAM → semantic map) as above;
  navigation, V-JEPA, and drone orchestration are parked, not cancelled.
