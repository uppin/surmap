# Camera calibration RPC (checkerboard) + sidecar covariance fix

**Date:** 2026-11-03
**Area:** survey / calibration

BIDI `CameraCalibrationService.StreamCalibration`: the client opens
with an explicit `CALIBRATION_TARGET_CHECKERBOARD` config (9x6-style
inner-corner grid + square size; frame size optional, else taken from
the first frame; lens model; detection upscaling up to 3x; an optional
expected baseline). The first response is the whole capture plan: nine
viewpoints in image terms (centre, size, which board corner to turn
away, a nominal distance and an instruction) that together clear
RTAB-Map's readiness bar — they need no intrinsics, so they are known
before the first frame. The client then streams stereo pairs and gets
per-view feedback naming the viewpoint each view filled and those that
remain, plus a `MoveSuggestion` for the next one. Views are measured and gated as RTAB-Map's
calibration dialog does: board x, y, size and skew per view, a view
kept unless it repeats an earlier one on all four, and ready only
when the kept views spread over x, y > 0.5, size > 0.4 and skew > 0.5
— so a set of flat, face-on views (which cannot fix the focal length)
is never solved. Guidance asks for position, then tilt, then
distance. An undecodable pair is reported `FRAME_UNREADABLE` and an
early `finish` is answered `not_ready`; neither ends the stream. A
ready `finish` returns the solved `EstimatedStereoCalibration`
(per-eye fx/fy/cx/cy, k1/k2/p1/p2 distortion, the left→right R and T,
baseline, reprojection RMS) for the chosen lens model — pinhole
radial-tangential, rational or equidistant fisheye, as in RTAB-Map's
dialog, fisheye pruning ill-conditioned views the same way. With an
expected baseline the translation is rescaled to it and the result
reports the scale and the square size the solve implied.
`surmap.calibration.export` writes a radial-tangential estimate as the
EuRoC `sensor.yaml` pair the streaming sidecar rectifies from; rational
and fisheye estimates are refused until the sidecar can rectify them
(`src/surmap/docs/todo/2026-11-03-streaming-sidecar-lens-models.md`).

Detection and solving run in an OpenCV sidecar
(`python -m surmap.calibration.opencv_sidecar`, JSON lines over
stdin/stdout) behind the `CheckerboardVision` port — RTAB-Map's
pipeline (`findChessboardCorners` → `cornerSubPix` with a window of
half the corner spacing and a 1 px drift bound → `calibrateCamera`
→ `stereoCalibrate` with fixed intrinsics), without the GUI or
live-camera ownership. RTAB-Map's own tool was checked and is not
usable for an RPC (GUI, direct camera drivers, built with
`BUILD_TOOLS=OFF` in SurMap's native build). A simulated
checkerboard (`SimulatedCheckerboard`, supersampled so corners are
unbiased) renders known-truth stereo pairs; detected corners land
within 0.25 px of truth, and solving from the detector's own corners
recovers fx within 2% and the 7 cm baseline within 3%. Enable on the
CM5 server with `--calibration`.

Also fixes the P1 deferred from PR #89: the streaming sidecar now
passes the odometry covariance to `Rtabmap::process` instead of
RTAB-Map's identity default, prepared as RTAB-Map's own `RtabmapThread`
prepares it (`deploy/rtabmap-stream/odom_covariance.h`): invalid or
"unknown" (1.0) covariances fall back to identity, the largest one is
carried across nodes RTAB-Map drops for too little motion, and an
odometry reset clears it. Unlike `RtabmapThread` the sidecar does not
start a new map on reset — the reset link carries near-zero
information and keyframes keep one map frame for the host. The policy
has a C++ unit test the image build runs. The full-loop closure acceptance that
proves the fix end to end stays in
`src/surmap/docs/todo/2026-11-03-bevy-loop-closure-acceptance.md`.
