# 2026-11-03 — Streaming sidecar rectifies radial-tangential lenses only

**Category:** Capability gap (found while adding calibration lens models)
**Source:** camera-calibration-rpc changeset (`camera-calibration-rpc-6847602b`)
**Packages:** deploy/rtabmap-stream, surmap.slam, surmap.calibration
**Consent:** Developer, 2026-11-03: "it's fine to defer fisheye". The
calibration RPC solves all three models; only their export is refused.
**Priority:** 2
**Status:** Open

## What is missing

`CameraCalibrationService` now solves RTAB-Map's three lens models
(pinhole radial-tangential, rational, equidistant fisheye), but
`surmap.calibration.export.estimated_sensor_yamls` refuses rational and
fisheye estimates. The streaming sidecar (`deploy/rtabmap-stream/main.cpp`)
assumes radial-tangential end to end:

- rectification uses `cv::stereoRectify` / `cv::initUndistortRectifyMap`
  (fisheye needs `cv::fisheye::*` or RTAB-Map's `stereoRectifyFisheye`);
- the `ready` message sends 4 distortion coefficients, which the host uses
  to map rectified keypoints back onto the raw image (rational has 8);
- the region rig (`answerRegion`) undistorts with the pinhole model.

## Done when

A fisheye and a rational calibration exported from the RPC drive the
streaming sidecar to the same keypoint-to-raw mapping and region answers
as their own OpenCV models, proven on a simulated fisheye rig.
