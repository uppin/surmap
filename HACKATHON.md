# SurMap — Meta Global AI Developer Hackathon

Civilian disaster-response mapping. A passively carried payload maps an
affected area so a search-and-rescue team can see landmarks, debris,
vehicles, and people who need help. A separate pilot or autopilot flies
the drone. SurMap never controls it, and it does not identify people:
no face recognition and no identity.

- **Track:** Push the Frontier
- **Team:** Mantas ([@uppin](https://github.com/uppin)) and Ginas
  Baladinskas ([@JazzGinas](https://github.com/JazzGinas))
- **Event:** started 26 Oct 2026; submissions due 4 Nov 2026

This page is the provenance and audit trail: what was written during
the event, what was imported, which Meta models the code calls, and
which third-party projects it builds on. Product documentation is
[README.md](README.md); pipeline design is
[docs/architecture.md](docs/architecture.md).

## Timeline

The first commit on `main` is
[`2afea352`](https://github.com/uppin/surmap/commit/2afea3524c91485e4db019dcc3281fdfb3fefbbf)
("Add passive-survey design, Python scaffold, and CI"), authored
26 Oct 2026 20:56:31 +0200 (committer date 21:06:03 +0200). It has no
parent commit. Everything below was merged into `main` after it.

| Date (2026) | Merged into `main` | Packages |
|---|---|---|
| 26 Oct | ConnectRPC serving kit (#4, imported — see below), contributor guide (#5) | `surmap.rpc`, `surmap.transport` |
| 27 Oct | Survey proto contracts and BIDI servers, CM5 stereo reconstruction (#13), RTAB-Map sidecar (#14), server deployment (#12), Coral detection and tracking, station SAM 3.1 via ONNX Runtime (#16), subpixel disparity (#25), moving-object pipeline (#17, #19, #21–#24), CI fixtures (#26, #27) | `surmap.survey`, `surmap.detection`, `surmap.slam`, `surmap.moving`, `surmap.geometry` |
| 30 Oct | Model docs (#28), live RTAB-Map streaming backend (#38), Muse Spark scene note (#29), KITTI and NTU VIRAL demo scenes and map rendering (#42–#46), Ask the map with Muse Wonder and voice (#41), provenance docs (#50) | `surmap.demo`, `surmap.labelling`, `surmap.mapqa` |
| 31 Oct | Dev console with persisted runs and 3D cloud (#53), SAM 3.1 video segmentation on GPU (#54), `StreamRegionPoints` (#55), persistent SAM surfaces (#57), per-scene SAM prompt (#58), fixes (#56, #59) | `surmap.demo`, `surmap.survey` |
| 1 Nov | One-command disaster mission demo (#39, includes the PX4 SITL / Gazebo work from #18): mask-to-cloud projection, GPS-anchored semantic-map snapshot, mission viewer, Meta SAM 3.1, Muse Spark labels, Baseten and Modal clients, fictional civilian earthquake-and-flood world | `surmap.mission`, `surmap.map`, `surmap.viewer`, `surmap.simulation`, `surmap.usage` |
| 1 Nov | Field deployment: CM5 + station SAM 3.1 (PyTorch) + remote demo page (#60) | `surmap.survey.sam3_torch`, deploy scripts |
| 2 Nov | Offline segmentation benchmark (#51) | `surmap.segbench` |

Not yet built: GPS on the survey wire (GPS reaches the snapshot from the
capture's `gps.csv`), and a committed SAM 3.1 ONNX export (CI uses a
tiny stand-in, `tests/fixtures/sam3_fake/fake_sam3.onnx`).

## Brought in, not written for this event

**ConnectRPC serving kit.** Commit
[`ccec0ab`](https://github.com/uppin/surmap/commit/ccec0ab8c8b8e182cbc304e626e667108993c92e)
(26 Oct 2026 21:50:23 +0200, "rpc: import ConnectRPC client/server
support for Python", merged in #4) adds `src/surmap/rpc`,
`proto/surmap/transport`, and [docs/connectrpc.md](docs/connectrpc.md).
It is product-blind transport plumbing (HTTP, WebSocket multiplexing,
health, metrics), imported and adapted. The survey contracts in
`proto/surmap/survey` were written later, in this repository.

**Developer prompts.** Commit
[`cb43a4f`](https://github.com/uppin/surmap/commit/cb43a4fc0705ad1ece26f4358f6205909a06258b)
(26 Oct 2026 21:37:13 +0200, "agents: import genericized skills and
commands for Muse") adds `.agents/` and the `.Muse/` symlinks, imported
from another project and genericized
([.agents/README.md](.agents/README.md)). They are coding-assistant
prompts, not product code.

## Meta models in SurMap

Meta Model API credits cover every model on
[the models page](https://dev.meta.ai/platform/models) except Muse
Wonder Full, which the clients refuse. Live calls happen only when the
matching `SURMAP_LIVE_*` flag is set; the default offline mission and
CI use fixtures and fake transports.

| Model | Provider and endpoint | Code | Role | Demo path |
|---|---|---|---|---|
| SAM 3.1 `sam-3.1` | Meta Model API, `POST https://api.meta.ai/v1/responses`, `Authorization: Bearer $MODEL_API_KEY` | `surmap.survey.meta_sam.MetaSamDetector` | Boxes and masks for one frame and one noun-phrase concept | `mission_demo.py --live` with `SURMAP_LIVE_META=1`; `seg_bench.py run --route meta`; `scripts/check_meta_sam.py` |
| Muse Spark `muse-spark-1.3` | Meta Model API, `POST /v1/responses` | `surmap.labelling.meta_muse` (`MetaMuseSceneClient`, `MetaMuseLabelClient`) | Picks the SAM concepts per keyframe (structured output, `text.format`); per-object label from a crop; civilian SAR scene note from a keyframe | Live mission with `SURMAP_LIVE_META=1` |
| Muse Wonder `muse-wonder-1.0` | Meta Model API, `POST /v1/responses` | `surmap.mapqa` (`MapQa`, `answer`) | Questions and a Markdown situation report over a snapshot | `python -m surmap.mapqa ask/report/serve`; viewer `POST /ask` when `SURMAP_LIVE_META=1` |
| Muse Voice Transcribe `muse-voice-transcribe-1.0` | Meta Model API, `POST /v1/asr/transcribe` (multipart, `PUSH_TO_TALK`, WAV) | `surmap.mapqa.client` | Spoken question to text, then Ask the map | `python -m surmap.mapqa ask-voice` |
| Muse Spark Open `meta-models/muse-spark-open-1026` | Baseten, `POST https://inference.baseten.co/v1/chat/completions`, bearer `BASETEN_API_KEY` | `surmap.labelling.baseten_muse.BasetenMuseLabelClient` | Open-weight per-object label from a crop: `reasoning_effort` `low`, fields from a `record_label` tool call (JSON mode is not supported for this model on Baseten) | Live mission whenever `SURMAP_LIVE_BASETEN=1`, with or without Meta; `seg_bench.py label --provider baseten` |
| Muse Spark Open `meta-models/Muse-Spark-Open-816B-A42B` | Modal shared endpoint, `MODAL_MUSE_URL` + proxy token | `surmap.labelling.modal_muse` | One chat completion | `scripts/check_modal_muse.py` only |
| SAM 3.1 `facebook/sam3.1` (`sam3.1_multiplex.pt`) | Modal GPU app `surmap-sam` (L4), `MODAL_SAM_URL` | `surmap.survey.modal_sam`, `modal_sam_app` | Remote GPU masks | Live mission with `SURMAP_LIVE_MODAL=1` and `--sam-route modal` (or Meta unset); `station_main --detector sam3-modal` |
| SAM 3.1 `facebook/sam3.1` | Station GPU, PyTorch | `surmap.survey.sam3_torch` | Continuous video segmentation in 16-frame windows | `scripts/demo.py --sam-device cuda:0`; `station_main --detector sam31-torch` |
| SAM 3.1 ONNX export | Station, ONNX Runtime | `surmap.survey.sam3` | Same detector port for an exported model | `station_main --detector sam3 --sam3-model <path>` |

Request details (reasoning effort, token caps, usage callbacks, budget
env vars) are in [docs/credits-usage.md](docs/credits-usage.md),
[docs/meta-sam.md](docs/meta-sam.md), and [docs/mapqa.md](docs/mapqa.md).

The on-board detector is Coral, not a Meta model: a Meta-on-Edge-TPU
spike found no Meta checkpoint that compiles to the Edge TPU as a
detector ([docs/coral-edge-tpu-model-spike.md](docs/coral-edge-tpu-model-spike.md)).

## Third-party building blocks

| Piece | What it is | How SurMap uses it | What SurMap adds |
|---|---|---|---|
| RTAB-Map (IntRoLab) | Visual SLAM | Pinned `introlab3it/rtabmap` image: batch sidecar (`rtabmap-euroc_dataset`, `rtabmap-export`) and a streaming `librtabmap` tool built by `scripts/build_rtabmap_stream.py` | Live per-frame odometry and keyframe streaming without stalling playback, dense points under a SAM polygon (`StreamRegionPoints`), ownership-scoped container teardown. Object points are never written back into RTAB-Map |
| PX4 SITL, Gazebo Harmonic, ROS 2 Jazzy | Flight simulator, world simulator, middleware | Fictional civilian earthquake-and-flood block under `docs/simulation/`, stereo camera model, capture dump (`scripts/ros2/dump_sitl_capture.py`), `scripts/launch_disaster_sitl.sh` | Ground-truth people for scoring, EuRoC export of captures (`surmap.simulation`). SurMap never arms PX4 or uploads a mission |
| SAM 3.1 (Meta) | Promptable concept segmentation | Meta Model API, PyTorch on the station GPU, Modal GPU, ONNX adapter | Mask-to-3D projection (`points_in_mask`), persistent object surfaces across window resets, moving-object smear isolation, a route benchmark (`surmap.segbench`) |
| EfficientDet-Lite0, SSD MobileNet V2, SSDLite MobileDet (Coral/Google) | INT8 detectors, COCO labels | `surmap.detection` via LiteRT; Edge TPU artifacts pinned by `scripts/fetch_coral_model.py` | Greedy IoU tracker, separate `StreamDetections` stream, stereo object points inside tracked boxes |
| ConnectRPC (connect-python 0.12.1) | HTTP/Protobuf RPC | Imported serving kit, see above | Survey contracts `Cm5SurveyService`, `StationSamService` |
| EuRoC MAV (ETH ASL) | Stereo/IMU dataset | Dev-console scene `euroc-v1-01-easy`, RTAB-Map e2e subset | Download on demand, SHA-256 pinned, not re-hosted |
| KITTI raw (KIT, TTI) | Driving stereo dataset, CC BY-NC-SA 3.0 | Dev-console scene `kitti-2011-09-26-drive-0009`, KITTI tracking parser | Converted locally, not re-hosted, credited on the page |
| NTU VIRAL (NTU Singapore) | UAV dataset, CC BY-NC-SA 4.0 | Dev-console scene `ntu-viral-sbs-01` | Stereo extrinsics recalibrated from the authors' checkerboard pairs |
| ETH3D `cables_2` | Stereo SLAM sequence | Ten downscaled pairs in `tests/fixtures/eth3d_cables2` (research-use terms in the fixture README) | Test data only |
| VisDrone, Purdue moving-object clips | Video with boxes | Parsers in `surmap.moving.snippets` | Moving-area pipeline tests |

Stereo depth (`surmap.survey.stereo`: SAD block matching, parabolic
subpixel disparity, back-projection) and the IoU tracker are written in
this repository with NumPy and Pillow; OpenCV is not a dependency.
