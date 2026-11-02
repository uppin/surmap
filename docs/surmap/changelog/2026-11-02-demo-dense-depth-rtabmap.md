# Demo dense depth is RTAB-Map's; the sidecar's disparity reaches the frame edge

**Date:** 2026-11-02
**Feature:** browser demo (dev console) / streaming sidecar

**Dense depth from RTAB-Map.** The video's Dense depth overlay used to
match the display pair again with the numpy block matcher
(`GET /dense-depth?dataset=&t_ns=`). On KITTI 0009 its median depth error
against the sidecar's SGBM was 40–85 %, it disagreed with the SAM pane,
and the page sent `t_ns` as a JSON double, so 429/447 KITTI and every
EuRoC frame were a 404. Now `GET /runs/<run_id>/dense-depth?frame_id=<n>`
paints the disparity RTAB-Map's sidecar journalled for that frame (a
replay reads its recording's), read per display pixel by
`surmap.slam.dense.display_depth` with the region geometry. A frame
without a dense buffer (only SAM frames have one) says so; nothing is
matched in its place. `StereoReconstructor.depth_map` is removed.

**No flashing.** With Dense depth on, the page keeps the previous frame
on screen until the next frame's overlay is in and draws them together.
Overlays and misses are cached per run and frame.

**Full-width disparity.** SGBM left the reference's first
`numDisparities` columns unmatched: 128 of KITTI's 620 (the frame's
widest disparity is 34 px). `fullFrameDisparity` now pads both images on
the left by `numDisparities` and crops the result; the left-right check
rejects matches into the padding. Region answers gain the same columns.
Runs recorded before keep the empty band in their journal.

**Rebuild RTAB-Map** (`GET /stream?rebuild_rtabmap=<run_id>`, a page
button): RTAB-Map runs live again over the run's scene while SAM is not
run; each frame gets its recorded masks (`surmap.demo.sam_journal`, by
`t_ns`). The result is a new recording that becomes the scene's cached
run.

Verification: gates green (pytest 1340 passed, 7 skipped); streaming
real-container e2e 11 passed on the rebuilt image, its two new
edge-band tests red before. KITTI `acdcc6aa` rebuilt as `4f0e962f`
(447 frames, 447 recorded SAM results): left 128 columns 0 % → 82 %
matched, rest 90 %; frames 120 and 200 overlays checked by eye.
