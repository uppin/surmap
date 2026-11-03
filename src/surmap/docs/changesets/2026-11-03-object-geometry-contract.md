# Object 3D contract for agents (`surmap.objects3d`)

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap

New `surmap.objects3d` package gives every detected object a compact 3D description that an
agent can read: `summarize` and `neighbours` produce an `ObjectSummary` (centroid, AABB, PCA
oriented box, height and convex-hull footprint along the stated up axis, `linear | planar |
volumetric` shape, neighbour relations `above | below | next_to | overlaps`);
`encode_obj_text` / `decode_obj_text` write and read `surmap-obj v1`, an OBJ-style block in
integer centimetres from the box centre, voxel-downsampled (5 cm) and capped at 500 points and
1,000 faces; `write_glb` / `read_glb_header` write and check a dependency-free GLB (POINTS now,
TRIANGLES with faces). Every output names its `frame` and `up_axis`, because the demo map is y-down
and ENU snapshots are z-up. Additive library with no caller yet; the agent's object tools use it.

Contract and grammar are in `docs/agent.md` (Object 3D contract).

Tests: 46 in `tests/test_objects3d_summary.py` and `tests/test_objects3d_codec.py`, with builders
in `tests/object_fakes.py`. Full suite 1399 passed, 29 skipped; ruff, ruff format and strict mypy
clean.
