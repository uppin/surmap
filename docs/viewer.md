# Survey viewer

A local, time-synced view of one survey replay: the camera with
detection and landmark overlays, a height-coloured 3D map, a short
telemetry strip, and the landmark list. One clock drives every pane.

No GPU and no API key. The default EuRoC replay uses the same download
and cache as `scripts/demo.py`. The preview source needs neither.

## WSL2

From the repo root, inside the WSL distro:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
cd /path/to/surmap
uv sync --group dev
```

Preview (no download, bundled snapshot):

```bash
uv run python scripts/viewer.py --source preview
```

EuRoC V1_01 (first run downloads about 1.1 GB into
`~/.cache/surmap/demo-datasets`, then reuses it):

```bash
uv run python scripts/viewer.py --frames 200
```

Open **http://localhost:8770/** in the Windows browser. The server
binds `127.0.0.1`. WSL2 localhost forwarding still reaches that
address from Windows. Pass `--host 0.0.0.0` to listen on every
interface. Ctrl+C stops the server.

## What is on screen

- **Camera** (largest pane). The frame, with a box and a floating label
  such as `PERSON 8.0 m`. Box colour is the track's motion: green
  `static`, yellow `moving`, blue `unknown`. A mask cloud projects to
  a tinted outline when `mask_points` is present. Coral boxes appear
  only when `--coral-model-dir` is set; they are not a second landmark
  list.
- **Map**. Dark view, scene points coloured by height (blue/purple at
  the bottom of the cloud through cyan, green, and yellow to red).
  The drone is a white marker. Its path is a pink line with a drop
  line to the ground grid. Each landmark is a coloured marker (red
  person, amber vehicle, blue structure). `mask_points` are a cloud in
  that colour. A moving track draws its observation trail up to the
  current time. Chase follows the drone; Orbit is a free camera.
  `cut above N m` hides scene points above that height.
- **Telemetry**. Height and scene points for this replay, with one
  white cursor at the current time.
- **Landmarks**. Label, motion, latitude/longitude, and description.
  The v1 file has no confidence field, so none is shown.
- **Ask the map**. `POST /ask` with `{"question": "...", "snapshot_path": null}`.
  The response is `{"answer", "landmark_ids", "highlight_points"}`.
  Cited tracks are marked in the list and in the 3D view. With
  `SURMAP_LIVE_META=1`, a question is delegated to
  `surmap.mapqa.answer(question, snapshot_path=...)` when that package
  imports. Otherwise the answer is a local label match. This tree does
  not call a model.

HUD badges are survey state: `SURVEY`, `MAPPING` once scene points
exist, `LANDMARKS N`, and `GPS FIX`, `POSE`, or `NO POSE`. EuRoC ground
truth is `POSE`. A SITL capture with `gps.csv` is `GPS FIX`.

## Sources

| `--source` | Input | Pose |
|---|---|---|
| `euroc` (default) | `surmap.demo.datasets` cache | `mav0/state_groundtruth_estimate0/data.csv`, extracted from the cached zip when the demo extract did not keep it |
| `preview` | bundled `surmap.semantic_map_snapshot.v1` fixture | scripted east/north/up path over that fixture |
| `sitl` | PR #18 capture directory (`calibration.json`, `frames.jsonl`, `images/`, optional `gps.csv`) | GPS converted with the snapshot's 111320 m/degree scale |

```bash
uv run python scripts/viewer.py --source preview --fps 12 --loop
uv run python scripts/viewer.py --frames 200 --fps 8
uv run python scripts/viewer.py --no-stereo --frames 400
uv run python scripts/viewer.py --source sitl --capture ~/sitl-runs/hover-01 \
    --snapshot ~/sitl-runs/hover-01/map.json
```

`--snapshot` is a `surmap.semantic_map_snapshot.v1` file. Preview loads
a bundled one when the flag is omitted. EuRoC and SITL show an empty
landmark list until a snapshot is passed. The reader does not import
the unmerged writer (PR #35). The fixture file is
`src/surmap/viewer/fixtures/semantic_map_snapshot.json`. Tests read
that copy.

Tracks whose observation times overlap the replay are placed on that
clock. Otherwise replay progress scrubs each track along its own
observations, so a snapshot from another clock still moves.

## Ask hook

```http
POST /ask
Content-Type: application/json

{"question": "where is the person", "snapshot_path": "/absolute/path/map.json"}
```

`snapshot_path` is optional. Omitted, the question uses the snapshot
already loaded for the replay, and that replay's path is what
`surmap.mapqa.answer` receives when the live flag is on. The cited
`landmark_ids` and `highlight_points` (`[{x, y, z}, ...]`) are what
the page highlights.
