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
uv run python scripts/demo.py            # downloads+caches EuRoC, serves the demo
# open http://127.0.0.1:8765/ in a browser
```

The demo plays a recorded dataset as real-time video with the stereo
reconstructor's scene points overlaid as depth-coloured detections,
then builds the final RTAB-Map map from the same frames and draws it
top-down. Datasets are registry entries in `surmap.demo.datasets`
(`--list-datasets`): the first run downloads and SHA-256-verifies
the zip into the cache (`~/.cache/surmap/demo-datasets`, override
`--cache-dir`/`$SURMAP_DEMO_CACHE_DIR`); later runs download nothing.
Useful flags: `--frames N`, `--start I`, `--fps F`, `--no-rtabmap`,
`--prepare-only`. Add a dataset by adding one registry entry.

RTAB-Map note: RTAB-Map has no official PyPI package, and no host —
local or CI — may install it. The real backend is
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
provisioning step. Nothing in this tree calls an API. Hackathon
inference for that checkpoint is planned as Meta Model API
`sam-3.1`, with Modal as the GPU when the station runs the export
itself ([HACKATHON.md](HACKATHON.md)).

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
| 2 | ROS2 base station with NVIDIA RTX 5060 Ti | Ground processing: SAM 3.1 segmentation (Meta Model API `sam-3.1`; Modal GPU for the in-tree ONNX export), point-cloud/segment fusion, semantic map building, Muse Spark labelling |
| 3 | Simulation machine. Local/WSL path, not yet on `main`: Ubuntu + Gazebo Harmonic + PX4 SITL + ROS 2 Jazzy ([PR #18](https://github.com/uppin/surmap/pull/18); runbook `docs/simulation/px4-sitl.md` once that merges). Other hardware still open | Synthetic stereo/GPS, exported as a EuRoC session the demo and RTAB-Map sidecar already consume, and replay of recorded sessions. Passive: the simulator flies; SurMap sends no flight commands |

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
| Segmentation + video tracking | Base station | **SAM 3.1** (Meta). In-tree adapter: ONNX Runtime (`surmap.survey.sam3`). Hackathon calls: Meta Model API id `sam-3.1`; Modal GPU when the station runs the ONNX export | Yes |
| Semantic labelling and scene reasoning | Base station, via an API | **Muse Spark** (Meta). Per-object labels: Baseten Model APIs, `https://inference.baseten.co/v1`, hackathon id `meta-models/muse-spark-open-1026`. Scene note: Meta Model API, hosted Muse Spark (models page lists `muse-spark-1.3` as the latest id) | Yes |
| Pose / mapping | Pi CM5 | RTAB-Map | No — not a learned model; no Meta equivalent |
| Video representations | — | V-JEPA | Deferred |

SAM 3.1 notes: it detects, segments, and tracks objects in images and
video from text, exemplar, and visual prompts (Promptable Concept
Segmentation), and 3.1 adds object multiplexing for faster video
processing. On Meta Model API the model id is `sam-3.1` (Responses
API, `POST /v1/responses`): a text prompt plus an image or video
returns boxes and masks
([Models](https://dev.meta.ai/docs/models)). Meta's published
throughput figures are for an H100, so throughput and VRAM on the
RTX 5060 Ti — or on a Modal GPU — must be measured, not assumed.
Sources: [Meta SAM 3 announcement](https://ai.meta.com/blog/segment-anything-model-3/),
[SAM 3 paper page](https://ai.meta.com/research/publications/sam-3-segment-anything-with-concepts/).

Muse notes, checked 28 Oct 2026. Two different models, two APIs:

- **Muse Spark Open** is the open-weight release. Meta's models page
  says it is not served on Model API; call it from a hosted provider
  or run the weights yourself
  ([Models](https://dev.meta.ai/docs/models)). On Baseten the
  OpenAI-compatible base URL is `https://inference.baseten.co/v1`.
  The public catalog slug is `meta-models/muse-spark-open`. The
  hackathon credit path uses `meta-models/muse-spark-open-1026`;
  that dated slug is not in the public catalog, so confirm it with
  `GET /v1/models` before a live call. Baseten's docs: reasoning is
  always on (`reasoning_effort` `none` and `minimal` still run at
  `low`; the default is `xhigh`); image, video, and audio input;
  text output; no structured outputs (a `json_object` request is
  accepted and not enforced). Sources:
  [Model APIs](https://docs.baseten.co/inference/model-apis/overview),
  [Reasoning](https://docs.baseten.co/inference/model-apis/reasoning),
  [Vision](https://docs.baseten.co/inference/model-apis/vision),
  [Audio](https://docs.baseten.co/inference/model-apis/audio).
- **Muse Spark** (hosted) is the Model API model for the scene note.
  The models page lists `muse-spark-1.3` as the latest id, at
  `https://api.meta.ai/v1`, with text, image, video, audio, and PDF
  input and text output. Record the exact id on each run. Muse
  Wonder is not used.

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
        (Meta Model API `sam-3.1`, or the ONNX adapter on a Modal GPU)
        │   masks projected onto the point cloud, registered by RTAB-Map pose
        ▼
  objects / landmarks in 3D, anchored to GPS checkpoints
        │
        ▼
  Muse Spark Open assigns per-object labels
        (Baseten `meta-models/muse-spark-open-1026`)
  hosted Muse Spark writes a scene note for the area
        (Meta Model API, `muse-spark-1.3` unless a newer id is current)
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
   ([PR #18](https://github.com/uppin/surmap/pull/18), not merged).
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
- SAM 3.1 serving: Meta Model API `sam-3.1` versus the ONNX export on
  a Modal GPU (the in-tree adapter). Measured VRAM, resolution,
  keyframe rate, and video-mode versus per-image segmentation.
- Muse calls: confirm Baseten accepts `meta-models/muse-spark-open-1026`
  (the public catalog lists `meta-models/muse-spark-open`); labelling
  cost and latency per session. Baseten does not constrain that model
  to a JSON schema, so any label record is validated after the call.
  The scene note uses Meta Model API `muse-spark-1.3` unless a newer
  hosted id is current at integration. Muse Wonder is out of scope.
- Link between drone and base station (Wi-Fi / LTE / other), and
  therefore how much is processed live vs. store-and-forward.
- Simulation machine: dedicated hardware is still open. The local/WSL
  software path is Gazebo Harmonic + PX4 SITL + ROS 2 Jazzy, passive
  capture only, exported as a EuRoC session. The runbook
  `docs/simulation/px4-sitl.md` arrives with
  [PR #18](https://github.com/uppin/surmap/pull/18), which is not merged.
- Exact GPS checkpoint format and frame↔GPS time synchronization.
- Map export format (GeoJSON-flavoured JSON is the current leaning,
  unconfirmed).

## From the original conversation

- Exposing the board and GPU APIs for external access — Mantas.
- Passive survey pipeline (stereo → cloud → SAM → semantic map) as above;
  navigation, V-JEPA, and drone orchestration are parked, not cancelled.
