# SurMap — Meta Global AI Developer Hackathon

All code in this repository was written during the hackathon, which
started 26 Oct 2026. The first commit on `main` is
[`2afea352`](https://github.com/uppin/surmap/commit/2afea3524c91485e4db019dcc3281fdfb3fefbbf)
(26 Oct 2026, 21:06 +0200, "Add passive-survey design, Python
scaffold, and CI"). There is no earlier history.

The survey is for civilian disaster response. A passively carried
payload maps an affected area so a search-and-rescue team can see
landmarks, debris, and vehicles. SurMap does not fly the aircraft
and does not task it.

Submissions are due 4 Nov 2026. What is implemented versus planned is
below. Design of the pipeline remains
[docs/architecture.md](docs/architecture.md); model policy is in
[README.md](README.md).

## Credits

Three credit sources are core infrastructure for the hackathon build.
Meta Model API and Baseten are not called from `src/` yet. Modal is:
`surmap.survey.modal_sam` posts the SAM 3.1 ONNX tensor to
`MODAL_SAM_URL`. CI does not install Modal and does not hold a token.

| Source | Job | Id, as documented 28 Oct 2026 | Status |
|---|---|---|---|
| [Meta Model API](https://dev.meta.ai/docs/models) | Scene note over the mapped area. SAM 3.1 boxes and masks | Hosted Muse Spark: `muse-spark-1.3` (latest id on the models page). SAM: `sam-3.1` via `POST /v1/responses`. Base URL in the docs' examples: `https://api.meta.ai/v1` | Planned |
| [Baseten Model APIs](https://docs.baseten.co/inference/model-apis/overview) | Per-object semantic labels from Muse Spark Open (image crop, optional responder voice note) | Hackathon id `meta-models/muse-spark-open-1026`. Public catalog slug `meta-models/muse-spark-open`. Base URL `https://inference.baseten.co/v1` | Planned |
| Modal | inference on the exported ONNX model runs on a Modal GPU | App `surmap-sam` in `src/surmap/survey/modal_sam_app.py`. Client `MODAL_SAM_URL`. Default GPU `T4` (`SURMAP_MODAL_GPU`) | In tree. Live call needs deploy, the Volume, and `MODAL_SAM_URL`. CI has no account |

Muse Spark Open is not on Meta Model API. Meta's models page says to
run those weights yourself or call a hosted provider; Baseten is that
provider here. Hosted Muse Spark (`muse-spark-1.3`) is the Model API
model for the scene note. Muse Wonder is not used.

Baseten, same check: Muse Spark Open always reasons (`reasoning_effort`
`none` and `minimal` still run at `low`; default `xhigh`); it accepts
image, video, and audio and returns text; it does not enforce
structured outputs. Confirm `meta-models/muse-spark-open-1026` with
`GET /v1/models` before a live call — the public catalog lists the
undated slug.

The geometric pipeline (stereo, Coral detection, RTAB-Map, the demo)
does not use these credits.

## Modal GPU — deploy and stop

Run these in WSL from the repo root. Authenticate once; the token is
written to `~/.modal.toml` and must not be committed. Choose workspace
`ginas-bb` when the CLI asks:

```bash
uv run --with modal modal token new
```

The ONNX export is license-gated. Put it on Volume `surmap-sam3`.
The container reads `/models/sam3.1.onnx`.

```bash
uv run --with modal modal volume create surmap-sam3
uv run --with modal modal volume put surmap-sam3 ./sam3.1.onnx /sam3.1.onnx
```

Deploy. GPU defaults to `T4`. Set `SURMAP_MODAL_GPU=L4` (or another
type) to change it. `SURMAP_MODAL_TIMEOUT` defaults to 300 seconds.
`SURMAP_MODAL_SCALEDOWN_WINDOW` defaults to 60 seconds. The function
sets `max_containers=1` and does not set `min_containers`, so the
container scales to zero after that idle window.

```bash
uv run --with modal modal deploy src/surmap/survey/modal_sam_app.py
```

Copy the printed web URL, then on the station:

```bash
export MODAL_SAM_URL='https://<workspace>--surmap-sam-segment.modal.run'
python -m surmap.survey.station_main --detector sam3-modal
```

`MODAL_SAM_INPUT` (default `256x256`) must match the export.
`MODAL_SAM_MODEL` overrides the usage label (default `surmap-sam/<gpu>`).

Stop the app when the survey is finished:

```bash
uv run --with modal modal app stop surmap-sam
```

Spend for workspace `ginas-bb` is the Usage page in the Modal
dashboard, <https://modal.com/settings/usage>, and the `surmap-sam`
app page from `uv run --with modal modal app list`.

## Third-party building blocks

Pieces this tree builds on and did not create. "Adds" is only what the
code does on top of them.

| Piece | What it is | How this repo uses it | What this repo adds |
|---|---|---|---|
| RTAB-Map | Visual SLAM (IntRoLab). Trajectory and a static-scene cloud | `surmap.slam.sidecar.SidecarRtabmapBackend` stages streamed pairs as a EuRoC directory and, at `flush()`, runs the pinned image `introlab3it/rtabmap` (`rtabmap-euroc_dataset`, then `rtabmap-export`). Poses and the PLY cloud are parsed back. `RtabmapBackend` is the native-binding seam; CI does not install the bindings. Selected with `--slam-backend sidecar` | Container teardown limited to containers that instance started; a shared container (`SURMAP_RTABMAP_SHARED_CONTAINER`) is borrowed and never removed. Object points are not written back into RTAB-Map. No flight commands |
| EuRoC MAV | ASL stereo/IMU session layout (`mav0/cam0`, `cam1`, `imu0`) and the V1_01_easy sequence | Demo registry entry `euroc-v1-01-easy` (`surmap.demo.datasets`). The sidecar writes that layout from a live stream. `scripts/fetch_rtabmap_fixture.py` cuts a subset for the RTAB-Map e2e | Playback pacing, depth overlay, and end-of-stream RTAB-Map drawing in `surmap.demo.server`. The dataset itself is unchanged |
| ETH3D `cables_2` | Schöps et al., CVPR 2017, high-resolution stereo SLAM sequence | Ten downscaled pairs in `tests/fixtures/eth3d_cables2`, used by `tests/test_survey_stereo.py` and `tests/test_survey_cm5_stereo_e2e.py`. Research-use terms: see the fixture README | The fixture is test data only. It is not the flight-session format |
| KITTI tracking, VisDrone, Purdue UAV | Public video/stereo sequences with boxes | Parsers in `surmap.moving.snippets` (`kitti-tracking-stereo`, `visdrone-mot-traffic`, `purdue-uav-swarm`). KITTI e2e is opt-in (`tests/test_moving_kitti_e2e.py`, `SURMAP_REQUIRE_KITTI_E2E=1`) | Parsers and the moving-area pipeline that consumes them. Not the survey session format |
| SAM 3.1 | Meta's promptable segmenter | `surmap.survey.sam3`: an ONNX Runtime session whose contract is `image` float32 NCHW in, `masks` and `scores` out. CUDA provider when asked, CPU in CI. CI runs `tests/fixtures/sam3_fake` (a tiny ONNX stand-in, not Meta's weights). `station_main --detector sam3` selects it. `station_main --detector sam3-modal` posts that same contract to a Modal GPU (`surmap.survey.modal_sam`); the checkpoint is a Modal Volume, not a file in git. `StationSamService.StreamAnalysis` streams the boxes | `SamDetector` port, `AnalysisGate` (every frame, or drop when busy), mask outline polygon on the wire. The real checkpoint is not downloaded. Masks are not projected onto the cloud. Meta's API is not called |
| EfficientDet-Lite0, SSD MobileNet V2, SSDLite MobileDet | Coral/Google INT8 detection networks, COCO labels | `surmap.detection`: LiteRT (`ai-edge-litert`) runs the CPU twin; the Edge TPU file is for the board. Default profile `efficientdet-lite0`. Artifacts pinned by `scripts/fetch_coral_model.py`. A Meta-on-TPU spike was rejected in `docs/coral-edge-tpu-model-spike.md` | Greedy IoU tracker (`surmap.detection.tracker`, no external tracker library). Detections on their own `StreamDetections` stream. `CoralObjectPointSource` keeps stereo points whose projection falls inside a tracked box |
| ConnectRPC (connect-python 0.12.1) | HTTP/Protobuf RPC, including bidi streams | Dependency in `pyproject.toml`. `surmap.rpc` is that serving kit adapted to this repo (`docs/connectrpc.md`): bricks, Hypercorn and in-memory hosts, WebSocket multiplexing, `google.api.http` transcoding | Survey contracts in `proto/surmap/survey/v1/survey.proto`: `Cm5SurveyService` and `StationSamService`. Health and Prometheus text routes |

Stereo depth is code in this repo (`surmap.survey.stereo`): principal-point
alignment, SAD block match, parabolic subpixel disparity, back-projection.
It uses NumPy and Pillow. OpenCV is not a dependency. The IoU tracker
above is also code in this repo.

## Not in this tree

Checked `pyproject.toml` and `src/`. No import and no call for:

- Meta Model API or Baseten (see Credits — still planned).
- A committed Modal token or a `modal` dependency. The deploy module
  loads `modal` with `importlib` only when the package is installed.
  CI does not install it.
- ROS 2, Gazebo, or PX4. The passive WSL path (Gazebo Harmonic + PX4
  SITL + ROS 2 Jazzy, capture directory to a EuRoC session) is open
  [PR #18](https://github.com/uppin/surmap/pull/18), not merged.
  `docs/simulation/px4-sitl.md` does not exist on `main`.
- A GPS fix on the survey wire. `GpsCheckpoint` in `surmap.types` has
  no caller. PR #18 writes a GPS CSV beside the exported session and
  leaves GPS-on-the-wire deferred.
- A semantic-map type, a landmark store, or a map export file.
