# Camera indicator on the live floor plan

**Date:** 2026-10-30
**Feature:** browser demo

Each live frame event carries `camera` — the shown frame's position on
the floor plane, its optical axis projected there, and the display's
horizontal field of view (`2·atan(width / 2 / fx)`) — or null without
odometry or SLAM. The page redraws the floor plan with every frame,
marking the camera with a dot and a field-of-view wedge, so the marker
moves in step with the video.

Verification: gates green (pytest 568 passed, 2 skipped); heading
confirmed in the browser on NTU VIRAL sbs_01.
