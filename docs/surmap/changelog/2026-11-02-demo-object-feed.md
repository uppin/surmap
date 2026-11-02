# Demo object feed, car-shaped surfaces, Follow, and one selection across 3D, SAM and the feed

**Date:** 2026-11-02
**Feature:** SAM surfaces / browser demo (dev console) / demo run history

On KITTI 0009 car surfaces stretched 5–10 m along the viewing ray, parked
cars turned red as "moving", and masks with one to five depth points
became surfaces. A mask's edge pixels match the background behind the
car, and at KITTI's fx ≈ 362 px, b = 0.54 m one disparity pixel is metres
at 15–30 m.

**Surfaces.** A region now carries the camera that placed it
(`RegionResult.camera`: the dense buffer's `to_map`, or the live dense
line the sidecar sends before its answer). The surface layer keeps only
the points within 1.5 m of the region's median range from that camera
(`surfaces.object_points`). A dense demo region needs 50 of them
(`DENSE_REGION_MIN_POINTS`) to start or continue a surface;
`SurfaceMap`'s default stays one point for the mission's sparse hits.
Replaying `38b8dc54`: 42 → 28 surfaces, the smallest 1 → 275 points, car
surfaces ≈ 1.5 × 1.1 × 2.5–3.8 m, moving 3 → 2 (the two left are cars
driven right past, a known partial-view limit). A rewound moment of a
journalled run is recomputed from its journal (`demo/surface_timeline.py`,
once per run), so it shows today's logic, not the recording's.

**3D pane.** Its state is the console session's (`demo/cloud_view.py`
`CloudViewer`), not a run's:
- Every pan/tilt/zoom answers with a fresh render, also after the run has
  ended. It used to answer `409 nothing is playing`.
- A drag sends its whole movement, and ctrl+wheel pinches.
- The pose readout and the surfaces button update again. They had been
  broken by a block-scoped `const`.
- **Follow** (on by default) frames the view behind and above the shown
  frame's camera along its heading, with the camera at 3/4 of the image
  height; a yellow arrow marks it.
- The projection was mirrored, (x, −y, z) being left-handed, and is now
  the right way round.
- Each render comes with an id image (`cloud_ids_png`), so hovering a
  surface names it and selects all its pixels, and a click opens it in the
  feed.

**Object feed** (`demo/object_feed.py`): one card per surface with its own
client-side 3D preview.

**SAM pane** (`demo/sam_depth.py`):
- Each mask shows its object's own dense points, coloured near → far.
- Each object has a card next to it: cyan with its surface id, or grey
  with SAM's track id while it has too few depth points. Cards never
  overlap, and each is joined to its object by a leader with filled
  circle ends.
- Hovering a mask or card selects the object in 3D and the feed, and a
  surface selected anywhere is outlined there.

Verification:
- Gates green: ruff, format, mypy strict, and pytest 1255 passed / 28
  skipped. JS helpers and the PTZ readout are exercised in node.
- In the in-app browser on KITTI 0009, with real CDP mouse events:
  - a drag after the run turned the view by its full amount;
  - hover, click and card hover linked 3D, SAM and the feed;
  - Follow tracked the camera 16 m along the road and handed over to a
    drag without a jump;
  - 13 SAM cards, none overlapping, nine within 4 px of their object;
  - no page errors.
