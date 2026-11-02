# SurMap — passive drone surveyor

[![CI](https://github.com/uppin/surmap/actions/workflows/ci.yml/badge.svg)](https://github.com/uppin/surmap/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue)](tests/)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue)](pyproject.toml)

SurMap is a civilian disaster-response mapping payload. Carried over an
affected area, it builds a GPS-anchored 3D semantic map from stereo
video so a search-and-rescue (SAR) team can find landmarks, debris,
vehicles, and people who need help.

**Scope and safety.** SurMap is a passive observer. A separate pilot or
autopilot flies the aircraft. SurMap sends no flight commands, does no
path planning, and has no interface to a flight controller. It does no
facial recognition and no personal identification: a map label such as
`survivor` is a semantic object class, not an identity.

Hackathon provenance, model usage, and third-party credits:
[HACKATHON.md](HACKATHON.md). System design:
[docs/architecture.md](docs/architecture.md).

## 60-second quickstart (mission demo)

Offline is the default. It exports the recorded SITL capture in
`tests/fixtures/sitl_capture_tiny/`, projects recorded masks onto the
disaster-block ground truth, writes a semantic-map snapshot and an
impact report, and opens the survey viewer. It downloads nothing,
starts no Docker container, and needs no API key.

```bash
uv sync
uv run python scripts/mission_demo.py
# viewer: http://127.0.0.1:8770/
```

Outputs land in `mission-demo-out/`: the EuRoC export,
`semantic_map_snapshot.json`, and `impact.json`. An offline report says
`"basis": "fixtures"`. When a recorded live run is committed under
`demo/recordings/mission/`, offline mode replays those real model
responses instead and labels each one with its model and recording
time ([demo/recordings/README.md](demo/recordings/README.md)).

### Live run

A live run feeds a SITL capture through the Dockerized
`StreamingRtabmapBackend` (image pinned to `linux/amd64`), segments
each keyframe with SAM 3.1, labels every object, and writes a scene
note. The only required flag is Meta:

```bash
export SURMAP_LIVE_META=1
export MODEL_API_KEY='your-meta-key'      # single quotes: the key contains '|'
uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01
```

With `SURMAP_LIVE_META=1`, Muse Spark chooses what to look for in each
keyframe (structured output: up to `SURMAP_SAM_MAX_CONCEPTS` short noun
phrases, default 4, `person` always first, refreshed every
`SURMAP_CONCEPT_EVERY` posed frames, default 10) and SAM 3.1 on the
Meta Model API segments each one. `SURMAP_SAM_PROMPT=<noun>` pins a
single concept instead. Muse Spark also labels the objects and writes
the scene note.

Optional providers:

| Flags | Effect |
|---|---|
| `SURMAP_LIVE_BASETEN=1`, `BASETEN_API_KEY` | Per-object labels move to open-weight Muse Spark Open on Baseten, also when Meta is on (`reasoning_effort` `low`, fields from a `record_label` tool call) |
| `SURMAP_LIVE_MODAL=1`, `MODAL_SAM_URL`, `--sam-route modal` | SAM 3.1 runs on the project's Modal GPU app instead of the Meta API |
| `--record <dir>` | Writes every model request (auth dropped, images hashed) and response to `<dir>` for offline replay |

Keys are read only by the clients and never written to reports or
recordings. Runbook: [docs/mission-demo.md](docs/mission-demo.md).
Simulation: [docs/simulation/gazebo-disaster-world.md](docs/simulation/gazebo-disaster-world.md)
and [docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md).

### Ask the map

`surmap.mapqa` answers questions over a snapshot with Muse Wonder
(`muse-wonder-1.0`) and transcribes spoken questions with Muse Voice
Transcribe (`muse-voice-transcribe-1.0`):

```bash
uv run python -m surmap.mapqa ask --snapshot mission-demo-out/semantic_map_snapshot.json \
    --question "Where are the blocked roads?"
uv run python -m surmap.mapqa report --snapshot mission-demo-out/semantic_map_snapshot.json
uv run python -m surmap.mapqa ask-voice --snapshot mission-demo-out/semantic_map_snapshot.json \
    --audio query.wav
```

The mission viewer's Ask box (`POST /ask`) uses the same client when
`SURMAP_LIVE_META=1`; otherwise it matches labels locally. Details:
[docs/mapqa.md](docs/mapqa.md).

## Architecture
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
The one-command disaster survey (`scripts/mission_demo.py`) is a
separate command. It does not use this page. Offline, it writes a
fixture impact report (`"basis": "fixtures"`) and opens the survey
viewer on port 8770. `--live` feeds a SITL capture through the same
`StreamingRtabmapBackend` this demo uses. Runbook:
[docs/mission-demo.md](docs/mission-demo.md). Gazebo scene:
[docs/simulation/gazebo-disaster-world.md](docs/simulation/gazebo-disaster-world.md).

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
on the frame preview for each frame. SAM looks for one concept per
run: each scene has its own default (`box` on EuRoC, `car` on KITTI,
`person` on NTU VIRAL), the SAM pane's **SAM prompt** box restarts the
run with another (`/?dataset=…&prompt=…`), and `--sam-label` replaces
every scene's default. An `.onnx` export's concept is fixed at export,
so the box is read-only there. `--sam-model` can name another HF id, a
local `.pt`, or an `.onnx` export instead. SAM propagates in
16-frame windows so a long video fits a 16 GB card (ids restart per
window). The PyTorch stack is an optional install in `.venv` (see
`scripts/demo.py --help`). On an Apple-silicon Mac, `--sam-device mps`
runs SAM 3.1's image model on the GPU (Metal) per frame, about 2.4 s
a frame, with ids kept by box overlap; play at SAM's pace
(`--fps 0.35`) so regions stay within the sidecar's 10 s buffer. With the live map, each SAM result's masks
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
were at each frame. Every run also keeps a *journal*: its events in
order, and RTAB-Map's dense buffer (the disparity the sidecar computed
for each SAM frame, with the pose it used). **Replay run** (speed 1×,
4× or max; `GET /stream?replay=<run_id>&speed=N`) plays a persisted run
back from that journal without starting RTAB-Map or SAM. Frames, map
and SAM masks come from the journal, while regions and surfaces are
recomputed by the current code (`surmap.demo.replay.JournalPlayer`
takes the `SurfaceMap` under tuning). Each replay is saved as a new
run naming its source, for comparison. `--sam-fake` does the same without a GPU or model —
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
ON-BOARD (Raspberry Pi CM5 + Coral Edge TPU)
  stereo frames (L/R) + GPS checkpoints + timestamps
        ├──► RTAB-Map (passive): trajectory + static-scene points
        └──► Coral detector + IoU tracker (left channel): boxes, track ids
             ─► stereo points inside each box, static vs moving,
                layered over the static scene (never fused into it)
        │
        ▼  ConnectRPC streams / recorded session (no flight commands)
BASE STATION (NVIDIA RTX 5060 Ti)
  stereo ─► depth ─► point cloud (pixel ↔ 3D point ↔ frame)
  Muse Spark picks concepts ─► SAM 3.1 masks (Meta API, local GPU, or Modal)
        │   masks ─► 3D points (points_in_mask, StreamRegionPoints)
        ▼
  objects and persistent surfaces anchored to GPS (SemanticMapSnapshot)
        │
        ▼
  Muse Spark / Muse Spark Open labels + Muse Spark scene note
        │
        ▼
  semantic map ─► viewer, Ask the map (Muse Wonder, voice)
```

### Model policy: Meta first

Every learned stage uses a Meta model, except on-board detection,
where no Meta model compiles to the Edge TPU
([docs/coral-edge-tpu-model-spike.md](docs/coral-edge-tpu-model-spike.md)).

| Stage | Host | Model id in code | Meta? |
|---|---|---|---|
| Segmentation | Meta Model API / station GPU (PyTorch or ONNX) / Modal GPU | `sam-3.1` / `facebook/sam3.1` | Yes |
| Concepts to segment | Meta Model API (structured output) | `muse-spark-1.3` | Yes |
| Scene note | Meta Model API | `muse-spark-1.3` | Yes |
| Per-object labels | Meta Model API, or Baseten (open weights) | `muse-spark-1.3` / `meta-models/muse-spark-open-1026` | Yes |
| Map Q&A and report | Meta Model API | `muse-wonder-1.0` | Yes |
| Voice questions | Meta Model API | `muse-voice-transcribe-1.0` | Yes |
| On-board detection | Pi CM5 + Coral Edge TPU | EfficientDet-Lite0 (default), SSD MobileNet V2, SSDLite MobileDet (INT8) + greedy IoU tracker | No — no Meta Edge TPU detector |
| Visual SLAM | Pi CM5 / Docker sidecar | RTAB-Map | No — geometric, not learned |

Muse Wonder Full is never used; the clients refuse it.

## Dev console (`scripts/demo.py`)

An engineering console that plays a public stereo dataset in real time
and builds the map live:

```bash
uv run python scripts/demo.py
# open http://127.0.0.1:8765/
```

- **Live RTAB-Map** (`StreamingRtabmapBackend`): stereo pairs go over
  stdin to a `librtabmap` process in a pinned `linux/amd64` container,
  which streams odometry, keyframe points, and graph re-optimizations
  without stalling playback. `--no-rtabmap` runs without Docker.
- **SAM 3.1 video mode** (`--sam-device cuda:0`): `facebook/sam3.1`
  (gated; `HF_TOKEN` in `.env`) runs in 16-frame windows so long videos
  fit a 16 GB card. `--sam-fake` runs a stand-in without a GPU. Each
  scene has a default concept (`box`, `car`, `person`), changeable on
  the page or with `--sam-label`.
- **Persistent surfaces** (`surmap.survey.surfaces`): mask points that
  land on earlier points continue the same surface across SAM window
  resets. A surface that drifts 40 cm or more is drawn red as a moving
  object.
- **Run history**: every frame, detection, and cloud update is stored
  in `demo-history.db`; the timeline rewinds through it.

Datasets are fetched on first use, SHA-256 verified, and cached in
`~/.cache/surmap/demo-datasets` (`surmap.demo.datasets`, never
re-hosted):

| Scene | Zip | Licence |
|---|---|---|
| `euroc-v1-01-easy` (indoor MAV, 376×240 @ 20 Hz) | 1.15 GB | ETH ASL research dataset |
| `kitti-2011-09-26-drive-0009` (city drive, 620×188 @ 10 Hz) | 1.79 GB | CC BY-NC-SA 3.0 |
| `ntu-viral-sbs-01` (outdoor drone flight) | 3.78 GB | CC BY-NC-SA 4.0 |

Useful flags: `--dataset`, `--list-datasets`, `--frames N`,
`--start I`, `--fps F`, `--rtabmap-mode live|batch`, `--prepare-only`,
`--sam-model <id|path>`, `--cm5-host`, `--station-host`.

## Hardware and deployment

| Node | Hardware | Role |
|---|---|---|
| On-board payload | Raspberry Pi CM5 + Coral Edge TPU + stereo camera ([ELP dual-lens candidate](docs/camera-elp-stereo.md)) | Stereo capture, Coral detection (`StreamDetections`), object points (`100 + track_id`) over the static scene (`1`), ConnectRPC streaming (`surmap.survey.cm5_main`) |
| Base station | Workstation with NVIDIA RTX 5060 Ti | `surmap.survey.station_main --detector memory\|sam3\|sam3-modal\|sam31-torch`, mask projection, snapshots, Muse calls |
| Simulation host | Linux / WSL2 with Gazebo Harmonic, PX4 SITL, ROS 2 Jazzy | Fictional civilian earthquake-and-flood block, SITL capture export ([docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md)) |

```bash
uv run python scripts/fetch_coral_model.py
scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] --model efficientdet-lite0
scripts/deploy-station.sh <source-dir> <ssh-target>      # SAM 3.1 PyTorch on cuda:0
scripts/deploy-demo.sh <source-dir> <ssh-target>         # dev console against both
```

Details: [docs/deployment.md](docs/deployment.md).

## Benchmarks and evaluation

- `scripts/seg_bench.py`: offline scores for the SAM routes (Meta API,
  Modal, station ONNX, replay) on a recorded disaster-block flight —
  IoU, boundary F1, 3D survivor recall, cost
  ([docs/segmentation-benchmark.md](docs/segmentation-benchmark.md)).
- `scripts/eval_disaster_labelling.py`: per-class F1 of hosted Muse
  Spark (structured output) and open-weight Muse Spark Open on Baseten
  (tool call) on LADI v2 aerial disaster imagery (CC BY 4.0), downloaded
  on demand; no data is committed
  ([docs/disaster-labelling-eval.md](docs/disaster-labelling-eval.md)).
- `scripts/usage_report.py`: credit usage per provider, model, and day
  ([docs/credits-usage.md](docs/credits-usage.md)).

## Development and quality gates

```bash
uv sync --group dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy                 # strict, src and tests
uv run pytest -q
```

CI runs the same gates on Python 3.11 and 3.12 for every push to `main`
and every pull request. Model calls in tests use fake transports; live
tests are skipped unless their `SURMAP_LIVE_*` flag is set.

## Roadmap

Next hardware milestones:

- Bench validation of the ELP stereo module on the CM5: baseline,
  L/R sync, depth range, sustained thermal load.
- On-device latency of the Edge TPU profiles.
- Sustained SAM 3.1 throughput and VRAM on the RTX 5060 Ti.
- Link budget (Wi-Fi vs LTE store-and-forward) and a GeoJSON map
  export.
- GPS on the survey wire (today GPS comes from the capture's `gps.csv`).

Out of scope by design: navigation, path planning, flight-controller
interfaces, and drone tasking.
