# SLAM ↔ segmentation protocol guidelines

Recommended names and conventions for one exchange: the SLAM / point-cloud
side (Mantas, @uppin) sends a camera frame, the segmentation side
(Ginas, @JazzGinas) sends masks for that same frame. This is guidance
for the Meta hackathon disaster-mapping demo. It is not a schema. Nothing
in the tree validates these files.

The consumer that already exists is
`surmap.survey.mask_cloud.points_in_mask`. It keeps camera-frame points
whose pinhole projection falls inside a mask polygon, drops points at or
nearer than 5 cm, and, when a pose is passed, transforms the survivors
with `surmap.geometry.to_map_frame`. That result is a registration layer.
It should stay out of RTAB-Map's internal map
([architecture.md](architecture.md) §1, [mask-cloud.md](mask-cloud.md)).

Field names below follow the code that already holds them. Where two
modules disagree, the disagreement is listed under
[Open questions for @uppin](#open-questions-for-uppin) and is not resolved
here.

## What the SLAM side typically sends

One record per camera frame. Segmentation runs on one channel; the other
channel is for depth ([architecture.md](architecture.md) §5). The live
path uses the left image.

| Recommended field | Where the code already says this | Notes |
|---|---|---|
| `frame_id` | `StereoFramePair`, stream `pair`, `RawFrame`, station proto | Integer. The station echoes it on the way back. |
| `t_ns` | same types; architecture §6 | Integer nanoseconds. See the clock section. The name in code is `t_ns`. |
| `left_ref` | `StereoFramePair.left_ref` | Path or other reference to the image. Metadata should point at the image; the bytes can travel beside it (`left_data`, the stream pair payload, `RawFrame.data`). |
| `width`, `height` | `RawFrame`, stream `pair`, `StereoCalibrationSpec` | Pixels of the image the mask will be drawn on. |
| `fx`, `fy`, `cx`, `cy` | `StereoRig`, EuRoC `intrinsics: [fx, fy, cx, cy]` | Pinhole, in pixels, at that width and height. `points_in_mask` projects with these and ignores distortion. |
| `distortion_model`, `distortion_coefficients` | EuRoC `sensor.yaml` via `surmap.demo.datasets` and `simulation/calibration.py` | Model string `radial-tangential`. Coefficients `[k1, k2, p1, p2]`. |
| `baseline_m` | `StereoRig.baseline_m` | Metres. This is the depth cue the stereo path has. There is no depth-image path in the current types. |
| `pose` | `surmap.types.Pose` | Camera pose used to place points in the map. Position in metres, quaternion `(x, y, z, w)`. |

`right_ref` is the natural place for the other image when stereo depth
is reconstructed on the SLAM side rather than passed as a depth image.

### Pose

`Pose` is a position plus `orientation_xyzw`. The streaming wire sends the
same pose as seven numbers `[x, y, z, qx, qy, qz, qw]`
(`surmap.slam.stream_protocol`). `to_map_frame` and
`surmap.slam.streaming.pose_rotation` both apply it as

```text
p_map = R(q) · p_camera + t
```

with column vectors. A 4×4 `T_map_camera` with that `R` and `t` is the
same transform. The code does not store the live pose as a matrix, and
`Pose` has no `frame` field. The 4×4 that does exist is EuRoC `T_BS`
(body ← sensor) in `sensor.yaml`, which is calibration, not the per-frame
camera pose.

Odometry messages also carry `map_pose`: the pose after RTAB-Map's
odometry-to-map correction (`OdomUpdate` in `stream_protocol.py`). The
demo floor wedge uses `map_pose` when it is present, otherwise `pose`.
`StreamingRtabmapBackend.flush` returns the odometry `pose`. The assembled
cloud (`map_snapshot`) is placed with the graph pose. A mask projected
with the flush pose onto that cloud can disagree with the cloud after a
loop closure.

A `frame` string on the pose is worth sending anyway, so the segmentation
side can tell a RTAB-Map map pose from a body pose or an ENU pose. Suggested
value when it is the streaming map: `rtabmap_map`. Which frame that
actually is is an open question below.

### Clock

Architecture §6: timestamps are monotonic-clock nanoseconds on the CM5,
plus one UTC wall-clock anchor per session. The field name is `t_ns`.

Two other clocks already land in that same field:

- SITL capture (`scripts/ros2/dump_sitl_capture.py`) writes ROS
  `header.stamp` (`sec * 1_000_000_000 + nanosec`).
- Demo datasets (EuRoC, KITTI, NTU VIRAL) copy the dataset timestamp into
  `t_ns`.

The record should say which of these it is, in a `clock` string next to
`t_ns`, until one source is confirmed. Suggested values: `cm5_monotonic`,
`ros_header_stamp`, `dataset`.

### Which pixels the intrinsics belong to

The stream's `Rectification` (`stream_protocol.py`) carries three
related sets: rectified `(fx, fy, cx, cy)`, raw `(fx, fy, cx, cy)`, and
raw radial-tangential distortion, plus OpenCV `R1` (row-major). The demo
draws on the raw image and maps rectified keypoints back with
`rectified_to_raw` (`surmap.demo.server`). `StereoRig`, which
`points_in_mask` uses, is a single pinhole and a baseline, with no
distortion.

The intrinsics on the frame should be the pinhole of the image file
named by `left_ref`. A mask in another pixel space (raw lens image vs
rectified) will claim the wrong points. `pixel_space` on the frame is a
useful label: `rectified` or `raw`.

Image encodings already in use, for the bytes beside `left_ref`:

| Encoding string | Who uses it |
|---|---|
| `mjpeg`, `raw_rgb` | `FrameImage`, station proto, Meta SAM (`meta_sam.py` accepts only these) |
| `png` | mission demo builds a `RawFrame` with this encoding (`mission/demo.py`) |
| `gray8` | streaming sidecar pair payload |

`decode_rgb` (`detection/detector.py`) accepts `raw_rgb` or any bytes
Pillow can open. Meta SAM rejects `png`.

## What the segmentation side typically sends

One record per frame. `frame_id` should be the same integer that arrived
on the frame. The station service already does this:
`SamFrameDetections.frame_id` (`station_server.py`). It does not echo
`t_ns`. Echoing `t_ns` as well makes a dropped or reordered frame obvious.

Each mask:

| Recommended field | Where the code already says this | Notes |
|---|---|---|
| `encoding` | Meta request metadata uses `mask_encoding` | How `mask` is stored. See below. |
| `label` | `SamDetection.label` | Short noun. Station ONNX default is `object`. Modal uses the prompt (`person` unless overridden). |
| `score` | `SamDetection.score` | Float. Meta SAM stores `1.0` when the response has no confidence field (`meta_sam.py`). That `1.0` means "missing", which is easy to misread as certain. |
| `source` | three `SamDetector` adapters, no shared field yet | `station-onnx`, `modal`, or `meta-api`. |
| `model_id` | Meta `model` (`sam-3.1`); Modal `usage_model_name` | Which weights. See below. |

`box_xyxy` and `track_id` already ride on `SamDetection` and the station
proto. They are useful context. The projection step uses the mask, not
the box.

### Mask encoding

What the projection consumes today is `mask_polygon`: a list of `[x, y]`
vertices in frame pixels, the same space as `width` and `height`.
`mask_outline` (`sam3.py`) builds a coarse outline (at most 96 points).
`points_in_mask` runs an even-odd test on that ring and ignores a polygon
with fewer than three vertices. Modal returns the same polygon as
`mask_polygon`. Meta's wire mask is `one_bit`; the adapter turns it into
that polygon before anything else sees it.

A dense mask is a reasonable thing to send alongside the polygon:

- `encoding: "polygon"` and `mask_polygon: [[x, y], ...]` — what the
  current projection reads.
- `encoding: "png"` and `mask` as a path to a single-channel image, same
  width and height as the frame.
- `encoding: "coco_rle"` and `mask` as COCO uncompressed or compressed
  RLE, with `size: [height, width]`.

PNG and COCO RLE do not appear in the survey code. Sending them is fine
as long as the polygon the projection already understands is there too,
or until `points_in_mask` grows a raster path. Architecture §6 `Segment`
says "mask reference", which matches a path better than an inline polygon.

### Source and model id

| `source` | Adapter | `model_id` the adapter would put here |
|---|---|---|
| `station-onnx` | `surmap.survey.sam3.Sam3Detector` | No id string today. The checkpoint is the `--sam3-model` path (`station_main.py`). The path, or a hash of the file, is the honest id. |
| `modal` | `surmap.survey.modal_sam.ModalSamDetector` | `surmap-sam/<gpu>` (default GPU `L4`), or `MODAL_SAM_MODEL` when set (`usage_model_name`). |
| `meta-api` | `surmap.survey.meta_sam.MetaSamDetector` | `sam-3.1` unless `model=` overrides it. |

The `model_id` on a semantic-map snapshot landmark is a different string:
the Muse labeller that named the track (`mission/demo.py` stores
`labelled.model_id`). It should not be copied into this field.

## Units

Distances in this tree are metres: `baseline_m`, keypoint `depth`,
`Vec3`, `max_depth_m`, the 5 cm near plane in `points_in_mask`. Intrinsics
and polygon vertices are pixels. A pose translation should be metres in
the same frame as the cloud it places.

## Example

One illustrative exchange. Nothing loads this file.

[segmentation-protocol-example.json](segmentation-protocol-example.json)

The pose is an identity quaternion, so camera axes and map axes match
for that frame. The polygon is a rectangle in the 376×240 image. `clock`
and `frame` are the labels suggested above; both are open questions.

## Open questions for @uppin

Please confirm or correct these. The guidelines take no side.

### Coordinate frame and handedness

Several frames are already named in code, and they are not the same:

1. Camera optical, in `simulation/calibration.py`: +X right, +Y down,
   +Z forward. `viewer/poses.py` uses the same optical axis (+Z forward,
   image +Y world-down when the camera is level).
2. Semantic-map snapshot and `viewer/poses.py`: local ENU, x east,
   y north, z up, metres from the first GPS fix (`map/snapshot.py`).
3. Demo floor plan (`demo/server.py`, `floor_camera`): the drawn floor
   is the pose's x–z plane, so y is the axis left out. A camera looking
   straight down keeps a +z heading. That picture matches a frame whose
   vertical axis is y, which is the optical frame in (1) at the identity
   pose, and it does not match ENU in (2), whose floor is x–y.
4. EuRoC body frame for `T_BS`: +X up, +Y right, +Z forward. The Gazebo
   link is forward-left-up; the export negates Y rather than moving the
   simulated camera (`simulation/calibration.py`).

Which of these is the RTAB-Map map frame on `OdomUpdate.pose` /
`map_pose`? Is it right-handed, and which axis is up? Should segmentation
multiply by the odometry pose (what `flush` returns) or by `map_pose` /
the graph pose (what `map_snapshot` uses to place the cloud)?

### Units

Are RTAB-Map pose translations metres, in the same scale as `baseline_m`
and the stereo cloud? The types treat them as metres. A scaled visual
frame would silently shift every projected mask.

### Timestamp source

Is `t_ns` on a live survey the CM5 monotonic clock from architecture §6,
the ROS `header.stamp` the SITL dump writes, or a dataset clock? Where
does the session's UTC wall-clock anchor live, if the segmentation side
should see it? Should the mask record echo `t_ns` as well as `frame_id`?

### Other mismatches

- Live pose is a translation plus quaternion `(x, y, z, w)`, seven
  numbers on the stream wire. `Pose` has no `frame` field. The only 4×4
  in the camera config is `T_BS`.
- `StereoRig` has no distortion. Distortion is `radial-tangential`
  `[k1, k2, p1, p2]` on EuRoC `sensor.yaml` and on the raw half of
  `Rectification`, which also has a separate rectified pinhole and `R1`.
  `points_in_mask` uses the undistorted pinhole only.
- The image the demo shows is raw. The image RTAB-Map tracks is
  rectified. Masks should name which of those two they were drawn on.
- `RawFrame.encoding` is `png` in the mission demo, `mjpeg` / `raw_rgb`
  on the station proto, and `gray8` on the streaming pair. Meta SAM
  accepts only `mjpeg` and `raw_rgb`.
- Station ONNX has a model path and no `model_id`. Snapshot `model_id`
  is the labeller, not SAM.
- Masks in code are polygons from `mask_outline`, not PNG files or COCO
  RLE. Meta's wire encoding is `one_bit`, converted to a polygon before
  projection.
