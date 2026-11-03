# Initial discovery — camera calibration RPC

**Date**: 2026-11-03

## PR #89 correctness gaps addressed

- `src/surmap/docs/todo/2026-11-03-sidecar-odometry-covariance.md` (P1):
  `deploy/rtabmap-stream/main.cpp` called `slam.process(data, odomPose)`
  so RTAB-Map used identity (1 m / 1 rad) odometry covariance.
  Verified against local RTAB-Map headers: `Rtabmap::process` third
  argument is `odomCovariance`, and `RegistrationInfo::covariance`
  (`info.reg.covariance`) is the per-frame estimate to pass.
- Calibration was assumed, never measured: `StereoCalibration` on the
  survey wire and `*.camera.json` profiles are taken as truth. No way
  to calibrate a real rig, verify intrinsics/baseline, or get guided
  feedback while collecting views.

## RTAB-Map calibration — checked, not usable for an RPC

- `rtabmap-calibration` exists in the pinned image
  (`introlab3it/rtabmap@sha256:14a58ac…`, 0.24.2) but is a Qt GUI
  (`CalibrationDialog`, `QDialog`) owning a live camera driver
  (USB/OpenNI/Freenect/DC1394/FlyCapture/RealSense2). No file, pipe,
  or streamed-frame input; no headless API in `rtabmap::core`.
- SurMap builds RTAB-Map with `BUILD_APP=OFF -DBUILD_TOOLS=OFF`
  (`scripts/build_rtabmap_native.sh`); the sidecar links only
  `rtabmap::core`. Reusable: only the OpenCV algorithm
  (`findChessboardCorners` → `calibrateCamera` → `stereoCalibrate`)
  and the `StereoCameraModel` output concept.
- Decision (developer, 2026-11-03): Python RPC with an OpenCV
  sidecar — Python owns the BIDI stream, session, guidance and the
  simulated board; OpenCV runs in a separate sidecar process
  (stdin/stdout, like `surmap-rtabmap-stream`), so the main
  environment and the CM5 survey path gain no native dependency.

## Existing seams reused

- Proto + generated bindings: `proto/surmap/survey/v1/survey.proto`,
  `scripts/gen_survey_rpc.py` (grpcio-tools 1.73.1).
- RPC mounting: `surmap.rpc` `ServiceModule`/`Brick`
  (`src/surmap/survey/cm5_server.py` pattern).
- Frame types: `RawVideoFrame` (channel 0/1, `FrameEncoding`).
- Calibration output types: `StereoCalibration` proto +
  `StereoCalibrationSpec`/`render_cam_sensor_yaml`
  (`src/surmap/simulation/calibration.py`) for EuRoC export.
- Simulated rig numbers: ELP profile
  `examples/bevy-sitl-poc/assets/cameras/elp-stereo-pinhole.camera.json`
  (640×480, fx 381.36, baseline 0.07 m).
