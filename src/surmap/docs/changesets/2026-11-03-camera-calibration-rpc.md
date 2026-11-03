# Camera calibration RPC with a capture plan; streaming-sidecar odometry covariance

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap

`CameraCalibrationService.StreamCalibration` (BIDI, `surmap.survey.v1`) measured
the stereo rig from checkerboard views, following RTAB-Map's calibration dialog
(`guilib/src/CalibrationDialog.cpp`). The first response was a capture plan of
nine viewpoints in image terms — one near, four far corners, four diagonal tilts
— that clears RTAB-Map's readiness bar without knowing the intrinsics; feedback
named the viewpoint each view filled. Views were measured and gated by RTAB-Map's
x / y / size / skew rules. A new `surmap.calibration` package held the session,
plan, baseline rescale, EuRoC export and an OpenCV sidecar process: sub-pixel
refinement with half the corner spacing and a 1 px drift bound, detection
upscaled up to 3×, and pinhole radial-tangential, rational and fisheye solves.
OpenCV moved into a `calibration` extra (and the dev group), so the survey
install stays free of it.

The streaming RTAB-Map sidecar passed the odometry covariance to
`Rtabmap::process`, prepared as RTAB-Map's `RtabmapThread` prepares it, in
`deploy/rtabmap-stream/odom_covariance.h` with a C++ unit test the image build
runs. An odometry reset kept the map session; the link across it carries
near-zero information.

Verification: tests solved from detected corners of a supersampled, lens-distorted
simulated board; fx came back within 2% and the baseline within 3% for every lens
model, and a simulated person following the plan cleared the bar at fx 300, 381
and 520.

Before the review fixes in this PR, a fixed 11×11 sub-pixel window and a
view-count-only readiness gate let the same detected corners solve to fx 631.9 and
a 0.554 m baseline (truth 381.36 / 0.07 m).

Wrap notes: `calibration/fake.py`, an unused scripted adapter, was removed; long
sidecar, plan, session and service functions were split; `detect` took an
`EncodedFrame` and the simulator a `StereoRig`. The streaming sidecar's rational
and fisheye support was deferred with the developer's consent
(`src/surmap/docs/todo/2026-11-03-streaming-sidecar-lens-models.md`). The
architecture doc's claim that an odometry reset starts a new map session was
corrected: no code did that.
