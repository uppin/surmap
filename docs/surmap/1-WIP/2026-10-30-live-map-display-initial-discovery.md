# Initial Discovery: Live RTAB-Map display, overlay and throughput

**Changeset**: [2026-10-30-live-map-display.md](./2026-10-30-live-map-display.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- **Map plane is wrong.** `deploy/rtabmap-stream/main.cpp` builds the
  `StereoCameraModel` with an identity local transform, so RTAB-Map's
  poses and keyframe points are in the camera *optical* frame (x right,
  y down, z forward). `src/surmap/demo/server.py` plots `(x, y)` as the
  "top-down" map — a frontal view that drops depth. Measured on 400
  live frames: cloud spans x 6.0 m, y 4.2 m, **z 8.1 m**; trajectory y
  span 0.89 m (height). The floor plane is x–z.
- **Every frame counts as a keyframe.** The sidecar emits a keyframe
  whenever `getLastLocationId()` changes after `process()` returned
  true. Measured: 400 "keyframes" for 400 frames, but only 45 nodes in
  the optimized graph. The host stores 1000 points per emitted
  keyframe, so the cloud is padded with discarded nodes and
  `map_snapshot()` (pure-Python `Vec3` transforms) grows linearly.
- **Overlay is a separate, unrectified matcher.** The near/far dots come
  from `surmap.survey.stereo.StereoReconstructor`, constructed with the
  default `alignment_offset=(0, 0)`, while EuRoC principal points differ
  by +12.8 px / +6.9 px between cameras; no undistortion or rectification
  rotation. Blank walls produce grid-patterned "near" garbage. Depth
  resolution at the 2× downscaled matching width is `fx·b ≈ 12.6`
  (2 px = 6.3 m, 3 px = 4.2 m).
- **Throughput.** Per-frame medians: stereo matcher 49.9 ms, Coral CPU
  detector 18.7 ms, JPEG 1.1 ms, overlay 1.3 ms. Live playback without
  the detector reached 10.5 fps over 600 frames with the sidecar keeping
  up (lag 1, 0 dropped); `_map_event` cost grew 16 → 286 ms. With the
  detector the user's run showed 3.8 fps at frame 1275.
- **Apple Silicon.** The pinned `introlab3it/rtabmap` digest is
  amd64-only. `docker build` of the derived image fails on arm64 with
  `no match for platform in manifest`; it builds with
  `DOCKER_DEFAULT_PLATFORM=linux/amd64`. Nothing in the repo selects a
  platform.
- **Colour.** EuRoC V1_01 cameras are monochrome; the map is drawn flat
  grey (`#8a929c`). True per-point intensity is available from the left
  rectified image in the sidecar.
- `StreamingRtabmapBackend.map_snapshot()` is used by the demo and by
  `flush()`; `KeyframeUpdate` is re-exported from `surmap.slam`.
  `StereoReconstructor` is also used by `cm5_server`, `cm5_main`,
  `moving_stream` — those stay untouched.

## Exploration 1: demo, sidecar and stereo paths — 2026-10-30

**Agent**: parent Grep/Read plus runtime probes
**Scope**: why the live map and overlay are wrong, and where frame time goes

### Sequence

1. Read `README.md` §Demo — how the demo runs, backends.
2. Run `scripts/demo.py`; read the server log — `SidecarError: streaming sidecar did not become ready`.
3. Run `scripts/build_rtabmap_stream.py` — arm64 platform failure; rebuilt with `DOCKER_DEFAULT_PLATFORM=linux/amd64`.
4. Read `deploy/rtabmap-stream/main.cpp` 143–282 — stereo model, keyframe emission.
5. Read `src/surmap/demo/server.py` 80–320 — overlay, map event, playback loop.
6. Read `src/surmap/slam/streaming.py`, `src/surmap/slam/stream_protocol.py` in full.
7. Read `src/surmap/demo/page.py` — colouring and map drawing.
8. Read `src/surmap/survey/stereo.py` 143–260 — matcher.
9. Probe (scratch script) — per-axis spread of live trajectory/cloud over 400 frames.
10. Probe — per-stage frame timings over 40 frames.
11. Probe — live playback rate and `_map_event` cost over 600 frames.
12. Read EuRoC `cam0/cam1/sensor.yaml` intrinsics.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `another viewer` | `src scripts` | `demo/page.py:131` (shown when no frame arrived) |
| Grep | `platform\|amd64` | `src/surmap/slam scripts` | none |
| Grep | `map_snapshot\|KeyframeUpdate\|StereoReconstructor` | `src tests scripts` | `demo/server.py:63,148`; `slam/__init__.py:12`; `survey/cm5_*`, `moving_stream` |

### Inspected files

#### `deploy/rtabmap-stream/main.cpp`

**Why**: frame convention and keyframe emission.
**Excerpt**:

```cpp
rtabmap::StereoCameraModel stereoModel("surmap", fx, fy, cx, cy, baseline,
                                       rtabmap::Transform::getIdentity(), size);
...
if (!lost) added = slam.process(data, odomPose);
...
int nodeId = slam.getLastLocationId();
if (!lost && added && nodeId > 0 && nodeId != lastNodeId) {
  auto cloud = rtabmap::util3d::cloudFromStereoImages(leftRect, rightRect, stereoModel);
```

#### `src/surmap/demo/server.py`

**Why**: map plane and overlay source.
**Excerpt**:

```python
"cloud_xy": [[round(p.x, 3), round(p.y, 3)] for p in sample],
...
self._stereo = stereo if stereo is not None else StereoReconstructor()
...
points = self._stereo.reconstruct(FrameImage(...left_jpeg), FrameImage(...right_jpeg), rig)
```

#### `src/surmap/demo/page.py`

**Why**: near/far colouring and map colour.
**Excerpt**:

```js
const t = Math.min(1, Math.max(0, (point.d - 0.3) / 5.7));
view.fillStyle = `hsl(${180 - t * 180} 85% 55%)`;
...
ctx.fillStyle = '#8a929c';
```

#### `src/surmap/slam/streaming.py`

**Why**: host-side map state and cost.
**Excerpt**:

```python
for kf in keyframes:
    pose = graph.get(kf.node_id, kf.pose)
    ...
    transformed = tuple(_apply_pose(pose, p) for p in kf.points_local)
```

### Findings

Probe outputs:

```
trajectory 45   x span 1.70  y span 0.89  z span 1.57
cloud 400000    x span 6.03  y span 4.21  z span 8.13
keyframes 400 frames 400 dropped 0

jpeg 1.1 ms · stereo 49.9 ms · overlay 1.3 ms · detect 18.7 ms (medians)

achieved 10.5 fps over 600 frames (no detector)
map_event 16.9 ms @97 … 285.7 ms @324 … 49.2 ms @589
keyframes 595 dropped 0 lag 1
```
