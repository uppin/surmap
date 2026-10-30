# Live RTAB-Map display, keypoint overlay and throughput

**Date:** 2026-10-30
**Feature:** browser demo / streaming RTAB-Map backend

The live demo map is now a floor plan of the room. The sidecar emits a
keyframe only for a node RTAB-Map's optimised graph keeps (before: every
frame — 595 "keyframes" for 45 graph nodes), each graph update is
authoritative on the host, and the map is plotted on the optical
frame's floor plane (x, z) instead of the frontal (x, y) view. Keyframe
points carry the left rectified image's intensity and are capped at
6 m depth; the host keeps the map as cached numpy arrays.

The overlay is RTAB-Map's own odometry inlier keypoints for each frame
(protocol v3: the ready message carries the left camera's
rectification, each odom message its keypoints), mapped rectified → raw
through R1ᵀ and the radial-tangential model; a frame is held until its
odometry arrives, and detections never run ahead of their frame. The
depth ramp lives in Python and fixes the page's inverted hue (it drew
near points cyan, far ones red). The numpy matcher is no longer run on
the live path, pairs travel as raw gray8, and the detector runs on a
latest-only worker thread. Docker build/run/pull pin `linux/amd64`, so
the sidecar works on Apple Silicon; a bad hello fails fast.

Verification: gates green (ruff format/check, mypy strict, pytest 540
passed, 2 skipped) and the real-container streaming e2e green. Measured
on 600 live EuRoC frames with the Coral detector on an Apple Silicon
host (emulated sidecar): 18.0 fps shown (3.8 fps before), 56 ms median
display hold-back, keypoints on 599/600 frames (156 median), the same
feature moving 2.83 px median between frames, map events 3.3 ms median
(16 → 286 ms before).
