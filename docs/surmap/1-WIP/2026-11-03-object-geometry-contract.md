# Changeset: Object 3D contract — summary, `surmap-obj` text and GLB

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package, numpy-only pure functions, unit tests

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery (commit 1, `e98dc5f`)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 46 failing — commit 2
  - [x] Create failing acceptance tests
  - [x] Run acceptance tests (verify they fail)
  - [x] TDD Red — write failing unit/integration tests
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 46/46 green (`uv run pytest -q tests/test_objects3d.py`) — commit 3; typing fix in the red test at line 177 in commit 4; gates: ruff format, ruff check and mypy pass
  - [x] Milestone 1: `summarize` — centroid, AABB, PCA OBB, height, footprint, shape class
  - [x] Milestone 2: `neighbours` — distance and relation between summaries
  - [x] Milestone 3: `encode_obj_text` / `decode_obj_text` with voxel downsampling and cap
  - [x] Milestone 4: `write_glb` for points and triangles
  - [x] Acceptance: `tests/test_objects3d.py` passes
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/agent.md` — add "Object 3D contract" section (summary fields, `surmap-obj v1` grammar with an example, GLB layout); create the file if n1 has not landed yet
  - [ ] `docs/surmap/changelog/2026-11-03-object-geometry-contract.md` — write changelog entry
  - [ ] Validate tests (`/validate-tests`)

## Initial Discovery

Full codebase exploration that grounded this plan:
[2026-11-03-object-geometry-contract-initial-discovery.md](./2026-11-03-object-geometry-contract-initial-discovery.md).

## Stack Context

**Stack**: survey agent · slug **`#survey-agent`** — this PR is **3 of 9** · [#79](https://github.com/uppin/surmap/pull/79)
**Branch**: `pr-3-survey-agent` · **Base**: `pr-2-survey-agent`
**Successor**: `pr-4-survey-agent`
**Kind**: Feature · behaviour-adds
**Workflow**: preset `feature` · planned by `/plan-pr-stack` · pass-2 = owned stubs + failing acceptance and unit tests

Why the boundary falls here: the 3D contract is pure geometry with no dependency on the agent or the
demo; tools (n7) and the UI's preview (n9) consume it. Keeping it apart lets the mesh extension
later change one module.

### Owned API surface

- `surmap.objects3d.summary`: `ObjectSummary`, `Obb`, `Neighbour`, `ShapeClass`, `summarize`, `neighbours`
- `surmap.objects3d.obj_text`: `encode_obj_text`, `decode_obj_text`, `ObjTextLimits`
- `surmap.objects3d.glb`: `write_glb`, `read_glb_header` (test helper for chunk layout)

### Green wave

**Wave:** 1 of 4
**Node:** n3
**Concurrent with:** n1, n2, n4, n5, n6
**Blocks:** n7 (`get_object` returns `ObjectSummary`; `get_object_geometry` returns OBJ text and a GLB URI)

Real dependency edges, as opposed to the branch line:

    n1 → n7, n8        n1 ⇢ n4, n9 (compile only)
    n2 → n7    n3 → n7    n4 → n8    n5 → n8    n7 → n8    n6 → n9    n8 → n9

### Greenable independently?

**yes** — it owns everything its tests drive.

### Trunk-merge safety

**When this PR merges alone:** additive library, no caller; `uv run pytest -q` and every demo
unchanged. **Local dev data:** no. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| none | — | — | this node uses nothing from n1 or n2 |

**Greenable independently?** yes.

## Inherited Restructure — expect rewrite

n2 (`pr-2-survey-agent`) moves the demo run engine. This node touches no demo file, so no fallout is
expected; the section exists so a rebase conflict here is read as a mistake, not as expected.

## Affected Packages

- **surmap** (`src/surmap`): new `surmap.objects3d` package.

## Related Feature Documentation

- PRD: [PRD-2026-11-03-object-geometry-contract.md](./PRD-2026-11-03-object-geometry-contract.md)

## Summary

Three pure modules: a summary every tool result carries, an OBJ-style text the model can read when it
asks for geometry, and a GLB the viewer loads. Points now; faces are an optional argument that every
function already accepts.

## Background

See the PRD. The demo's live map is RTAB-Map y-down (`demo/cloud_view.py:6-8`) and the mission
snapshot is ENU z-up, so every output names its `frame` and `up_axis`; the summary's height and
footprint are computed along the stated up axis.

## Scope

- Summary, neighbours, OBJ text encode/decode, GLB writer
- **Out of scope:** mesh reconstruction (no surface code exists), multi-view renders, CityJSON export

## Technical Changes

### State A (Current)

`survey/surfaces.py:91 Surface(surface_id, label, points: NDArray[float32] Nx3, moving)`; 2D hulls
only (`moving/areas.py:84`). `surmap.geometry` holds pose helpers and `centroid`. No 3D export.

### State B (Target)

