# Initial Discovery: SAM region → dense 3D points

**Changeset**: [2026-10-31-sam-region-points.md](./2026-10-31-sam-region-points.md)
**Date**: 2026-10-31
**Passes**: 3

## Combined Conclusions

- **What RTAB-Map can answer by itself is sparse.** Its 2D→3D link is per visual word:
  `OdometryInfo.words` (keypoints by word id) + `OdometryInfo.localMap` (3D, odom frame)
  per frame, and `Signature::getWordsKpts()` / `getWords3()` per keyframe
  (`rtabmap.getMemory()->getSignature(id)`). Left image only; capped by `Vis/MaxFeatures`
  (1000) / `Kp/MaxFeatures` (500). The sidecar already streams the *inliers* of these as
  the overlay keypoints. Not a surface.
- **Dense depth must be computed, and the sidecar is the right place.** It holds the
  rectified pair (`cv::stereoRectify` + `initUndistortRectifyMap` from the full camera
  YAMLs), the odometry pose, and since #54's base `map_pose` (`getMapCorrection() *
  odomPose`). RTAB-Map ships `util2d::disparityFromStereoImages` (`Stereo/DenseStrategy`
  0=BM, 1=SGBM) and `util3d::cloudFromDisparity`. The keyframe path
  (`cloudFromStereoImages`) voxel-downsamples to 5 cm and is keyframe-only — the region
  path must not reuse it.
- **Stored keyframe images are lossy.** `Mem/ImageCompressionFormat` defaults to `.jpg`,
  applied to *both* stereo images (`Memory.cpp:6853-6854`); disparity from
  `getNodeData()` images is degraded. The region path keeps its own ring of uncompressed
  rectified pairs.
- **The Python `StereoReconstructor` is not a substitute.** It aligns by a constant shift
  (no rectification) and matches at ~160 px width; it remains the CM5's `inmemory`-mode
  scene source.
- **CM5 has no live pose today.** `cm5_main --slam-backend sidecar` uses the *batch*
  `SidecarRtabmapBackend` (poses only at `flush()`); only the demo uses
  `StreamingRtabmapBackend`. A live region query needs the streaming backend on the CM5.
- **Contract seams.** `Cm5SurveyService` already has three BIDI rpcs mounted by one
  `Brick` in `cm5_service_module`; `StreamDetections` shows the "no source configured →
  reject the stream" shape. `Point2`/`Point3` messages exist and are reusable.
- **Sidecar protocol.** Requests are 4-byte LE length + JSON header (+ payloads for
  pairs); responses are JSON lines; `PROTOCOL_VERSION = 3`. The backend has a writer
  thread fed by a bounded drop-oldest pair queue and a reader thread demultiplexing
  `odom` / `keyframe` / `graph` / `error`. Region requests must not go through the
  drop-oldest pair queue.
- **Tests have seams.** `tests/test_slam_streaming.py` drives the backend with a
  `FakeProcess` (scripted stdout lines, recorded stdin). `tests/test_slam_streaming_e2e.py`
  runs the real container over the 90-pair EuRoC fixture and skips when not prepared
  (fails when `SURMAP_REQUIRE_RTABMAP_STREAM_E2E=1`, as CI sets).
- **Demo SAM (#54).** SAM segments **channel 0** display JPEGs (`_SamWorker.submit(…,
  left_jpeg)`); `sam` SSE events carry `mask_polygon` in display pixels; `VideoSamDetector`
  and `VideoSamStreamer` ports have in-memory adapters; `--sam-device` is the only switch.
  The demo's backend is injected via `backend_factory` (a `LiveSlamBackend` protocol), so
  a fake region source fits the existing test style. #53 added the WebGL 3D cloud pane.
- **Prior art, unmerged.** `cursor/project-sam-masks-onto-cloud-6d39` (PRD
  `mask-cloud`: `points_in_mask` filters an existing camera-frame cloud by polygon) and
  `run-full-demo-locally-43aacb7a` (PRD `live-rtabmap-sam-fusion`: accumulating semantic
  layer). Neither is on `main`; neither computes dense per-frame depth. No conflict.
- **Deferred work.** `src/surmap/docs/todo/` holds six moving-objects items; none sits in
  this path. No `code-issues/` or `deferred-answers/` directories exist for `surmap`.

## Exploration 1: RTAB-Map's queryable feature state — 2026-10-31

**Agent**: parent Grep/Read
**Scope**: upstream `introlab/rtabmap` @ `9dac5ce4` (cloned to the session scratchpad) and
`deploy/rtabmap-stream/main.cpp`

### Sequence

1. Grep `keypoint|words|features|statistics|...` in `src` — find where keypoints come from
2. Read `src/surmap/slam/stream_protocol.py` 1–120 — the `Keypoint` wire type
3. Grep RTAB-Map usage in `deploy/rtabmap-stream/main.cpp`
4. Read `main.cpp` 165–348 — setup, per-pair loop, keypoint and keyframe emission
5. Grep `words|localMap|inliersIDs|...` in rtabmap `OdometryInfo.h`, `RegistrationInfo.h`
6. Grep stereo/memory/grid params in rtabmap `Parameters.h`
7. Grep `getWords3|getWordsKpts|getMemory|getNodeData|organizedFastMesh|...` in rtabmap headers
8. Grep `ImageCompressionFormat|ImagePostDecimation` in `Parameters.h`, `compressImage2` in `Memory.cpp`

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `words\|localMap\|inliersIDs` | rtabmap `core/OdometryInfo.h`, `RegistrationInfo.h` | `OdometryInfo.h:109` `words`, `:110` `localMap`; `RegistrationInfo.h:104` `inliersIDs`, `:107` `matchesIDs` |
| Grep | `getWords3\|getWordsKpts` | rtabmap `core/Signature.h` | `:458` `getWordsKpts`, `:562` `getWords3` |
| Grep | `getMemory\|getNodeData\|getSignature` | rtabmap `Rtabmap.h`, `Memory.h` | `Rtabmap.h:351`, `Memory.h:556`, `:621` |
| Grep | `Stereo, DenseStrategy\|StereoSGBM` | rtabmap `Parameters.h` | `:881` `0=cv::StereoBM, 1=cv::StereoSGBM`; `:894-907` SGBM params |
| Grep | `Kp, MaxFeatures\|Vis, MaxFeatures` | rtabmap `Parameters.h` | `:263` 500, `:773` 1000 |
| Grep | `disparityFromStereoImages\|cloudFromDisparity` | rtabmap `util2d.h`, `util3d.h` | `util2d.h:212`, `util3d.h:352`, `:438` |
| Grep | `organizedFastMesh` | rtabmap `util3d_surface.h` | `:74` |
| Grep | `ImageCompressionFormat` / `compressImage2` | rtabmap `Parameters.h`, `Memory.cpp` | `Parameters.h:224` default `.jpg`; `Memory.cpp:6853-6854` right image uses the RGB codec |

### Inspected files

#### `deploy/rtabmap-stream/main.cpp`

**Why**: what the sidecar holds per frame and what it already emits.
**Excerpt**:

```cpp
cv::remap(leftRaw, leftRect, mapLx, mapLy, cv::INTER_LINEAR);
cv::remap(rightRaw, rightRect, mapRx, mapRy, cv::INTER_LINEAR);
rtabmap::SensorData data(leftRect, rightRect, stereoModel, (int)frameId, tNs / 1e9);
rtabmap::Transform odomPose = odom->process(data, &info);
...
for (int wordId : info.reg.inliersIDs) {
  auto kp = info.words.find(wordId);
  auto landmark = info.localMap.find(wordId);
...
auto cloud = rtabmap::util3d::cloudFromStereoImages(leftRect, rightRect, stereoModel);
// Voxel-downsample (~5 cm): keep the first finite point per voxel.
```

#### rtabmap `corelib/include/rtabmap/core/OdometryInfo.h`

**Why**: the per-frame feature state.
**Excerpt**:

```cpp
std::multimap<int, cv::KeyPoint> words; ///< Keypoints of the current frame, by word id (F2M).
std::map<int, cv::Point3f> localMap;    ///< Local feature map in the odometry frame, by word id (F2M).
```

#### rtabmap `corelib/src/Memory.cpp`

**Why**: whether stored images are fit for dense matching.
**Excerpt**:

```cpp
compressedImage = reuseCompressedImage?cv::Mat():compressImage2(image, _rgbCompressionFormat);
compressedDepth = reuseCompressedDepth?cv::Mat():compressImage2(depthOrRightImage,
    depthOrRightImage.type() == CV_32FC1 || depthOrRightImage.type() == CV_16UC1
    ? depthCompressionFormat : _rgbCompressionFormat);
```

### Findings

RTAB-Map's 2D↔3D link is sparse and left-only; dense per-pixel depth is not stored and
must be computed. The sidecar already has every input for it (rectified pair, pose).
Stored keyframe images are JPEG by default — unsuitable for matching.

## Exploration 2: survey contract, CM5 server, Python stereo — 2026-10-31

**Agent**: parent Grep/Read
**Scope**: `proto/`, `src/surmap/survey/`, `src/surmap/slam/`, `docs/connectrpc.md`

### Sequence

1. Grep `channel|sam|segment` in `src` — where channels and SAM live
2. Read `docs/connectrpc.md` 1–80 — rpc kit shape
3. Read `proto/surmap/survey/v1/survey.proto` — whole contract
4. Read `src/surmap/survey/sam.py` 1–40 — SAM port
5. Read `src/surmap/survey/stereo.py` 1–60, 90–213 — Python reconstructor
6. Read `src/surmap/survey/cm5_server.py` 1–200, 236–297 — handlers and service module
7. Read `src/surmap/slam/base.py` — `SlamBackend` port
8. Read `src/surmap/survey/cm5_main.py` 52–192 — backend wiring
9. Grep `def to_map_frame` in `src/surmap/geometry.py`
10. List `src/surmap/docs/todo/`, read each head — deferred-work cross-check

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `channel` | `src/surmap` | `slam/streaming.py:167` `_to_gray8(frame, channel, …)`; `demo/server.py:361` |
| Glob | `*.proto` | repo | `proto/surmap/survey/v1/survey.proto`, `proto/surmap/transport/v1/socket_rpc.proto` |
| Grep | `def to_map_frame` | `src/surmap/geometry.py` | `:21` |

### Inspected files

#### `proto/surmap/survey/v1/survey.proto`

**Why**: where the new rpc belongs and which messages exist.
**Excerpt**:

```proto
service Cm5SurveyService {
  rpc StreamSurvey(stream Cm5Request) returns (stream Cm5Response);
  rpc StreamDetections(stream Cm5Request) returns (stream DetectionResponse);
  rpc StreamMovingAreas(stream Cm5Request) returns (stream MovingAreasResponse);
}
message Point2 { double x = 1; double y = 2; }   // image pixel coordinates
message Point3 { double x = 1; double y = 2; double z = 3; }  // map frame
```

#### `src/surmap/survey/cm5_main.py`

**Why**: which SLAM backend the CM5 runs.
**Excerpt**:

```python
if args.slam_backend == "sidecar":
    description = build_description(
        slam=sidecar_backend(args.calibration_dir, args.rtabmap_image, args.rtabmap_shared_container),
        use_stereo=False,
        detections=detections,
    )
```

#### `src/surmap/survey/stereo.py`

**Why**: whether the existing Python dense path fits.
**Excerpt**:

```python
scale = max(1, left_gray.shape[1] // self._match_width_px)
small_left = left_gray[::scale, ::scale]
...
aligned_right = _shift_image(small_right, round(offset_x / scale), round(offset_y / scale))
```

### Findings

The rpc slots in beside the three existing BIDI methods; `StreamDetections` is the model
for "reject without a source". The CM5's RTAB-Map mode is batch-only today. The Python
reconstructor has no rectification and a low matching width.

## Exploration 3: refreshed `main` (#53, #54), streaming backend, demo SAM — 2026-10-31

**Agent**: parent Grep/Read
**Scope**: `git diff 05c7b85 HEAD`, `src/surmap/slam/streaming.py`, `src/surmap/demo/server.py`,
`tests/test_slam_streaming*.py`, prior PRDs on other branches

### Sequence

1. `git diff --stat 05c7b85 HEAD` — what landed since the stale branch
2. Read changelogs `2026-10-31-rtabmap-demo-sam31-video.md`, `2026-10-31-generic-test-console.md`
3. `git diff` of `stream_protocol.py`, `sam.py`, `main.cpp` — `map_pose`, video SAM ports
4. Grep `sam|Sam` in `src/surmap/demo/server.py`; read `_sam_event`, `build_server` SAM wiring
5. Grep structure of `src/surmap/slam/streaming.py`; read 207–422
6. Grep test structure of `tests/test_slam_streaming.py`; read `tests/test_slam_streaming_e2e.py` 1–60
7. `git log --all --diff-filter=A` for `PRD-*` — prior SAM/cloud PRDs; read `mask-cloud` and `live-rtabmap-sam-fusion` heads
8. Read prior changeset `2026-10-30-kitti-demo.md` — repo changeset conventions

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `sam\|Sam` | `src/surmap/demo/server.py` | `:444` `_SamWorker`, `:518` `_sam_event`, `:540` `_SamStreamWorker`, `:948` `submit(index + 1, t_ns, left_jpeg)` |
| Grep | `^def test` | `tests/test_slam_streaming.py` | `FakeProcess` `:33`, `test_frame_odometry_returns_that_frames_pose_and_keypoints` `:343` |
| git log | `PRD` adds | all branches | `PRD-2026-10-28-mask-cloud.md` (branch `cursor/project-sam-masks-onto-cloud-6d39`), `PRD-2026-10-29-live-rtabmap-sam-fusion.md` (branch `run-full-demo-locally-43aacb7a`) |

### Inspected files

#### `deploy/rtabmap-stream/main.cpp` (diff since `05c7b85`)

**Why**: pose the region points should use.
**Excerpt**:

```cpp
<< ",\"map_pose\":"
<< (lost ? std::string("null") : poseJson(slam.getMapCorrection() * odomPose))
```

#### `src/surmap/slam/streaming.py`

**Why**: how a request/response pair can be added without blocking playback.
**Excerpt**:

```python
self._in_queue: queue.Queue[tuple[StereoFramePair, bytes, bytes] | None] = queue.Queue(
    maxsize=max(1, queue_size)
)
...
def _write_loop(self) -> None:
    while True:
        item = self._in_queue.get()
```

#### `src/surmap/demo/server.py`

**Why**: where SAM results enter the event stream.
**Excerpt**:

```python
def _sam_event(frame_id: int, t_ns: int, detections: tuple[SamDetection, ...]) -> DemoEvent:
    return DemoEvent("sam", {"frame_id": frame_id, "t_ns": t_ns, "objects": [ ...
        "mask_polygon": [[round(x, 1), round(y, 1)] for x, y in detection.mask_polygon],
```

### Findings

`map_pose` exists per odom message, so map-frame placement needs no new pose plumbing.
The writer thread is the single stdin owner; region requests need their own,
non-dropping path to it. Demo SAM is channel 0, display pixels; the region event can hang
off `sam` events by `frame_id`.
