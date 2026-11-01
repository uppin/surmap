# SurMap — Meta Global AI Developer Hackathon

Civilian disaster-response mapping. A passively carried payload maps
an affected area so a search-and-rescue team can see landmarks,
debris, and vehicles. A separate pilot or autopilot flies the drone.
SurMap never controls it, and it does not identify people: no face
recognition and no identity.

Submissions are due 4 Nov 2026. What is on `main`, and what is only on
open pull requests, is below. Design of the pipeline remains
[docs/architecture.md](docs/architecture.md); model policy is in
[README.md](README.md).

TODO(Ginas): track; team: …

## What was built during the event (26 Oct – 4 Nov 2026)

The first commit on `main` is
[`2afea352`](https://github.com/uppin/surmap/commit/2afea3524c91485e4db019dcc3281fdfb3fefbbf)
("Add passive-survey design, Python scaffold, and CI"). It was
authored 26 Oct 2026, 20:56:31 +0200. The committer date on the same
commit is 21:06:03 +0200. An earlier draft of this page cited only
the committer time. There is no parent commit.

Product code written in this repository after that commit, and on
`main` now, includes the survey protobuf contracts and ConnectRPC
servers, stereo reconstruction, the Coral detector and tracker, the
RTAB-Map sidecar and the streaming demo, the moving-object pipeline,
the SAM 3.1 ONNX adapter, and the Muse Spark scene-note client. The
packages are `surmap.survey`, `surmap.detection`, `surmap.slam`,
`surmap.demo`, `surmap.moving`, `surmap.labelling`, and
`surmap.geometry`. That is not a claim that every bullet in the
architecture doc is implemented. GPS on the survey wire, a
GPS-tied semantic map, and mask projection are not on `main`.

Open, not merged:

- [PR #48](https://github.com/uppin/surmap/pull/48)
  (`feat/segmentation-protocol-guidelines`) contains every commit on
  [PR #39](https://github.com/uppin/surmap/pull/39)
  (`feat/mission-demo`) plus
  `docs/segmentation-protocol-guidelines.md` and
  `docs/segmentation-protocol-example.json`. #48 is the branch likely
  to land. The hackathon demo script `scripts/mission_demo.py` is on
  that branch, not on `main`.
- [PR #41](https://github.com/uppin/surmap/pull/41)
  (`cursor/ask-the-map-2463`) is Ask the map (`surmap.mapqa`).

The guidelines file on #48 says it is guidance for one frame exchange,
not a schema, and that nothing in the tree validates those files.
`surmap.survey.mask_cloud.points_in_mask`, the projection function it
names, is on #48/#39 and is not on `main`.

## Brought in, not written for this event

These landed inside the same dates. They were imported, not written
as the survey product.

**ConnectRPC serving kit.** Commit
[`ccec0ab`](https://github.com/uppin/surmap/commit/ccec0ab8c8b8e182cbc304e626e667108993c92e)
(26 Oct 2026, 21:50:23 +0200, "rpc: import ConnectRPC client/server
support for Python") adds `src/surmap/rpc`,
`proto/surmap/transport`, and [docs/connectrpc.md](docs/connectrpc.md).
That doc says the tree was imported as a product-blind serving kit
and adapted to this repo. It is transport plumbing (HTTP, WebSocket
multiplexing, health and metrics). The survey contracts in
`proto/surmap/survey` were added later, in this repository.

**Developer prompts.** Commit
[`cb43a4f`](https://github.com/uppin/surmap/commit/cb43a4fc0705ad1ece26f4358f6205909a06258b)
(26 Oct 2026, 21:37:13 +0200, "agents: import genericized skills and
commands for Muse") adds `.agents/` and the `.Muse/` symlinks.
[.agents/README.md](.agents/README.md) says that tree was imported
from another project and genericized. Those files are assistant
prompts, not product code.

**Open-source building blocks.** The survey builds on the projects in
the table below (RTAB-Map, public datasets, Coral/Google detectors,
SAM 3.1, connect-python). This repository did not create them.

## Model policy

Meta Model API credits cover the models on
[the models page](https://dev.meta.ai/platform/models) except Muse
Wonder Full. The scene note on `main` calls hosted Muse Spark
(`muse-spark-1.3`). Muse Spark Open is not on that API; on #48/#39
its labels go to Baseten. Muse Wonder (`muse-wonder-1.0`) is the Ask
the map model on #41, not the scene-note default. SAM 3.1 and Muse
Voice Transcribe (`muse-voice-transcribe-1.0`) are in the tables
below. Muse Wonder Full is refused by the clients that check for it.

## Meta models in SurMap

"On demo path" means `scripts/mission_demo.py` (the hackathon demo,
on #48/#39, not on `main`) or `scripts/demo.py` (the EuRoC / KITTI /
NTU dev demo, on `main`). Offline mission playback does not call a
model. A live mission start currently refuses to run unless both
`SURMAP_LIVE_META=1` and `SURMAP_LIVE_BASETEN=1` are set. See
`build_live_services` in `src/surmap/mission/demo.py` on #48/#39.

| Model | Provider/path | Code | What it does | On demo path |
|---|---|---|---|---|
| Muse Spark `muse-spark-1.3` | Meta Model API, `POST https://api.meta.ai/v1/responses`, bearer `MODEL_API_KEY` | `src/surmap/labelling/meta_muse.py` (`MetaMuseSceneClient`) on `main` | One civilian scene note from a JPEG and the on-board label strings. Default model `muse-spark-1.3` (`SURMAP_META_MODEL` or the constructor may select another covered id). Refuses Muse Wonder Full and any `meta-models/` slug | Not called by `scripts/demo.py`. On the mission demo: live only. Offline writes a fixture note and does not construct this client. `SURMAP_LIVE_META=1` is required for a live start. On `main` that variable is only the opt-in for `tests/test_labelling_meta_muse.py`; the client does not read it |
| Muse Spark Open | Baseten, id `meta-models/muse-spark-open-1026`, `POST https://inference.baseten.co/v1/chat/completions`, bearer `BASETEN_API_KEY` | `src/surmap/labelling/baseten_muse.py` on #48/#39, not on `main` | Per-object plain-text label from an image crop. The map point is attached after the reply and is not sent | Live mission only, and required: startup raises unless `SURMAP_LIVE_BASETEN=1` and `BASETEN_API_KEY` is non-blank. Offline uses the fixture label `survivor` and does not call Baseten. Not on `scripts/demo.py` |
| Muse Spark Open on Modal | Model string `meta-models/Muse-Spark-Open-816B-A42B` (`MODAL_MUSE_MODEL` overrides). URL `MODAL_MUSE_URL`. Proxy token `MODAL_PROXY_TOKEN_ID` and `MODAL_PROXY_TOKEN_SECRET` | `src/surmap/labelling/modal_muse.py` and `scripts/check_modal_muse.py` on #48/#39, not on `main` | One chat completion against a Modal shared endpoint. The mission demo does not import it | CLI only (`scripts/check_modal_muse.py`) |
| SAM 3.1 | Meta Model API, default id `sam-3.1`, `POST https://api.meta.ai/v1/responses`, bearer `MODEL_API_KEY` | `src/surmap/survey/meta_sam.py` (`MetaSamDetector`) on #48/#39, not on `main` | Boxes and masks for one frame and a short text prompt. The module docstring says a live `sam-3.1` response was not captured, and the JSON envelope is assumed to match a text Responses call | Live mission: a successful start has `SURMAP_LIVE_META=1`, and that sets the SAM provider to `meta` (`sam = "meta" if meta else "modal"`). Offline uses a recorded polygon and does not call this client. Also `scripts/check_meta_sam.py`, which posts only when `SURMAP_LIVE_META=1` and `MODEL_API_KEY` are both set. Not on `scripts/demo.py` |
| SAM 3.1 on Modal GPU | App `surmap-sam`. Checkpoint named in the app as `facebook/sam3.1` (`sam3.1_multiplex.pt`). Client posts to `MODAL_SAM_URL`. The module's default GPU string is `L4` | `src/surmap/survey/modal_sam.py`, `src/surmap/survey/modal_sam_app.py`, `scripts/check_modal_sam.py` on #48/#39. Station flag `--detector sam3-modal` is on that branch, not on `main` | Remote GPU boxes, polygons, and scores | Not the SAM provider of a successful live mission: that start requires `SURMAP_LIVE_META=1`, which selects Meta SAM. If `SURMAP_LIVE_MODAL=1` is set as well, `MODAL_SAM_URL` must be non-blank or startup still raises. `scripts/check_modal_sam.py` is the CLI check. Not on `scripts/demo.py` |
| SAM 3.1 ONNX on the station | ONNX Runtime. Contract: input `image` float32 NCHW in 0..1; outputs `masks` and `scores` | `src/surmap/survey/sam3.py` on `main`. Selected with `python -m surmap.survey.station_main --detector sam3 --sam3-model <path>` | Same `Sam3Detector` for a real export or the test file. CUDA provider when asked and installed; CPU otherwise | Not on `scripts/demo.py` and not on the mission demo's perception path. The only ONNX file in the tree is `tests/fixtures/sam3_fake/fake_sam3.onnx` (a tiny stand-in from `scripts/make_fake_sam3_model.py`). No SAM 3.1 checkpoint export is committed |
| Muse Wonder Q&A | `muse-wonder-1.0` (`SURMAP_MAPQA_MODEL` overrides), `POST https://api.meta.ai/v1/responses`, bearer `MODEL_API_KEY`. Names containing `wonder-full` are refused | `src/surmap/mapqa/` on #41, not on `main` | Question, Markdown report, or local `POST /ask` over a semantic-map snapshot JSON. It reads the snapshot; it does not write one | CLI and that process's HTTP server: `python -m surmap.mapqa ask`, `report`, `serve`. The CLI calls the API whenever it runs. The live test is skipped unless `SURMAP_LIVE_META=1`. The mission viewer on #48/#39 looks up `surmap.mapqa.answer`. #41 does not export `answer` (`MapQa.ask` is the method). As the two branches stand, that lookup misses and `POST /ask` stays on the viewer's local label match |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0`, `POST https://api.meta.ai/v1/asr/transcribe`, field `audioEncoding` `WAV` | `VOICE_MODEL` in `src/surmap/mapqa/client.py` on #41. CLI `python -m surmap.mapqa ask-voice` | Transcribes one WAV clip, then asks the snapshot | CLI only. The mission demo does not call it. `docs/mapqa.md` on #41 says the clip must be RIFF/WAVE, mono, 16-bit PCM, 16 kHz or 24 kHz. The client posts the bytes as `audio/wav` and does not check that format |

### Design history

The on-board detector is Coral, not a Meta model. A Meta-on-Edge-TPU
spike was tried and rejected: no Meta checkpoint in that attempt fit
the Edge TPU as a detector. The note is
[docs/coral-edge-tpu-model-spike.md](docs/coral-edge-tpu-model-spike.md).
The default profile in code is `efficientdet-lite0`
(`surmap.detection.profiles`).

## Credits

On `main`, the only Meta client under `src/` is the scene note. The
rows below say where the other clients live. They are not described
as future work: either the code is on `main`, or it is on the named
open PR, or it is absent.

| Source | Job | Id, as documented 28 Oct 2026 | Status |
|---|---|---|---|
| [Meta Model API](https://dev.meta.ai/docs/models) | Scene note over one mapped JPEG. SAM 3.1 boxes and masks on #48/#39 | Hosted Muse Spark: `muse-spark-1.3` (default). `SURMAP_META_MODEL` or the constructor may select another covered id, including Muse Wonder (`muse-wonder-1.0`). Muse Wonder Full is refused. SAM: `sam-3.1` via `POST /v1/responses`. Base URL: `https://api.meta.ai/v1` | Scene note is on `main`: `MetaMuseSceneClient` (`surmap.labelling.meta_muse`) posts to `POST /v1/responses` with `Authorization: Bearer` from `MODEL_API_KEY`. Default model `muse-spark-1.3`. `reasoning.effort` defaults to `high` (`SURMAP_META_REASONING_EFFORT`: `low`, `medium`, or `high`). `max_output_tokens` defaults to 4096 (`SURMAP_META_MAX_OUTPUT_TOKENS`, at least 16). A constructor argument wins over the env vars. The JPEG is an `input_image` data URL. The note is `output_text` from `message` items only. The prompt is a civilian search-and-rescue description and asks for no flight advice. SAM 3.1 on this API is `MetaSamDetector` on #48/#39, not on `main` |
| [Baseten Model APIs](https://docs.baseten.co/inference/model-apis/overview) | Per-object label from one JPEG crop | Hackathon id in code: `meta-models/muse-spark-open-1026`. Base URL `https://inference.baseten.co/v1` | Client `BasetenMuseLabelClient.label(jpeg, coarse_label, xyz)` on #48/#39, not on `main`. The call sends the crop, not the map point, and it has no audio argument. The live mission requires `SURMAP_LIVE_BASETEN=1` |
| Modal | GPU for SAM 3.1, and a separate Muse Spark Open chat endpoint | SAM app name `surmap-sam`. Muse model string `meta-models/Muse-Spark-Open-816B-A42B` | Both are on #48/#39, not on `main`. The Muse endpoint is the check script only. A successful live mission uses Meta SAM, not Modal SAM |

Muse Spark Open is not on Meta Model API. Meta's models page says to
run those weights yourself or call a hosted provider; Baseten is the
provider the mission demo calls for labels. Hosted Muse Spark
(`muse-spark-1.3`) is the Model API model for the scene note. Muse
Wonder Full is not used.
`MetaMuseSceneClient` sends
`reasoning.effort` `high` unless `SURMAP_META_REASONING_EFFORT` or
the constructor sets `low` or `medium` (anything else is refused).
`max_output_tokens` is 4096 unless `SURMAP_META_MAX_OUTPUT_TOKENS`
or the constructor sets another integer of at least 16; the cap
counts visible output and reasoning. Optional `before_call` is
invoked with `"meta"` before the request and may raise to block it.
Optional `on_usage` is invoked after a response that includes
`usage`, with provider `"meta"`, the model id, `input_tokens`,
`output_tokens`, and `output_tokens_details.reasoning_tokens` (or
nothing for that last count when the detail is absent). Credits
cover the models on the Meta models page except Muse Wonder Full
(ids matching `wonder-full` or `wonder_full`). This client refuses
that id and the Baseten slug `meta-models/muse-spark-open-1026`.

Baseten, checked 28 Oct 2026
([Model APIs](https://docs.baseten.co/inference/model-apis/overview),
[Reasoning](https://docs.baseten.co/inference/model-apis/reasoning),
[Vision](https://docs.baseten.co/inference/model-apis/vision),
[Audio](https://docs.baseten.co/inference/model-apis/audio)):
Muse Spark Open always reasons (`reasoning_effort` `none` and
`minimal` still run at `low`; default `xhigh`); it accepts image,
video, and audio and returns text; it does not enforce structured
outputs (a `json_object` request is accepted and not constrained).
The client on #48/#39 sends `meta-models/muse-spark-open-1026`,
a JPEG crop, and no JSON-mode flag. It does not send audio. Any
label record is validated after the call.

The geometric pipeline on `main` (stereo, Coral detection, RTAB-Map,
`scripts/demo.py`) does not use these credits.

## Third-party building blocks

Pieces this tree builds on and did not create. "Adds" is only what the
code does on top of them.

| Piece | What it is | How this repo uses it | What this repo adds |
|---|---|---|---|
| RTAB-Map | Visual SLAM (IntRoLab). Trajectory and a static-scene cloud | `surmap.slam.sidecar.SidecarRtabmapBackend` stages streamed pairs as a EuRoC directory and, at `flush()`, runs the pinned image `introlab3it/rtabmap` (`rtabmap-euroc_dataset`, then `rtabmap-export`). Poses and the PLY cloud are parsed back. `RtabmapBackend` is the native-binding seam; CI does not install the bindings. Selected with `--slam-backend sidecar` | Container teardown limited to containers that instance started; a shared container (`SURMAP_RTABMAP_SHARED_CONTAINER`) is borrowed and never removed. Object points are not written back into RTAB-Map. No flight commands |
| EuRoC MAV | ASL stereo/IMU session layout (`mav0/cam0`, `cam1`, `imu0`) and the V1_01_easy sequence | Demo registry entry `euroc-v1-01-easy` (`surmap.demo.datasets`). The sidecar writes that layout from a live stream. `scripts/fetch_rtabmap_fixture.py` cuts a subset for the RTAB-Map e2e | Playback pacing, depth overlay, and end-of-stream RTAB-Map drawing in `surmap.demo.server`. The dataset itself is unchanged |
| ETH3D `cables_2` | Schöps et al., CVPR 2017, high-resolution stereo SLAM sequence | Ten downscaled pairs in `tests/fixtures/eth3d_cables2`, used by `tests/test_survey_stereo.py` and `tests/test_survey_cm5_stereo_e2e.py`. Research-use terms: see the fixture README | The fixture is test data only. It is not the flight-session format |
| KITTI tracking, VisDrone, Purdue moving-object clips | Public video/stereo sequences with boxes. The Purdue clips are many small fast aircraft, used as moving objects | Parsers in `surmap.moving.snippets` (`kitti-tracking-stereo`, `visdrone-mot-traffic`, `purdue-uav-swarm`). The last id is the code name of that clip set. KITTI e2e is opt-in (`tests/test_moving_kitti_e2e.py`, `SURMAP_REQUIRE_KITTI_E2E=1`) | Parsers and the moving-area pipeline that consumes them. Not the survey session format |
| SAM 3.1 | Meta's promptable segmenter | On `main`, `surmap.survey.sam3`: an ONNX Runtime session whose contract is `image` float32 NCHW in, `masks` and `scores` out. CUDA provider when asked, CPU in CI. CI runs `tests/fixtures/sam3_fake` (a tiny ONNX stand-in, not Meta's weights). `station_main --detector sam3` selects it. `StationSamService.StreamAnalysis` streams the boxes | `SamDetector` port, `AnalysisGate` (every frame, or drop when busy), mask outline polygon on the wire. On `main` the real checkpoint is not downloaded, masks are not projected onto the cloud, and SAM is not called over the API. Projection and the API/Modal clients are on #48/#39 |
| EfficientDet-Lite0, SSD MobileNet V2, SSDLite MobileDet | Coral/Google INT8 detection networks, COCO labels | `surmap.detection`: LiteRT (`ai-edge-litert`) runs the CPU twin; the Edge TPU file is for the board. Default profile `efficientdet-lite0`. Artifacts pinned by `scripts/fetch_coral_model.py`. A Meta-on-TPU spike was rejected; see the design-history note above | Greedy IoU tracker (`surmap.detection.tracker`, no external tracker library). Detections on their own `StreamDetections` stream. `CoralObjectPointSource` keeps stereo points whose projection falls inside a tracked box |
| ConnectRPC (connect-python 0.12.1) | HTTP/Protobuf RPC, including bidi streams | Dependency in `pyproject.toml`. `surmap.rpc` is the imported serving kit (`docs/connectrpc.md`): bricks, Hypercorn and in-memory hosts, WebSocket multiplexing, `google.api.http` transcoding | Survey contracts in `proto/surmap/survey/v1/survey.proto`: `Cm5SurveyService` and `StationSamService`. Health and Prometheus text routes |

Stereo depth is code in this repo (`surmap.survey.stereo`): principal-point
alignment, SAD block match, parabolic subpixel disparity, back-projection.
It uses NumPy and Pillow. OpenCV is not a dependency. The IoU tracker
above is also code in this repo.

## Not on main

Checked on `main`. These are absent here even when an open PR has them.

- ROS 2, Gazebo, or PX4 Python code. [PR #18](https://github.com/uppin/surmap/pull/18)
  is still open (Gazebo/PX4 SITL capture exported to a EuRoC session).
  #48/#39 add the fictional civilian earthquake-and-flood block and
  `docs/simulation/px4-sitl.md`. That path is not in this tree, so
  this page does not link to the file.
- A GPS field on `proto/surmap/survey`. `GpsCheckpoint` in
  `surmap.types` has no caller on `main`. #48/#39 construct
  `GpsCheckpoint` values for the mission snapshot. #18 writes a GPS
  CSV beside an exported session. GPS-on-the-survey-wire is still not
  in the proto.
- A semantic-map type or snapshot writer. #48/#39 add
  `surmap.map.snapshot.SemanticMapSnapshot`. #41 reads a snapshot
  file and does not write one.
- Real SAM 3.1 weights. The committed ONNX file is the fake fixture.
