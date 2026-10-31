# SurMap — passive drone surveyor

[![CI](https://github.com/uppin/surmap/actions/workflows/ci.yml/badge.svg)](https://github.com/uppin/surmap/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue)](tests/)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue)](pyproject.toml)

SurMap is a civilian disaster-response mapper. A drone carries it over
an affected area and it builds a map from stereo video so a
search-and-rescue team can see landmarks, debris, and vehicles. A
separate pilot or a separate autopilot flies the aircraft. SurMap never
sends flight commands, and it does not identify people: no face
recognition and no identity. A text label on a map point, including the
fixture word `survivor` on the mission demo, is not identification.

Hackathon scope, credits, and what is only on an open pull request:
[HACKATHON.md](HACKATHON.md).

**Current scope: passive survey only.**
SurMap observes and maps. It does not fly the drone.

Design: [docs/architecture.md](docs/architecture.md).
Code on `main`: survey contracts and servers, stereo, Coral detection,
RTAB-Map, the dev demo below, the moving-object pipeline, a SAM 3.1
ONNX adapter tested with a fake model, and a Muse Spark scene-note
client. A GPS-tied semantic map and mask projection are not on `main`.

## 60-second demo

The hackathon demo is `scripts/mission_demo.py` on
[PR #48](https://github.com/uppin/surmap/pull/48)
(`feat/segmentation-protocol-guidelines`), which contains every commit
on [PR #39](https://github.com/uppin/surmap/pull/39). It is not on
`main` until that PR lands. `scripts/demo.py` (EuRoC, KITTI, NTU VIRAL)
is the secondary dev demo and is on `main` today.

Offline, the default, uses the recorded fixture
`tests/fixtures/sitl_capture_tiny/` on that branch. It does not download
a dataset, does not start Docker, and does not call Meta, Baseten, or
Modal.

```bash
uv sync
uv run python scripts/mission_demo.py
# viewer: http://127.0.0.1:8770/
```

A live run is the same script with `--live --capture <dir>`.
`build_live_services` in `src/surmap/mission/demo.py` on #48/#39
refuses to start unless every item below is true. This is the current
gate, not a shorter one:

- `SURMAP_LIVE_META=1` and a non-blank `MODEL_API_KEY` (scene note, and
  SAM, because this flag selects Meta SAM)
- `SURMAP_LIVE_BASETEN=1` and a non-blank `BASETEN_API_KEY` (per-object
  labels). The live mission does not start without this flag
- If `SURMAP_LIVE_MODAL=1` is also set, `MODAL_SAM_URL` must be
  non-blank or startup raises. With `SURMAP_LIVE_META=1`, the SAM
  provider is still Meta (`sam = "meta" if meta else "modal"`)

```bash
export SURMAP_LIVE_META=1
export MODEL_API_KEY='your-key'       # single quotes
export SURMAP_LIVE_BASETEN=1
export BASETEN_API_KEY='your-key'
uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01
```

The live path feeds the capture to `StreamingRtabmapBackend`, so Docker
is required and the image is pinned to `linux/amd64`
(`surmap.slam.streaming.PINNED_PLATFORM`). The process does not enable
PX4 motors. Where a PX4 runbook says "armed", that word is PX4's
motor-enable state.

Ask the map (`python -m surmap.mapqa`) is on
[PR #41](https://github.com/uppin/surmap/pull/41), not on `main`, and
not inside `scripts/mission_demo.py`. The mission viewer's `POST /ask`
looks for `surmap.mapqa.answer`, which #41 does not export, so that
request stays on the local label match. Details:
[HACKATHON.md](HACKATHON.md).

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

## Dev demo (EuRoC, KITTI, NTU VIRAL)

This is the secondary demo. It plays a recorded dataset. It is not the
hackathon mission demo above.

```bash
uv run python scripts/demo.py            # serves the demo; downloads nothing at start
# open http://127.0.0.1:8765/ in a browser
```

Docker is required when RTAB-Map is on. The streaming backend passes
`--platform linux/amd64` on `docker build` and `docker run`
(`surmap.slam.streaming.PINNED_PLATFORM`).
`scripts/fetch_rtabmap_fixture.py` passes the same platform on
`docker pull`. The batch sidecar's `docker run` does not pass
`--platform`. `--no-rtabmap` sets `with_rtabmap=False`,
so the server builds no SLAM backend and does not need Docker. The
flag's help text says "skip the final RTAB-Map map".

Dataset zips, from `surmap.demo.datasets` (the downloader prints
`size_bytes / 1e9` to two decimals):

| Scene | Bytes | Printed size |
|---|---|---|
| `euroc-v1-01-easy` | 1,149,702,102 | 1.15 GB |
| `kitti-2011-09-26-drive-0009` | 1,791,264,044, plus calibration zip 4,068 | 1.79 GB |
| `ntu-viral-sbs-01` | 3,775,725,925 | 3.78 GB |

Nothing is fetched until a scene is picked, or until `--prepare-only`.

The page has a scene picker with every registered scene. A scene not yet
in the cache is downloaded, verified and converted the first time it is
picked, with a progress bar on the page (MB downloaded, checksum, frames
extracted); later picks and launches are cache hits. Pause/Resume stops
feeding RTAB-Map as well as the video, so the map stays consistent;
Restart replays the scene. A new viewer takes the stream over (the
running one stops and its sidecar is removed).

The page is a generic test console: every run is persisted as it streams
to a SQLite database (`<cache-dir>/demo-history.db`, override with
`--history-db`), with one row per shown frame (image, overlay points,
camera), its detections, and a point-cloud snapshot per map update. The
timeline under the video rewinds and winds forward through the persisted
run — each moment shows that frame's image and overlay points with the
point cloud as it was at that moment — and earlier runs can be re-opened
from the persisted-runs picker (`GET /runs`,
`GET /runs/<id>/snapshot?seq=N`). The point-cloud pane is a 3D WebGL view
(sampled to 12,000 points for display): drag its corner to resize it,
use Fullscreen to expand it, and drive it with the Pan/Tilt/Zoom buttons,
drag to orbit, Shift+drag to pan and wheel to zoom. The top-down floor
plan remains alongside it as a mini-map.

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
at the end instead), `--prepare-only`. `--sam-device cuda:0`
additionally runs the real SAM 3.1 (`facebook/sam3.1`, downloaded
with `HF_TOKEN` from the project `.env`) in continuous (video) mode
on that GPU and draws its masks, with SAM's persistent object ids,
on the frame preview for each frame; `--sam-label` is the concept
prompt (`car` on KITTI) and `--sam-model` can name another HF id, a
local `.pt`, or an `.onnx` export instead. SAM propagates in
16-frame windows so a long video fits a 16 GB card (ids restart per
window). The PyTorch stack is an optional install in `.venv` (see
`scripts/demo.py --help`). With the live map, each SAM result's masks
are also placed in 3D: the sidecar's dense stereo under each mask on
that frame, and the station assigns every one of those points to a
persistent object *surface* (`surmap.survey.surfaces`). A mask whose
points land where an earlier frame's points were already assigned
continues that surface (so SAM's id restarts do not split an object),
otherwise it starts a new one. The 3D pane draws the surface layer:
static surfaces translucent, one colour per surface; a surface that has
drifted 40 cm or more from where it was first seen is a moving object's
smear, drawn red and more opaque. The Hide/Show surfaces button toggles
the layer. Surfaces are persisted with the run (`surface_points` in
`demo-history.db`), so scrubbing and re-opened runs show them as they
were at each frame. `--sam-fake` does the same without a GPU or model —
a stand-in SAM outlines the centre of every frame. The live panel shows keyframe
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

The streaming backend and `scripts/fetch_rtabmap_fixture.py` pin
`--platform linux/amd64`, as in the prerequisite note above. That
script's comment says the image is amd64-only and an arm64 host pulls
it for emulation. The batch sidecar does not pass `--platform`.

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
`--slam-backend streaming --calibration-dir <dataset>` runs the live
sidecar instead (`--frame-size`, default `376x240`): poses arrive while
the survey streams, and the same sidecar serves
`Cm5SurveyService.StreamRegionPoints` — a frame id, channel and polygon
(e.g. a SAM mask) in, every dense-stereo point inside it on that frame
out, in the map frame. Frames stay queryable for `--region-buffer-s`
(default 10 s); older ones are answered `FRAME_EXPIRED`.
Teardown is ownership-based: the backend removes only the containers
it started (exact names, never a prefix/image sweep). To borrow a
reusable already-running container instead, set
`SURMAP_RTABMAP_SHARED_CONTAINER=<name>` (or
`--rtabmap-shared-container`): it is driven via `docker exec`/`cp`
and is never started, stopped, or removed by SurMap.
`surmap.slam.RtabmapBackend` remains for a host that does provide
native bindings, and tests/simulation otherwise use
`surmap.slam.InMemorySlamBackend`.

Object detection note: the on-board detector is Coral, behind
`surmap.detection`. The default profile is EfficientDet-Lite0 INT8,
with `ssd-mobilenet-v2` and `ssdlite-mobiledet` as alternatives
(`surmap.detection.MODEL_PROFILES`). Prepare artifacts with
`uv run python scripts/fetch_coral_model.py` (pinned SHA-256; the
Edge-TPU artifact runs on the CM5's Coral board, its CPU twin proves
the same network in CI). Detections travel on their own wire stream
(`Cm5SurveyService.StreamDetections`, keyed by `frame_id`, never
attached to survey frames). Tracked objects also surface as survey
object points. A designation is a map-layer id on that wire: `1` is
the static scene, and object points use `100 + track_id`. Choose the
model at deploy time:

```bash
scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] \
    --model ssdlite-mobiledet [--coral-cpu]
```

or at process level with `--detector coral --coral-model <profile>
--coral-model-dir <dir> [--coral-edgetpu]`. The CM5 process defaults
to `--detector none`.

A Meta detector was spiked for the Edge TPU and rejected. That note
is [docs/coral-edge-tpu-model-spike.md](docs/coral-edge-tpu-model-spike.md).
It is history, not the detector this tree runs.

Station SAM note: `surmap.survey.sam3` is an ONNX Runtime adapter
behind `SamDetector`. The same session code asks for the CUDA provider
when `--sam3-device cuda` (or `auto` and CUDA is installed) and uses
CPU otherwise. Tests and CI run
`tests/fixtures/sam3_fake/fake_sam3.onnx`, generated by
`scripts/make_fake_sam3_model.py`. That file is not SAM 3.1 weights.
No real ONNX export is in the tree. The station process defaults to
`--detector memory`, which returns no boxes. The ONNX adapter is
selected only with:

```bash
python -m surmap.survey.station_main --detector sam3 \
    --sam3-model <path-to-an-onnx-file>
```

The module docstring calls exporting a real checkpoint a station
provisioning step. This repository does not do that export. Meta API
SAM and Modal SAM are on PR #48/#39, not here. See
[HACKATHON.md](HACKATHON.md).

## On main

- Stereo reconstruction from a frame pair (`surmap.survey.stereo`),
  and survey servers that stream those points.
- Coral detection and tracking when `--detector coral` is selected.
  The CM5 server default is `--detector none`.
- RTAB-Map trajectory and a static-scene cloud when a Docker backend
  is selected (`--slam-backend sidecar`, or the streaming backend in
  the dev demo). The CM5 server default is `--slam-backend inmemory`.
  The pose is for the map, not for steering. Object points are not
  written back into RTAB-Map.
- Object points from stereo inside a tracked box, kept as a separate
  map layer from the static scene. Moving-object code is under
  `surmap.moving`.
- A Muse Spark scene-note client, `muse-spark-1.3` on the Meta Model
  API (`surmap.labelling.meta_muse`). Nothing on `main` calls it from
  the demo. Per-object labels are not on `main`.

## On PR #48 (and #39), not on main

- `scripts/mission_demo.py`, the hackathon demo.
- Mask projection (`surmap.survey.mask_cloud.points_in_mask`).
- A semantic-map snapshot that stores GPS (`surmap.map.snapshot`).
- Baseten labels, Meta API SAM, and Modal SAM. The live mission
  requires `SURMAP_LIVE_BASETEN=1` and `SURMAP_LIVE_META=1`.
- The fictional civilian earthquake-and-flood block under
  `docs/simulation/`.

Ask the map is PR #41, not #48.

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
| 1 | Raspberry Pi CM5 + Coral Edge TPU + stereo camera (candidate: ELP dual-lens module, see [docs/camera-elp-stereo.md](docs/camera-elp-stereo.md)) | On-board role: stereo capture, Coral detection and tracking, object points layered on RTAB-Map. `GpsCheckpoint` has no caller on `main` |
| 2 | Base station with NVIDIA RTX 5060 Ti | Ground processing. On `main` the station server can load the ONNX SAM adapter; real SAM 3.1 weights are not in the tree. ROS 2 nodes are design intent in the architecture doc, not a package in this repo |
| 3 | Simulation machine | Not in this tree. [PR #18](https://github.com/uppin/surmap/pull/18) and [PR #48](https://github.com/uppin/surmap/pull/48) carry Gazebo Harmonic + PX4 SITL + ROS 2 Jazzy and a fictional civilian earthquake-and-flood block. `docs/simulation/px4-sitl.md` is on #48, not here. "Armed" in that PX4 path means the motor-enable state |

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
| Segmentation | Station ONNX adapter on `main` (fake weights in CI). Meta API and Modal GPU on PR #48/#39 | **SAM 3.1** | Yes |
| Scene note | Meta Model API (`muse-spark-1.3`) | **Muse Spark**, client on `main` | Yes |
| Per-object labels | Baseten, on PR #48/#39 only | **Muse Spark Open** (`meta-models/muse-spark-open-1026`) | Yes |
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

The diagram is the intended pipeline. On `main`, mask projection and
the GPS-tied semantic map are absent. The scene-note client is
`muse-spark-1.3` via the Meta Model API
(`surmap.labelling.meta_muse`). ROS 2 node names in the architecture
doc have no package in this repo.
Details: [docs/architecture.md](docs/architecture.md).

## Roadmap

1. **Design** — this document and the architecture doc. Implementation
   on `main` is past a scaffold; see "On main" above.
2. **Simulation / offline pipeline** — the hackathon path is
   `scripts/mission_demo.py` on PR #48 (same commits as PR #39), not
   a file in this tree. Gazebo Harmonic, PX4 SITL, and ROS 2 Jazzy are
   on that PR and on open PR #18. There is no
   `docs/simulation/px4-sitl.md` on `main`.
3. **On-board capture and detection** — CM5 + stereo camera + Coral:
   synchronized frames, detection/tracking, RTAB-Map trajectory, GPS,
   store-and-forward to the base station.
4. **Base station** — the station server is on `main`. ROS 2 ingest,
   fusion, and map nodes are still names in the architecture doc.
   Muse Spark labelling on `main` is the scene-note client only.
5. **Later, if at all** — multi-drone map merging, then navigation.

## Open decisions

- Stereo camera: ELP dual-lens module is the candidate; commit only
  after the bench tests in [docs/camera-elp-stereo.md](docs/camera-elp-stereo.md)
  pass (baseline measurement, L/R sync, depth range, CM5 sustained load).
- On-device benchmark of the Edge TPU profiles. The code default is
  `efficientdet-lite0`; `ssd-mobilenet-v2` and `ssdlite-mobiledet` are
  the other profiles. The tracker in tree is the greedy IoU tracker.
- SAM 3.1 on the RTX 5060 Ti: measured VRAM, resolution, keyframe rate,
  and whether video-mode tracking or per-image segmentation is used.
- Labelling cost and latency per session. Model ids and endpoints are
  in [HACKATHON.md](HACKATHON.md).
- Link between drone and base station (Wi-Fi / LTE / other), and
  therefore how much is processed live vs. store-and-forward.
- Simulation machine: no Gazebo world on `main`. The local path is on
  PR #18 and PR #48.
- Exact GPS checkpoint format and frame↔GPS time synchronization.
- Map export format (GeoJSON-flavoured JSON is the current leaning,
  unconfirmed).

## From the original conversation

- Exposing the board and GPU APIs for external access — Mantas.
- Passive survey pipeline (stereo → cloud → SAM → semantic map) as above;
  navigation, V-JEPA, and drone orchestration are parked, not cancelled.
