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
- **SAM 3.1 on a Mac** (`--sam-device mps`): on Apple silicon, SAM
  3.1's image model runs per frame on the GPU (Metal), about 2.4 s a
  frame, with ids kept by box overlap. Play at SAM's pace (`--fps 0.35`)
  so regions stay within the sidecar's 10 s buffer.
- **Persistent surfaces** (`surmap.survey.surfaces`): mask points that
  land on earlier points continue the same surface across SAM window
  resets. A surface that drifts 40 cm or more is drawn red as a moving
  object.
- **Run history**: every frame, detection, and cloud update is stored
  in `demo-history.db`; the timeline rewinds through it.
- **Replay run** (speed 1×, 4× or max; `GET /stream?replay=<run_id>&speed=N`):
  every run keeps a journal of its events and RTAB-Map's dense buffer
  (the disparity computed for each SAM frame, with its pose), so a
  persisted run plays back without starting RTAB-Map or SAM. Frames,
  map and masks come from the journal; regions and surfaces are
  recomputed by the current code (`surmap.demo.replay.JournalPlayer`
  takes the `SurfaceMap` under tuning). Each replay is saved as a new
  run naming its source, for comparison.

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
