# Disaster mission demo

One command runs a civilian search-and-rescue survey and opens the
viewer. SurMap stays passive: the command does not enable PX4 motors
(PX4's armed state) and does not upload the lawnmower. Gazebo overview:
[simulation/gazebo-disaster-world.md](simulation/gazebo-disaster-world.md).
A live Gazebo flight is not part of CI.

```bash
uv run python scripts/mission_demo.py
```

That is offline mode, the default. It does not need Gazebo, a GPU, or
an API key. Add `--live` only on a machine that should call the hosted
models.

The viewer listens on [http://127.0.0.1:8770/](http://127.0.0.1:8770/).
Ctrl+C stops it. `--no-viewer` writes the report and exits. This is
not the dataset demo: that page is
[http://127.0.0.1:8765/](http://127.0.0.1:8765/) from `scripts/demo.py`
(EuRoC, KITTI, NTU VIRAL). `--live` uses the same
`StreamingRtabmapBackend` that page uses.

Outputs land in `mission-demo-out/` (gitignored):

| File | What it is |
|---|---|
| `euroc/mav0/` | EuRoC export of the recorded SITL fixture |
| `semantic_map_snapshot.json` | `surmap.semantic_map_snapshot.v1` |
| `impact.json` | Found, total, mean position error, time to first detection |

## What the command chains

1. **Session.** Offline exports `tests/fixtures/sitl_capture_tiny/` to EuRoC. That fixture is not a flight of the disaster block. Perception uses a second recorded fixture: one camera point per person in the ground-truth JSON, posed at the offset in `src/surmap/mission/fixtures/offline_perception.json`. If `gz` is missing, that is expected for this mode.
2. **SAM 3.1 masks.** Offline uses a recorded polygon. Live uses Meta when `SURMAP_LIVE_META=1`, otherwise Modal when `SURMAP_LIVE_MODAL=1`.
3. **Mask to cloud.** `points_in_mask` projects the points. Nothing is written back into RTAB-Map.
4. **Labels and a scene note.** Offline labels each object `survivor` and writes a fixture scene note. With `SURMAP_LIVE_META=1`, live labels use Muse Spark `muse-spark-1.3` on the Meta Model API and the scene note uses the same API. Baseten labels are used only when that Meta flag is unset and `SURMAP_LIVE_BASETEN=1`.
5. **Snapshot.** `build_snapshot` anchors the tracks to the disaster-block GPS origin.
6. **Viewer.** `http://127.0.0.1:8770/` shows the snapshot. The impact line is `GET /impact`.
7. **Question.** The report answers "Where are the survivors?" Highlighted points are the matched landmarks. `POST /ask` on the viewer does the same. If `surmap.mapqa` is installed and `SURMAP_LIVE_META=1`, that POST delegates to `surmap.mapqa.answer`.
8. **Impact.** Found, total, mean position error in metres, and time to first detection. **Total is the length of the `people` array** in `docs/simulation/gz/worlds/disaster_block_ground_truth.json`. A match is a survivor-labelled point within 3 m. Offline `impact.json` sets `"basis": "fixtures"` and says the figures were computed from fixtures.

Keys stay in the environment (`MODEL_API_KEY`, `BASETEN_API_KEY`, `MODAL_SAM_URL`). The report does not contain them.

## WSL — offline

From the SurMap repo in the WSL distro, Windows browser on the same URL:

```bash
cd ~/surmap
uv sync --group dev
uv run python scripts/mission_demo.py
```

Open http://127.0.0.1:8770/ . The amber line is the fixture impact.
The landmark list is the people the fixture placed. Ask "Where are the
survivors?" if the line is not enough; the points highlight.

No Gazebo window in this mode. The EuRoC tree under
`mission-demo-out/euroc/` is the tiny recorded capture, exported by
the same function a real dump uses.

## WSL — live

Live still does not enable PX4 motors. Fly or replay on the WSL host
that has PX4, then point the command at the capture.

This is the live command. It calls Meta SAM 3.1 (`sam-3.1`), Muse Spark
labels (`muse-spark-1.3`), and the Muse Spark scene note. It does not
need Baseten.

```bash
# terminal 1 — simulator, GUI on WSLg
echo "$DISPLAY"          # :0 on Windows 11 WSLg
./scripts/launch_disaster_sitl.sh

# terminal 2 — after the cameras are bridged
source /opt/ros/jazzy/setup.bash
uv run python scripts/ros2/dump_sitl_capture.py --output ~/sitl-runs/disaster-01
# see docs/simulation/px4-sitl.md for the topic flags

# terminal 3
export SURMAP_LIVE_META=1
export MODEL_API_KEY='your-key'          # single quotes
uv run python scripts/mission_demo.py --live --capture ~/sitl-runs/disaster-01
```

`--live` without `--capture` stops. If `gz` is on `PATH` it tells you
to launch SITL yourself and pass the capture. If `gz` is missing it
tells you the same, because a live score needs that recording.

`SURMAP_LIVE_META=1` selects Meta SAM, Muse Spark labels, and the scene
note. Baseten (`SURMAP_LIVE_BASETEN=1`, `BASETEN_API_KEY`) and Modal SAM
(`SURMAP_LIVE_MODAL=1`, `MODAL_SAM_URL`) are used only when
`SURMAP_LIVE_META` is unset. A flag that is unset is not called.
`SURMAP_SAM_PROMPT` overrides the SAM noun; the default is `person`.

The 3D cloud in live mode is the same streaming backend as
`scripts/demo.py` (`--rtabmap-mode live`). `open_live_map()` builds
`StreamingRtabmapBackend` from the capture calibration, feeds every
stereo pair, and reads `map_snapshot()` after `flush()`.
`live_map_backend()` is `live-rtabmap`. An empty snapshot says
positions were not estimated. Offline keeps using the fixture cloud
and says so (`"basis": "fixtures"`). Live model calls stay behind
`SURMAP_LIVE_META`, `SURMAP_LIVE_BASETEN`, and `SURMAP_LIVE_MODAL`.

The survey flies at 5 m above home (see
[simulation/gazebo-disaster-world.md](simulation/gazebo-disaster-world.md)).
The live map asks the sidecar for a depth cap of 30 m
(`--max-depth-m`, or `SURMAP_MAX_DEPTH_M`). Points closer than 2 px of
disparity are kept and farther noisy points are dropped
(`--min-disparity-px`, or `SURMAP_MIN_DISPARITY_PX`). On this rig
(`fx` ≈ 381, baseline 0.07 m) 2 px is about 13 m, which still covers
the street in the lower part of a forward frame at 5 m. An explicit
flag wins over the environment variable. `0` for the disparity floor
turns that filter off and leaves the depth cap in charge.

## Tests

```bash
uv run pytest -q tests/test_mission_metrics.py tests/test_mission_demo.py
```

Those tests use fakes. They do not open a socket except to
`127.0.0.1` for the viewer. They do not read API keys into the report.
They do not launch Gazebo. The WSL steps above are the operator run.
