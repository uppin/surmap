# Demo object feed, car-shaped surfaces, working 3D pane - PRD

**Date**: 2026-11-02
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Dev console (`scripts/demo.py`, README § Dev console): a new
  object feed, plus a 3D pane that responds to pan, tilt and zoom at all times
- **Related Feature**: SAM surfaces (`docs/architecture.md` §6, `surmap.survey.surfaces`):
  regions are depth-banded and need enough points before they start or continue a surface

## Summary

The console lists every detected object (surface) in a feed. Each card has its own 3D
preview that the viewer pans, tilts and zooms. Object surfaces become the shape of the
object instead of a smear along the viewing ray. The main 3D pane moves with the mouse
and trackpad, including after the run has finished.

## Background

On KITTI 0009 (`car`), car surfaces stretch 5–10 m away from the camera and parked cars
are drawn red as moving. Masks with a handful of depth points start surfaces of their
own. The 3D pane ignores drags once a run ends, and only partly follows them while one
plays.

## Proposed Changes

### What's Changing

1. **Depth band.** A region keeps only the points within `depth_band_m` (default 1.5 m)
   of its median range from the camera that saw it.
2. **Minimum depth.** A region with fewer than `min_points` (default 50) points after the
   band neither starts nor continues a surface. That object becomes a surface on the
   first later frame with enough depth.
3. **Object feed.** A feed under the 3D pane: one card per surface, with its label and
   id, point count, static or moving, first and last frame, and a client-side 3D preview
   with drag to orbit, Shift+drag to pan, wheel or pinch to zoom, and the same ◀ ▶ ▲ ▼ + −
   buttons. It fills from live, replayed and cached runs and follows the timeline when a
   moment is scrubbed.
4. **3D pane PTZ.**
   - The pose belongs to the console session, not to a run, so it survives a new run.
   - Every PTZ action is accepted with or without a run playing, and answers with the
     cloud re-rendered under the new pose. A finished run, a scrubbed moment and a
     cached rerun all move immediately.
   - A drag sends its whole movement.
5. **Dense points on the SAM preview.** Over each SAM mask, the SAM pane draws the dense
   points that object keeps (after the depth band), at their image pixels. Each point is
   coloured on a near-to-far gradient over that object's own depth range, and the
   object's label shows the range (for example `car #8 · 4.1–6.3 m`). Live runs and
   replays have it. A scrubbed moment shows masks only.

6. **Picking in the 3D pane.** Hovering a surface's points shows its id and label and
   selects (highlights) all of that surface's points. Clicking it scrolls the feed to that
   object's card and highlights it. Hovering a card selects its surface in the pane.
7. **The SAM view in the same selection.** Hovering a SAM mask selects its object's points
   in 3D, and clicking it opens its feed card. Hovering an object in 3D (or its card)
   outlines its masks in the SAM view.

### What's Staying the Same

- The main 3D pane stays server-rendered from every map point.
- Regions stay a read-only layer. Nothing is written to RTAB-Map.
- Moving detection keeps its 0.4 m threshold.
- Recorded surfaces in old runs' history are not rewritten. A replay recomputes them.

## Impact Analysis

### Technical Impact

`SurfaceMap.assign` takes an optional camera position. `RegionResult` and the `region`
event carry it. The PTZ state moves from `PlaybackControls` to a session-level viewer,
and the feed script is a new module spliced into the page.

### User Impact

Car surfaces are car-sized. Fewer false "moving" objects and fewer one-point objects.
The 3D pane is usable after a run. A feed to browse objects one at a time.

## Implementation Plan

See the changeset [2026-11-02-demo-object-feed.md](./2026-11-02-demo-object-feed.md).

## Acceptance Criteria

1. A region whose points include a tail along the view ray yields a surface without the tail.
2. A region with fewer than 50 points after the band yields no surface, and doesn't grow one.
3. A later region with enough points starts that surface.
4. `cloud_orbit` after the run finished answers 200 with a re-rendered `cloud_png`.
5. A pose set in one run is the pose of the next.
6. The page carries the object feed, fed by `surface` events and snapshot surfaces.
7. A `region` event carries, per region, the banded points' display pixels and range, sampled to at most 1500.
9. Hovering a surface in the 3D pane shows `label #id` and highlights all its points; clicking it brings its feed card into view.
10. Hovering a SAM mask lights up its surface in 3D, and clicking it brings its feed card into view. Hovering a surface in 3D outlines its SAM masks.
11. On KITTI 0009 in a browser: car-sized surfaces, a feed card per surface whose preview
   orbits, depth-coloured dense points on each SAM mask, and a 3D pane that follows drags after the run ends.

## References

### Affected Features (Complete List)

- README.md § Dev console
- docs/architecture.md §6 (SAM surface layer)

### Related Documentation

- docs/surmap/changelog/2026-10-31-sam-surfaces.md
