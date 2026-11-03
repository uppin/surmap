# Camera calibration (checkerboard)

`CameraCalibrationService.StreamCalibration` measures the stereo rig's
intrinsics, distortion and extrinsic from checkerboard views, instead of
taking `StereoCalibration` / `*.camera.json` values on trust. Its logic
follows RTAB-Map's own calibration dialog
(`guilib/src/CalibrationDialog.cpp` in introlab/rtabmap); where SurMap
differs, this page says so.

Enable it on the CM5 server with `cm5_main --calibration`. It needs the
`calibration` extra (`uv sync --extra calibration`, which adds
`opencv-python-headless`); the survey path imports no OpenCV.

## The stream

The service is BIDI on `surmap.survey.v1`
(`proto/surmap/survey/v1/survey.proto`):

1. **Config** (first message): an explicit
   `CALIBRATION_TARGET_CHECKERBOARD` with its `CheckerboardSpec` (inner
   corners across × down, square size in metres), and optionally
   `min_views` (default 8), `width`/`height` (0 takes them from the
   first frame; every frame must then match), `lens_model`,
   `max_detection_scale` (1–3) and `expected_baseline_m`.
2. **Plan** (first response, as soon as the image size is known): the
   nine `CalibrationViewpoint`s that together clear the readiness bar
   below. They are in image terms — board centre, size, which board
   corner to turn away, a nominal distance and an instruction — so they
   need none of the intrinsics being solved.
3. **Frames → feedback**: each `CalibrationStereoFrame` is answered with
   `CalibrationFeedback`: found in each eye, accepted / board not found /
   too similar / frame unreadable, the view's centre, size and skew, the
   four spreads, `ready`, the plan viewpoint it filled
   (`matched_viewpoint`, −1 for none), the viewpoints that remain, and a
   `MoveSuggestion` for the next view.
4. **Finish → result**: `finish` before the views are ready is answered
   `not_ready` with the progress so far, and the stream stays open. A
   ready `finish` returns `EstimatedStereoCalibration`.

A frame that cannot be decoded is reported as `FRAME_UNREADABLE` and the
stream goes on. Contract violations end it: no config first, a target
other than checkerboard, a detection scale above 3, or a frame whose size
differs from the stream's.

## The capture plan

| Viewpoints | Target | Why |
|---|---|---|
| 1 | Near (size 0.55), facing the camera, centred midway between the lenses | Largest size. Centred on one lens, the other eye loses it to the stereo disparity |
| 4 | Far (size 0.13; 0.28 for fisheye), facing the camera, at (0.2, 0.2) … (0.8, 0.8) | Spreads x, y and size. Inset from the edge so the other eye still sees the whole board |
| 4 | Middle distance (size 0.3), centred, one board corner turned about 45° away | Skew. RTAB-Map's skew is a corner angle, which a diagonal tilt changes; turning one side away barely does |

A view fills a viewpoint when its centre is within a sixth of the image
of the target, its size within 25% of the target size, and the same
corner is turned away (or none). The turned-away corner is read from the
image: the opposite corner pair with the widest mean angle (> 95°) is far
and near, and the far one has the shorter edges. A view that fills a
remaining viewpoint is kept even when the duplicate rule would call it
alike, because opposite tilts read the same unsigned skew but constrain
the solve differently.

The suggestion is the remaining viewpoint that widens the first spread
still short (position, then tilt, then size), with the camera move from
the current view. Once the plan is used up and the bar is not met, it
falls back to the first uncovered 3×3 cell, then tilt, then distance.
Distances use a nominal focal length of one image width (≈53° HFOV);
they are guidance, not measurement. Simulated rigs at fx 300, 381 and
520 that follow the plan fill all nine viewpoints and clear the bar.

## Views and readiness (RTAB-Map's rules)

Each view is measured from its left-eye corners as RTAB-Map's
`getParams` does, each value in [0, 1]: board centre x and y, size =
sqrt(board quad area / image area), and skew = 2·|90° − the angle at the
board's upper-right corner|.

- A view needs the full grid in **both** eyes. If the right eye lists
  the corners from the board's other end, it is reordered to match.
- A view is rejected as too similar when an accepted one is within
  |Δx|, |Δy| < 0.1, |Δsize| < 0.05 and |Δskew| < 0.1.
- The session is **ready** with at least `min_views` accepted views
  whose spreads (max − min) reach x > 0.5, y > 0.5, size > 0.4 (0.25 for
  fisheye) and skew > 0.5. Face-on views alone, which cannot fix the
  focal length, are never ready.

## Detection and solving (the OpenCV sidecar)

`surmap.calibration.opencv_sidecar` runs as its own process, speaking
JSON lines over stdin/stdout behind the `CheckerboardVision` port.

- **Detect**: `findChessboardCorners` (adaptive threshold, normalised),
  retried on the frame upscaled 2× … `max_detection_scale`× for boards
  too small at native resolution, with corners mapped back to native
  pixels; then `cornerSubPix` with a half-window of half the smallest
  corner spacing. If any corner moves more than 1 px (RTAB-Map's default
  bound), the whole board is dropped; RTAB-Map drops only that corner,
  but views here are full grids without corner IDs. `findChessboardCornersSB`
  is the fallback when the classic detector finds nothing.
- **Solve**: each eye alone, then the extrinsic with intrinsics fixed:

  | `lens_model` | Solver | Distortion |
  |---|---|---|
  | `PINHOLE_RADTAN` (default) | `calibrateCamera` + `stereoCalibrate`, k3 held at 0 | k1, k2, p1, p2 |
  | `PINHOLE_RATIONAL` | the same with `CALIB_RATIONAL_MODEL` | k1, k2, p1, p2, k3, k4, k5, k6 |
  | `FISHEYE` | `cv::fisheye::calibrate` + `cv::fisheye::stereoCalibrate`; an ill-conditioned view is dropped and the solve retried while ≥ 4 remain | k1, k2, k3, k4 |

- **Expected baseline**: when `expected_baseline_m` > 0 the solved
  translation is scaled to it; the result reports `baseline_scale`, the
  `solved_baseline_m` before scaling and the `implied_square_size_m`
  (square size × scale; a scale far from 1 usually means a mis-measured
  square). Intrinsics do not depend on the square size and stay as
  solved.

The result carries per-eye fx, fy, cx, cy and distortion, the
left → right rotation and translation (x_right = R·x_left + T), the
baseline, reprojection RMS per eye and for the stereo solve, and the
number of views used.

## Export to the streaming sidecar

`surmap.calibration.export.estimated_sensor_yamls` writes a solved
estimate as the EuRoC `cam0`/`cam1` `sensor.yaml` pair: each eye's own
intrinsics and distortion, and body poses whose
inv(T_BS_cam1) · T_BS_cam0 is the solved [R | T], which is what the
streaming sidecar rectifies from. Only radial-tangential estimates are
exported: the sidecar's rectification, its rectification message to the
host and its region answers assume that model, so rational and fisheye
estimates are refused rather than misread.

## Verification

Tests solve from **detected** corners of a simulated board
(`surmap.calibration.simulated`: 8× supersampled, through an ideal,
radial-tangential/rational or fisheye lens), so the whole pipeline is
judged against known truth. Recovered fx is within 2% and the baseline
within 3% for every lens model; a board at 4.5 m, about 3.4 px per
square, is found with 2× upscaling and missed without it.
