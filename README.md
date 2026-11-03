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
vehicles, and people who need help. Meta models do the understanding:
Muse Wonder decides what to look for and describes the scene, SAM 3.1
segments it, and the team can ask the finished map questions.

**Scope and safety.** SurMap is a passive observer. A separate pilot or
autopilot flies the aircraft. SurMap sends no flight commands, does no
path planning, and has no interface to a flight controller. It does no
facial recognition and no personal identification: a map label such as
`survivor` is a semantic object class, not an identity.

## What it does

- **Capture**: stereo frames, GPS, and timestamps from the payload or a recorded PX4 SITL flight.
- **Map**: RTAB-Map tracks the camera passively; stereo depth turns pixels into 3D points.
- **Segment**: Muse Wonder picks what to look for per keyframe (`person` first); SAM 3.1 masks it.
- **Anchor**: masks become 3D objects and persistent surfaces in a GPS-anchored snapshot.
- **Understand**: Muse Wonder or Muse Spark Open labels each object; Muse Wonder writes the scene note.
- **Ask**: the viewer answers typed or spoken questions over the map.

## Meta models

| Model | Hosted on | What it does |
|---|---|---|
| Muse Wonder `muse-wonder-1.0` | Meta Model API | SAM concepts per keyframe (structured output), per-object labels, scene note, Ask the map and situation report, LADI v2 labelling |
| Muse Spark Open `meta-models/muse-spark-open-1026` | Baseten | Open-weight per-object labels (`record_label` tool call), LADI v2 labelling |
| SAM 3.1 `sam-3.1` | Meta Model API | Masks for each keyframe concept in a live mission |
| SAM 3.1 `facebook/sam3.1` | Self-deployed Modal GPU app (`surmap-sam`), or the station GPU (PyTorch) | Remote GPU masks; continuous video segmentation in the dev console |
| Muse Voice Transcribe `muse-voice-transcribe-1.0` | Meta Model API | Spoken questions to text for Ask the map |

Every Meta Model API text call defaults to Muse Wonder; Muse Wonder Full
is refused. The only non-Meta learned stage is on-board detection: no
Meta model compiles to the Coral Edge TPU
([spike](docs/coral-edge-tpu-model-spike.md)). Endpoints and code
paths: [HACKATHON.md](HACKATHON.md).

## Quickstart

### Offline mission demo (60 seconds, no keys)

```bash
uv sync
uv run python scripts/mission_demo.py
# viewer: http://127.0.0.1:8770/
```

It replays the recorded SITL capture in `tests/fixtures/sitl_capture_tiny/`
and writes `semantic_map_snapshot.json` and `impact.json` to
`mission-demo-out/`, with no download, Docker, or API key. A recorded
live run under `demo/recordings/mission/` is replayed with its real
model responses instead ([demo/recordings/README.md](demo/recordings/README.md)).

### Live mission

A live run streams a SITL capture through Dockerized RTAB-Map, SAM 3.1,
and the Muse clients. Only the Meta flag is required:

```bash
export SURMAP_LIVE_META=1
export MODEL_API_KEY='your-meta-key'      # single quotes: the key contains '|'
uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01
```

| Flags | Effect |
|---|---|
| `SURMAP_LIVE_BASETEN=1`, `BASETEN_API_KEY` | Per-object labels move to Muse Spark Open on Baseten, also when Meta is on |
| `SURMAP_LIVE_MODAL=1`, `MODAL_SAM_URL`, `--sam-route modal` | SAM 3.1 runs on the Modal GPU app instead of the Meta API |
| `SURMAP_SAM_MAX_CONCEPTS` (default 4), `SURMAP_CONCEPT_EVERY` (default 10) | Concepts per keyframe, and how many posed frames between concept refreshes |
| `SURMAP_SAM_PROMPT=<noun>` | Pins one SAM concept instead of Muse Wonder's list |
| `--record <dir>` | Writes every model request (auth dropped, images hashed) and response for offline replay |

Keys are read only by the clients and never written to reports or
recordings. Runbook, WSL notes, and a fully local Ollama path:
[docs/mission-demo.md](docs/mission-demo.md). Simulation:
[docs/simulation/px4-sitl.md](docs/simulation/px4-sitl.md).

### Ask the map

```bash
uv run python -m surmap.mapqa ask --snapshot mission-demo-out/semantic_map_snapshot.json \
    --question "Where are the blocked roads?"
```

`report` prints a Markdown situation report and `ask-voice --audio q.wav`
takes a spoken question. The mission viewer's Ask box uses the same
client when `SURMAP_LIVE_META=1`; otherwise it matches labels locally
([docs/mapqa.md](docs/mapqa.md)).

### Dev console

