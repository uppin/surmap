# Demo video toggles: RTAB-Map points and dense depth

**Date:** 2026-11-02
**Feature:** browser demo (dev console)

The video pane gets two checkboxes under the frame:

- **RTAB-Map points** (checked by default) shows or hides the tracked
  features drawn on the frame. Detection boxes stay.
- **Dense depth** (unchecked by default) lays the shown frame's dense
  stereo depth over it, at 65 % opacity, in the overlay's near → far
  ramp (`DEPTH_COLOURS` at the scene's `depth_stops_m`). Pixels with no
  left-right consistent match stay transparent.

Either box redraws the shown frame at once, live, paused or rewound.

**Server.** `GET /dense-depth?dataset=<id>&t_ns=<t>` matches that frame's
display pair with the numpy stereo matcher, capped at the scene's map
depth, and answers an RGBA PNG at the display size
(`demo/dense_view.py`); a t_ns the scene has no pair for is a 404. The
matcher's per-pixel depth is now public as
`StereoReconstructor.depth_map`; `reconstruct` samples its points from
it, unchanged. About 300 ms a 376×240 frame on a laptop, so the page
keeps one request in flight (live frames meanwhile are skipped) and the
last 16 overlays. It is a view of the stereo pair only: nothing reaches
RTAB-Map.