```python
@dataclass(frozen=True)
class ObjectSummary:
    id: str; label: str; confidence: float | None
    frame: str; up_axis: Literal["+y", "-y", "+z"]; units: Literal["m"]
    n_points: int; n_faces: int
    centroid: tuple[float, float, float]
    aabb_min: tuple[float, float, float]; aabb_max: tuple[float, float, float]
    obb: Obb                                  # centre, extents, rotation (3x3, PCA axes)
    height_m: float; footprint_m2: float; shape: ShapeClass
    observed_frames: int; t_first_ns: int | None; t_last_ns: int | None
    neighbours: tuple[Neighbour, ...]
    geometry_uri: str | None

def summarize(id: str, label: str, points: NDArray[np.float32], *, frame: str, up_axis: ...,
              faces: NDArray[np.int32] | None = None, ...) -> ObjectSummary
def encode_obj_text(summary: ObjectSummary, points, *, faces=None, colors=None,
                    limits: ObjTextLimits = ObjTextLimits()) -> str
def write_glb(points, *, colors=None, faces=None, frame: str, up_axis: str) -> bytes
```

```text
# surmap-obj v1 id=obj_17 label=car frame=map up=-y unit=cm
# origin_m=412.35,-88.10,2.04 scale=0.01 points=500 (decimated from 14211)
v -226 -90 -74 158 156 153
f 1 2 3
```

### Delta (What's Changing)

#### surmap

- `src/surmap/objects3d/{__init__,summary,obj_text,glb}.py` (new)

## Verification

**Method:** V1 — fail→pass unit and acceptance tests
**Command:** `uv run pytest -q tests/test_objects3d.py`
**Before:** red — stubs raise `NotImplementedError`
**After:** green

## Testing Plan

Synthetic numpy fixtures only: an axis-aligned box rotated by a known yaw, a plane, a pole, two
stacked boxes, a 14,000-point noisy box for decimation, a two-triangle mesh. GLB verified by parsing
its header, JSON chunk and BIN length.

## Acceptance Tests

### surmap

- `tests/test_objects3d.py`
  - a rotated box summarises to its centroid, extents (±1 cm), yaw (±1°) and `volumetric`
  - a plane is `planar`, a pole is `linear`
  - height and footprint follow the stated up axis (`-y` for the demo map)
  - 14,000 points encode to ≤ 500 `v` lines with `decimated from 14000`, and decode within 1 cm
  - faces encode as 1-based `f` lines
  - GLB has glTF magic, version 2, mode 0 for points / 4 for triangles, accessor min/max = AABB
  - a box resting on another reads `above`; side by side reads `next_to`

## Decisions & Trade-offs

- **Package name `objects3d`**, because `surmap.geometry` already exists for pose helpers.
- **Integer centimetres relative to the OBB centre**, not LLaMA-Mesh's [0,64] grid: the agent needs
  real dimensions, and cm keep a car's coordinates in three digits.
- **Deterministic decimation** (voxel, then a strided pick sorted by voxel key) so tool results are
  reproducible in tests; Poisson-disk can replace it behind the same limits later.
- **No `pygltflib`** — GLB for points and triangles is ~80 lines of struct packing; no new dependency.
- **Red step (commit 2)** — `tests/test_objects3d.py`, 46 tests, every one failing on this node's
  own `NotImplementedError` (25 `summary`, 14 `obj_text`, 7 `glb`); none drives a predecessor stub.
  Known-red on this branch and not this node's: n1's 32 red tests (`tests/test_agent_contracts.py`,
  `tests/test_agent_services.py`) and `tests/test_survey_cm5_rtabmap_e2e.py::test_euroc_pairs_stream_real_rtabmap_poses_and_points`
  (a real-RTAB-Map timeout, red on `origin/main` too).
- **Contract details the stubs fix** — `Obb.extents` are half-lengths, largest first; `Obb.rotation`
  is row-major box→frame (column *i* is box axis *i*); `Neighbour.relation` is where the neighbour
  sits relative to the summarised object (the proto's reading), `distance_m` the AABB gap.
  Added real types beyond the planned surface: `Relation`, `UpAxis`, `DecodedObj` (decoder result,
  points in frame metres, faces 0-based) and `GlbHeader` (what `read_glb_header` returns).
- **Proto alignment (n1's `ObjectSummary` message)** — field names match one-for-one. Differences
  n7's converter maps: `Obb` ↔ `OrientedBox` (rotation 3x3 tuple ↔ 9 repeated doubles);
  `ShapeClass` ↔ `Shape` and `Relation` ↔ `Relation` (no `*_UNSPECIFIED` here);
  `confidence`, `t_first_ns`, `t_last_ns`, `geometry_uri` are `None`-able here but plain scalars
  in proto3 (None → 0 / "").
- **Typing fix in the red test (commit 4)** — `tests/test_objects3d.py:177` called `.max()` with no
  argument on a numpy array, which the strict mypy stubs reject. It is now `np.max(...)` on the same
  array: same value, same assertion, no test weakened. Supervisor-approved; the only edit to a red-step test.