`uv run python scripts/demo.py` (then http://127.0.0.1:8765/) plays a
public stereo dataset (EuRoC, KITTI, or NTU VIRAL) and builds the map
live with RTAB-Map and, with `--sam-device cuda:0` or `mps`, SAM 3.1.
It shows SAM objects as persistent 3D surfaces with an object feed,
toggles RTAB-Map's tracked points and its dense depth for each SAM frame
on the video, rewinds and replays every recorded run, rebuilds a run's
RTAB-Map without rerunning SAM, and exports or imports runs as
`.surmaprun` files. Full feature list and flags:
[docs/dev-console.md](docs/dev-console.md).

## Architecture

```text
ON-BOARD (Raspberry Pi CM5 + Coral Edge TPU)
  stereo + GPS + timestamps ─► RTAB-Map (passive) + Coral detector/tracker
        │  ConnectRPC streams / recorded session (no flight commands)
        ▼
BASE STATION (NVIDIA RTX 5060 Ti)
  stereo depth ─► point cloud
  Muse Wonder concepts ─► SAM 3.1 masks ─► 3D objects and surfaces
  ─► GPS-anchored semantic-map snapshot
  ─► Muse Wonder / Muse Spark Open labels + scene note
  ─► viewer and Ask the map
```

Design and scope boundary: [docs/architecture.md](docs/architecture.md);
snapshot format: [docs/semantic-map-snapshot.md](docs/semantic-map-snapshot.md).

## Evaluation

**LADI v2 disaster labelling.** `scripts/eval_disaster_labelling.py`
scores both Muse label clients on twelve multi-label classes of
[LADI v2](https://huggingface.co/datasets/MITLL/LADI-v2-dataset) aerial
disaster imagery (CC BY 4.0). Test split, 300 images, reasoning effort
`high`, 0 failed calls:

| Provider | Model | Micro F1 | Macro F1 |
|---|---|---|---|
| Meta Model API | Muse Wonder `muse-wonder-1.0` | 0.900 | 0.677 |
| Baseten | Muse Spark Open `meta-models/muse-spark-open-1026` | 0.889 | 0.654 |

Both models over-predict debris, bridges, and flooding: recall is high,
but precision on those classes is under 0.5. To reproduce (images are
downloaded on demand and cached outside the repo):

```bash
SURMAP_EVAL_MAX_IMAGES=300 SURMAP_LIVE_META=1 uv run python scripts/eval_disaster_labelling.py \
    --provider meta --reasoning-effort high --limit 300 --out ~/surmap-eval/wonder-high-300.json
```

For Muse Spark Open, use `--provider baseten` with `SURMAP_LIVE_BASETEN=1`.
Details: [docs/disaster-labelling-eval.md](docs/disaster-labelling-eval.md).

Also: `scripts/seg_bench.py` scores the SAM routes (Meta API, Modal,
station ONNX, replay) on a recorded disaster-block flight by IoU,
boundary F1, 3D survivor recall, and cost
([docs/segmentation-benchmark.md](docs/segmentation-benchmark.md)), and
`scripts/usage_report.py` prints credit usage per provider, model, and
day ([docs/credits-usage.md](docs/credits-usage.md)).

## Datasets

Nothing is committed or re-hosted; every dataset is downloaded on
demand and cached outside the repo. `scripts/download_disaster_data.py`
fetches the Boreal Forest Fire UAV smoke dataset (CC BY 4.0) and NOAA's
January 2025 Eaton and Palisades fire imagery (CC0-1.0), with subsets,
limits, and dry runs ([docs/disaster-datasets.md](docs/disaster-datasets.md)).
LADI v2 is fetched by the eval script; the dev-console scenes are listed
in [docs/dev-console.md](docs/dev-console.md).

## Survey agent

A chat agent that runs demos, SAM and object tools for you, served on
`127.0.0.1:8780`:

```bash
uv run python -m surmap.agent --sam-fake --model ollama:llama3.2
```

Flags, routes and the event stream: [docs/agent.md](docs/agent.md)
§ *Running the agent*.

## Hardware and deployment

| Node | Hardware | Role |
|---|---|---|
| On-board payload | Raspberry Pi CM5 + Coral Edge TPU + stereo camera ([ELP candidate](docs/camera-elp-stereo.md)) | Stereo capture, Coral detection and tracking, ConnectRPC streaming (`surmap.survey.cm5_main`) |
| Base station | Workstation with NVIDIA RTX 5060 Ti | `surmap.survey.station_main --detector memory\|sam3\|sam3-modal\|sam31-torch`, mask projection, snapshots, Muse calls |
| Simulation host | Linux / WSL2 with Gazebo Harmonic, PX4 SITL, ROS 2 Jazzy | Fictional civilian earthquake-and-flood block, SITL capture export |

```bash
uv run python scripts/fetch_coral_model.py
scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] --model efficientdet-lite0
scripts/deploy-station.sh <source-dir> <ssh-target>      # SAM 3.1 PyTorch on cuda:0
scripts/deploy-demo.sh <source-dir> <ssh-target>         # dev console against both
```

Details: [docs/deployment.md](docs/deployment.md) and
[docs/modal.md](docs/modal.md).

## Development

```bash
uv sync --group dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy                 # strict, src and tests
uv run pytest -q
```

CI runs these gates on Python 3.11 and 3.12 for every push to `main` and
every pull request. Model calls in tests use fake transports; live tests
are skipped unless their `SURMAP_LIVE_*` flag is set.

The agent chat web front end (Vite, React, shadcn/ui) lives in
[web/agent-chat/](web/agent-chat/README.md).

## Roadmap

- Bench-validate the ELP stereo module on the CM5 (baseline, L/R sync,
  depth range, thermal load) and measure Edge TPU latency on-device.
- Sustained SAM 3.1 throughput and VRAM on the RTX 5060 Ti.
- GPS on the survey wire (today it comes from the capture's `gps.csv`),
  a link budget (Wi-Fi vs LTE store-and-forward), and GeoJSON export.

Out of scope by design: navigation, path planning, flight-controller
interfaces, and drone tasking.

## Credits

SurMap builds on RTAB-Map, PX4, Gazebo, ROS 2, ConnectRPC, Coral
detectors, and open datasets. Provenance, licences, and third-party
credits: [HACKATHON.md](HACKATHON.md).
