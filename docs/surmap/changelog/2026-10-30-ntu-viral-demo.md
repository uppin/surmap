# NTU VIRAL outdoor drone scene

**Date:** 2026-10-30
**Feature:** browser demo / dataset registry / streaming RTAB-Map backend

A third scene: NTU VIRAL `sbs_01`, a 354 s UAV flight over NTU
Singapore's Biological Sciences plaza, fetched from the dataset's
Hugging Face host (size + SHA-256 pinned, matching its published
`SHA256SUMS.txt`). Its ROS 1 bag is unpacked to a temporary file
(unpacking progress), the stereo `sensor_msgs/Image` messages are read
through a typed adapter over `rosbags` (new dependency), each right image
pairs with the nearest left within 5 ms, both are written as PNG, and the
bag is deleted — 3,540 pairs in 81 s.

Calibration: the dataset authors' intrinsics (VINS-Fusion config); the
extrinsics from `cv2.stereoCalibrate` on the authors' `calib_stereo.zip`
(132 pairs, 9×6 at 80 mm, intrinsics fixed, RMS 0.359 px): right camera
0.2593 m along +x of the left, 1.16°. The VINS-Fusion `body_T_cam`
reverse the rig (95–97 % negative disparity on real pairs).

The streaming sidecar now resets lost odometry after one frame
(`Odom/ResetCountdown=1`); RTAB-Map's default 0 never recovers and lost
the last ~140 s of this flight.

Verification: gates green (pytest 576 passed, 2 skipped); EuRoC
real-container e2e green. Against the Leica ground truth (first 1,500
frames, rigid alignment): ATE 2.12 m, best-fit scale 0.96; whole flight
tracked (0 of 3,325 frames lost) with detections person 1586, truck 80,
car 68.
