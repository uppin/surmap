# Initial Discovery: Project SAM masks onto the cloud

**Changeset**: [2026-10-28-mask-cloud.md](./2026-10-28-mask-cloud.md)
**Date**: 2026-10-28
**Passes**: 1

## Combined Conclusions

State A has no mask-to-cloud function. SAM polygons already exist as
`SamDetection.mask_polygon` (frame pixels). Camera-frame clouds already
exist as `tuple[Vec3, ...]` from `StereoReconstructor.reconstruct`. The
pinhole projection used for boxes (`fx * x / z + cx`, `fy * y / z + cy`)
and the `z <= 0.05` drop live in `CoralObjectPointSource` and
`project_overlay`. Map-frame conversion is `surmap.geometry.to_map_frame`.
Nothing writes object points back into RTAB-Map.

This change adds `points_in_mask` in `src/surmap/survey/mask_cloud.py`.
It keeps camera-frame points whose projection lies inside the polygon
and inside the frame `[0, width) × [0, height)`, drops `z <= 0.05`, and
applies `to_map_frame` only when a pose is passed. An empty polygon
returns `()`. No new model, no network, no RTAB-Map write.

Deferred TODOs under `src/surmap/docs/todo/` are moving-object follow-ups
and do not sit on this path. `src/surmap/docs/code-issues/` does not
exist. No package README declares an architecture diagram. `HACKATHON.md`
is not on `main` (it is still the subject of PR #28); this change does
not edit `README.md`.

## Exploration 1: mask projection seam — 2026-10-28

**Agent**: parent Grep/Glob/Read
**Scope**: where SAM polygons, camera points, projection, and map-frame
transforms already live, and whether a mask-cloud module exists.

### Sequence

1. `gh api` comment `6479199252` — the task text.
2. Glob `src/surmap/**/*.py` — survey and geometry modules.
3. Grep `to_map_frame|polygon|z <= 0.05` — existing projection and pose use.
4. Read `src/surmap/geometry.py`, `src/surmap/types.py` — pose transform and `Vec3`.
5. Read `src/surmap/detection/source.py` — box selection and `z <= 0.05`.
6. Read `src/surmap/survey/stereo.py` (`StereoRig`, back-projection) — rig fields.
7. Read `src/surmap/survey/sam.py`, `src/surmap/survey/sam3.py` (`_mask_outline`) — polygon shape.
8. Read `src/surmap/demo/server.py` `project_overlay` — frame bounds on a projection.
9. Read `docs/architecture.md` §4.2 and §5–6 — fuse is design intent, not code.
10. Glob `tests/**/*.py` and `HACKATHON.md` — no mask-cloud test; no hackathon file on this checkout.
11. List `src/surmap/docs/todo/` — moving-object records only. `code-issues/` absent.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Glob | `src/surmap/**/*.py` | repo | `survey/sam.py`, `survey/sam3.py`, `geometry.py`, `detection/source.py`; no `mask_cloud.py` |
| Grep | `to_map_frame\|z <= 0.05\|mask_polygon` | `src` | `detection/source.py:102`, `demo/server.py:65`, `geometry.py:21`, `sam.py:44` |
| Glob | `tests/**/*mask*` | repo | none |
| Glob | `HACKATHON.md` | repo | none on `main` |

### Inspected files

#### `src/surmap/detection/source.py`

**Why**: the existing "points whose projection falls in a 2D region" path.
**Excerpt**:

```python
if point.z <= 0.05:
    continue
projected.append(
    (
        rig.fx * point.x / point.z + rig.cx,
        rig.fy * point.y / point.z + rig.cy,
        point,
    )
)
map_points = tuple(to_map_frame(point, pose) for point in inside)
```

#### `src/surmap/geometry.py`

**Why**: the pose transform the task names.
**Excerpt**:

```python
def to_map_frame(point_camera: Vec3, pose: Pose) -> Vec3:
    """Transform one camera-frame point into the map frame using a pose."""
    r = _rotate(point_camera, pose.orientation_xyzw)
    p = pose.position
    return Vec3(r.x + p.x, r.y + p.y, r.z + p.z)
```

#### `src/surmap/survey/sam.py`

**Why**: the polygon type a SAM mask already produces.
**Excerpt**:

```python
mask_polygon: tuple[tuple[float, float], ...] = ()
```

#### `src/surmap/demo/server.py`

**Why**: how a projection is rejected outside the frame.
**Excerpt**:

```python
if 0.0 <= u < calibration.width and 0.0 <= v < calibration.height:
    visible.append(...)
```

#### `docs/architecture.md`

**Why**: whether fuse is implemented or still a design node.
**Excerpt**:

```text
surmap_fuse | Project SAM masks onto the point cloud using RTAB-Map poses
```

The surrounding section says topic names are design intent. No Python
function performs that projection.

### Findings

- Projection formula and the 5 cm depth gate are already the on-board
  convention. Reuse them; do not invent a second camera model.
- Polygons are closed implicitly (the outline helper does not repeat the
  first vertex). Containment must close the ring.
- `to_map_frame` is exact for an identity quaternion plus a translation,
  which is the acceptance pose.
- Object points are documented as layered onto RTAB-Map, never written
  back. This function returns a tuple and takes no SLAM backend.
- Scope is two new files plus the docs the lifecycle wraps into. No
  server wiring was requested.
