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

## Model policy

Meta Model API credits cover the models on
[the models page](https://dev.meta.ai/platform/models) except Muse
Wonder Full. Muse Spark is the default: hosted `muse-spark-1.3`, and
Muse Spark Open on Baseten. Muse Wonder (`muse-wonder-1.0`) is in
scope, planned for map Q&A ("ask the map"), and optional for the
scene note. SAM 3.1 and Muse Voice Transcribe
(`muse-voice-transcribe-1.0`) are in scope. Muse Wonder Full is not
used.

## Credits

Three credit sources are core infrastructure for the hackathon build.
None of them is called from `src/` today. Rows marked planned have no
client, no request, and no test.

| Source | Job | Id, as documented 28 Oct 2026 | Status |
|---|---|---|---|
| [Meta Model API](https://dev.meta.ai/docs/models) | Scene note over the mapped area. SAM 3.1 boxes and masks | Hosted Muse Spark: `muse-spark-1.3` (latest id on the models page). SAM: `sam-3.1` via `POST /v1/responses`. Base URL in the docs' examples: `https://api.meta.ai/v1` | Planned |
| [Baseten Model APIs](https://docs.baseten.co/inference/model-apis/overview) | Per-object semantic labels from Muse Spark Open (image crop, optional responder voice note) | Hackathon id `meta-models/muse-spark-open-1026`. Public catalog slug `meta-models/muse-spark-open`. Base URL `https://inference.baseten.co/v1` | Planned |
| Modal | GPU for station-side SAM 3.1 inference behind the in-tree ONNX adapter | No Modal app in this repo | Planned |

Muse Spark Open is not on Meta Model API. Meta's models page says to
run those weights yourself or call a hosted provider; Baseten is that
provider here. Hosted Muse Spark (`muse-spark-1.3`) is the Model API
model for the scene note. Muse Wonder Full is not used.

Baseten, checked 28 Oct 2026
([Model APIs](https://docs.baseten.co/inference/model-apis/overview),
[Reasoning](https://docs.baseten.co/inference/model-apis/reasoning),
[Vision](https://docs.baseten.co/inference/model-apis/vision),
[Audio](https://docs.baseten.co/inference/model-apis/audio)):
Muse Spark Open always reasons (`reasoning_effort` `none` and
`minimal` still run at `low`; default `xhigh`); it accepts image,
video, and audio and returns text; it does not enforce structured
outputs (a `json_object` request is accepted and not constrained).
Confirm `meta-models/muse-spark-open-1026` with `GET /v1/models`
before a live call — the public catalog lists the undated slug.
Any label record is validated after the call.

The geometric pipeline (stereo, Coral detection, RTAB-Map, the demo)
does not use these credits.

## Third-party building blocks

Pieces this tree builds on and did not create. "Adds" is only what the
code does on top of them.

| Piece | What it is | How this repo uses it | What this repo adds |
|---|---|---|---|
| RTAB-Map | Visual SLAM (IntRoLab). Trajectory and a static-scene cloud | `surmap.slam.sidecar.SidecarRtabmapBackend` stages streamed pairs as a EuRoC directory and, at `flush()`, runs the pinned image `introlab3it/rtabmap` (`rtabmap-euroc_dataset`, then `rtabmap-export`). Poses and the PLY cloud are parsed back. `RtabmapBackend` is the native-binding seam; CI does not install the bindings. Selected with `--slam-backend sidecar` | Container teardown limited to containers that instance started; a shared container (`SURMAP_RTABMAP_SHARED_CONTAINER`) is borrowed and never removed. Object points are not written back into RTAB-Map. No flight commands |
| EuRoC MAV | ASL stereo/IMU session layout (`mav0/cam0`, `cam1`, `imu0`) and the V1_01_easy sequence | Demo registry entry `euroc-v1-01-easy` (`surmap.demo.datasets`). The sidecar writes that layout from a live stream. `scripts/fetch_rtabmap_fixture.py` cuts a subset for the RTAB-Map e2e | Playback pacing, depth overlay, and end-of-stream RTAB-Map drawing in `surmap.demo.server`. The dataset itself is unchanged |
| ETH3D `cables_2` | Schöps et al., CVPR 2017, high-resolution stereo SLAM sequence | Ten downscaled pairs in `tests/fixtures/eth3d_cables2`, used by `tests/test_survey_stereo.py` and `tests/test_survey_cm5_stereo_e2e.py`. Research-use terms: see the fixture README | The fixture is test data only. It is not the flight-session format |
| KITTI tracking, VisDrone, Purdue UAV | Public video/stereo sequences with boxes | Parsers in `surmap.moving.snippets` (`kitti-tracking-stereo`, `visdrone-mot-traffic`, `purdue-uav-swarm`). KITTI e2e is opt-in (`tests/test_moving_kitti_e2e.py`, `SURMAP_REQUIRE_KITTI_E2E=1`) | Parsers and the moving-area pipeline that consumes them. Not the survey session format |
| SAM 3.1 | Meta's promptable segmenter | `surmap.survey.sam3`: an ONNX Runtime session whose contract is `image` float32 NCHW in, `masks` and `scores` out. CUDA provider when asked, CPU in CI. CI runs `tests/fixtures/sam3_fake` (a tiny ONNX stand-in, not Meta's weights). `station_main --detector sam3` selects it. `StationSamService.StreamAnalysis` streams the boxes | `SamDetector` port, `AnalysisGate` (every frame, or drop when busy), mask outline polygon on the wire. The real checkpoint is not downloaded. Masks are not projected onto the cloud. Meta's API is not called |
| EfficientDet-Lite0, SSD MobileNet V2, SSDLite MobileDet | Coral/Google INT8 detection networks, COCO labels | `surmap.detection`: LiteRT (`ai-edge-litert`) runs the CPU twin; the Edge TPU file is for the board. Default profile `efficientdet-lite0`. Artifacts pinned by `scripts/fetch_coral_model.py`. A Meta-on-TPU spike was rejected in `docs/coral-edge-tpu-model-spike.md` | Greedy IoU tracker (`surmap.detection.tracker`, no external tracker library). Detections on their own `StreamDetections` stream. `CoralObjectPointSource` keeps stereo points whose projection falls inside a tracked box |
| ConnectRPC (connect-python 0.12.1) | HTTP/Protobuf RPC, including bidi streams | Dependency in `pyproject.toml`. `surmap.rpc` is that serving kit adapted to this repo (`docs/connectrpc.md`): bricks, Hypercorn and in-memory hosts, WebSocket multiplexing, `google.api.http` transcoding | Survey contracts in `proto/surmap/survey/v1/survey.proto`: `Cm5SurveyService` and `StationSamService`. Health and Prometheus text routes |

Stereo depth is code in this repo (`surmap.survey.stereo`): principal-point
alignment, SAD block match, parabolic subpixel disparity, back-projection.
It uses NumPy and Pillow. OpenCV is not a dependency. The IoU tracker
above is also code in this repo.

## Not in this tree

Checked `pyproject.toml` and `src/`. No import and no call for:

- Meta Model API, Baseten, or Modal (see Credits — planned).
- ROS 2, Gazebo, or PX4. The passive WSL path (Gazebo Harmonic + PX4
  SITL + ROS 2 Jazzy, capture directory to a EuRoC session) is open
  [PR #18](https://github.com/uppin/surmap/pull/18), not merged.
  `docs/simulation/px4-sitl.md` does not exist on `main`.
- A GPS fix on the survey wire. `GpsCheckpoint` in `surmap.types` has
  no caller. PR #18 writes a GPS CSV beside the exported session and
  leaves GPS-on-the-wire deferred.
- A semantic-map type, a landmark store, or a map export file.
