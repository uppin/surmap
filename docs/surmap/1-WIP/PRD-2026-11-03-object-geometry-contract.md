# Object 3D contract for agents - PRD

**Date**: 2026-11-03
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Survey agent (new, `docs/agent.md` created at wrap) — how an agent sees a
  detected object's 3D reconstruction
- **Related Feature**: [Semantic map snapshot](../../semantic-map-snapshot.md) — the frame and
  units conventions this contract states explicitly

## Summary

Give every detected object a compact, LLM-friendly 3D description that works for point clouds today
and polygonal surfaces later without changing its shape: an always-present summary, an on-request
quantised OBJ text block, and a GLB file for viewers and other tools.

## Background

LLMs reason far better over per-object summaries (centre, oriented box, extents, relations) than over
raw coordinates (ConceptGraphs, SceneGPT, LLM-Grounder). When geometry is needed in context, OBJ text
with quantised integer coordinates is the representation models are trained on (LLaMA-Mesh,
MeshLLM). GLB (glTF 2.0) carries points (mode POINTS) now and triangles later, and three.js loads it
natively. Sources are listed in the changeset's discovery companion.

## Proposed Changes

### What's Changing

- `surmap.objects3d.summary` — `ObjectSummary`: id, label, confidence, frame, up axis, units,
  point/face counts, centroid, AABB, OBB (centre, extents, rotation from PCA), height, footprint
  area, shape class (`linear | planar | volumetric` from PCA eigenvalue ratios), observed frames and
  time span, neighbours (id, distance, relation `above | below | next_to | overlaps`), and
  `geometry_uri`. `summarize(...)` and `neighbours(...)` compute it from an Nx3 array (and faces
  when present).
- `surmap.objects3d.obj_text` — `surmap-obj v1` encoder: header comments (id, label, frame, unit,
  origin in metres, scale, counts, `decimated from N`), `v x y z [r g b]` in integer centimetres
  relative to the OBB centre, `f a b c` for faces; voxel downsampling (default 5 cm) then a cap
  (default 500 points / 1,000 faces) with deterministic decimation. A decoder for round-trip tests.
- `surmap.objects3d.glb` — GLB writer: POINTS primitive with `POSITION` (float32, map metres) and
  optional `COLOR_0`; TRIANGLES when faces are given; frame and up axis in `asset.extras`.

### What's Staying the Same

- `survey/surfaces.py` and every stored point set; no new dependency (numpy only).

## Impact Analysis

### Technical Impact

A new pure library; no existing caller.

### User Impact

None directly; the agent's `get_object` / `get_object_geometry` tools (n7) return these.

## Implementation Plan

See the changeset `2026-11-03-object-geometry-contract.md`.

## Acceptance Criteria

1. A box-shaped point set summarises to the right centroid, extents (±1 cm), yaw and
   `volumetric`; a flat set is `planar`; a pole is `linear`.
2. The OBJ text of a 14,000-point cloud has at most 500 `v` lines, a `# decimated from 14000`
   header, and decodes back within 1 cm of the decimated points.
3. A mesh input adds `f` lines with 1-based indices; the same decoder reads it.
4. The GLB parses as glTF 2.0 (magic, version 2, JSON + BIN chunks), with mode 0 for points and
   mode 4 for triangles, and the accessor min/max equal the AABB.
5. Neighbour relations: an object resting on another reads `above`, side by side reads `next_to`.

## References

### Affected Features (Complete List)

- Survey agent (new)

### Related Documentation

- `docs/semantic-map-snapshot.md`, `docs/mask-cloud.md`
