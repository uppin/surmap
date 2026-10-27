# SurMap — passive drone surveyor

[![CI](https://github.com/uppin/surmap/actions/workflows/ci.yml/badge.svg)](https://github.com/uppin/surmap/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue)](tests/)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue)](pyproject.toml)

A drone-mounted survey system that builds a semantic map of an area from
stereo video and GPS while the drone is flown by someone (or something) else.

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

RTAB-Map note: RTAB-Map has no official PyPI package, and no host —
local or CI — may install it. The real backend is
`surmap.slam.SidecarRtabmapBackend`: it stages streamed stereo pairs
as a EuRoC-style dataset and runs the pinned RTAB-Map Docker image
(`rtabmap-euroc_dataset` + `rtabmap-export`) over it, returning
RTAB-Map's optimized poses and assembled cloud at end of stream. Run
`uv run python scripts/fetch_rtabmap_fixture.py` to pull the pinned
image and cut the EuRoC V1_01 test subset; the CM5 server selects the
sidecar with `--slam-backend sidecar --calibration-dir <dataset>`.
`surmap.slam.RtabmapBackend` remains for a host that does provide
native bindings, and tests/simulation otherwise use
`surmap.slam.InMemorySlamBackend`.

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
- Segment objects with Meta's SAM on the base station and project those
  regions onto the point cloud.
- Assign semantic labels to mapped objects with an LLM via a Models API.
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
| 2 | ROS2 base station with NVIDIA RTX 5060 Ti | Ground processing: SAM segmentation, point-cloud/segment fusion, semantic map building, LLM labelling client |
| 3 | Simulation machine (hardware and software not yet chosen) | Synthetic stereo/GPS data and replay of recorded sessions, so the pipeline can be developed and tested without flying |

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
| Segmentation + video tracking | Base station, RTX 5060 Ti | **SAM 3.1** (Meta, released 2026-03-27 as a drop-in update to SAM 3, 2025-11-19) | Yes |
| Semantic labelling | Via Models API | Newest Meta Llama model offered by the chosen API at integration time; exact model ID recorded per run | Yes, preferred |
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
  LLM via Models API assigns semantic labels
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
   and machine 2 without flying.
3. **On-board capture and detection** — CM5 + stereo camera + Coral:
   synchronized frames, detection/tracking, RTAB-Map trajectory, GPS,
   store-and-forward to the base station.
4. **Base station** — ROS2 nodes for ingest, SAM 3.1, fusion, map
   building, and LLM labelling; one drone's footage at a time.
5. **Later, if at all** — multi-drone map merging, then navigation.

## Open decisions

- Stereo camera: ELP dual-lens module is the candidate; commit only
  after the bench tests in [docs/camera-elp-stereo.md](docs/camera-elp-stereo.md)
  pass (baseline measurement, L/R sync, depth range, CM5 sustained load).
- Which Edge TPU detector (SSD MobileNet V2 vs. EfficientDet-Lite) and
  which box tracker — to be settled by on-device benchmarks.
- SAM 3.1 on the RTX 5060 Ti: measured VRAM, resolution, keyframe rate,
  and whether video-mode tracking or per-image segmentation is used.
- Which Models API and which exact Meta Llama model ID it exposes;
  labelling cost/latency budget per session.
- Link between drone and base station (Wi-Fi / LTE / other), and
  therefore how much is processed live vs. store-and-forward.
- Simulation machine: hardware, and simulator/replay software
  (candidates not yet evaluated).
- Exact GPS checkpoint format and frame↔GPS time synchronization.
- Map export format (GeoJSON-flavoured JSON is the current leaning,
  unconfirmed).

## From the original conversation

- Exposing the board and GPU APIs for external access — Mantas.
- Passive survey pipeline (stereo → cloud → SAM → semantic map) as above;
  navigation, V-JEPA, and drone orchestration are parked, not cancelled.
