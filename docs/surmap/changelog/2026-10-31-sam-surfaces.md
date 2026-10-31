# SAM surfaces — region points assigned to persistent object surfaces

**Date:** 2026-10-31
**Feature:** Station fusion / browser demo / demo run history

SAM region points (`StreamRegionPoints`, one mask on one frame) now
give objects a lasting shape. `surmap.survey.surfaces.SurfaceMap`
assigns every dense region point to one object *surface*. Identity is
continuation by overlap, not SAM's track id (SAM 3.1 ids restart every
16-frame window). A region's 10 cm match voxels already owned by a
surface vote for it, and the most-voted surface continues when it holds
≥ 20 % of them. Otherwise a new surface starts. A match voxel has one
owner, so points on another surface's voxels stay with it. Within a
surface, points are deduplicated per 2 cm.

Moving objects become smeared surfaces, at the developer's request. A
surface whose region centroid has drifted ≥ 0.4 m from its first
observation is marked moving for good. Its points keep accumulating,
and it is drawn red (α 0.9) over the static surfaces (translucent,
α 0.5, one colour per surface). This departs from architecture §6
layer 3 (moving objects as snapshots) for the display layer only.
Nothing is written into RTAB-Map's map. Known limit: an object that
moves more than its own overlap per frame never continues a surface.
Using SAM's in-window track id as a continuation hint would close it.

In the demo, each `region` event is followed by a `surface` event (per
region: surface id, label, track id, `continued`, `moving`, the newly
assigned points, the surface's total). The server draws the surface
layer into the 3D view (`demo/surface_render.py`) and re-renders when
it changes. A Hide/Show surfaces button posts `cloud_surfaces`. The
browser's `cloud_regions` round-trip is removed; it was never wired
into the page, so no region had reached the 3D view before. Surfaces
are persisted per run in `demo-history.db` (`surface_points`, one row
per assignment, with `moving`). A history snapshot carries the
surfaces as they were at its frame, and its `cloud_png` is drawn with
them. `demo/server.py` went from 1819 to 1814 lines.

Verification: gates green (ruff, format, mypy strict, pytest 700
passed / 12 skipped). The rendered page's scripts pass `node --check`.
Live on the real streaming sidecar with the fake SAM:

- **EuRoC V1_01, 120 frames:** 120 region → 119 surface events (the
  last region arrives after the sidecar closed). 118 of 119 continued
  surface 1, and new points per frame fell from 4127 to about 500 as
  voxels filled (30 817 points). The surface stays static and is drawn
  translucent over the cloud.
- **KITTI 0009, 60 frames:** 60 separate static surfaces and no
  continuation. The centred box hits a new patch of road every frame.

The red smear is proven by the acceptance and render tests, not by a
live moving object. Real SAM 3.1 objects on the GPU are not verified.
