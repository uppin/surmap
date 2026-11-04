# PRD: simulation preview — overview, then FPV with RTAB-Map keypoints

**Date**: 2026-11-04
**Affects**: [docs/simulation/bevy-simulation.md](../bevy-simulation.md), the agent chat's simulation pane
**Changeset**: [2026-11-04-sim-preview-fpv-keypoints.md](2026-11-04-sim-preview-fpv-keypoints.md)

## Problem

The chat's simulation preview embeds the whole Bevy page: header, HUD text, the stereo panel with
its calibration readout and the Take off button all crowd one small frame, and nothing shows what
RTAB-Map makes of the drone's camera.

## Requirements

1. **Only the camera feed.** The preview (`?view=preview`) shows a single view edge to edge: no
   page bezel (the dark header with its title, note and LOCAL POC badge), no hint text, no frame
   padding or border, no stereo panel, no HUD status text, no Take off button.
2. **Overview by default.** While the viewed drone is on the ground the view is the overview: the
   chase camera orbiting the drone, with the trackpad PTZ (scroll pans/tilts, pinch zooms).
3. **FPV when flying.** Once the viewed drone is airborne (a fleet drone out of `Docked`, or the
   keyboard drone engaged) the view switches to the drone's left camera, full frame; it switches
   back to the overview when the drone is docked again.
4. **RTAB-Map points on their own frame.** With the bridge on, the FPV shows the frame RTAB-Map
   processed together with that frame's odometry inlier keypoints (raw pixels, coloured by depth),
   as the demo page does: a frame is held until its odometry arrives, so the view may lag the live
   camera but points never sit on a different frame. Without the bridge, the FPV is the live left
   camera with no points.
5. **The preview is the live page.** The chat's iframe opens the scenario with `view=preview` and
   `fleet=1` (so the agent's fleet commands fly what the preview shows), plus `bridge=<url>` when
   the chat was started with one. "Open simulation" keeps opening the full page.
6. **Starting the bridge locally.** `scripts/dev.sh --bridge` first makes the streaming RTAB-Map
   image ready (`scripts/build_rtabmap_stream.py`: present, or built once per source hash) and
   stops before starting anything when it cannot; then starts the agent with its stereo bridge
   and hands the chat the bridge URL. Without the option nothing changes.

## Out of scope

Keypoints on the full page's stereo panel; a bridge on the Modal deployment.
