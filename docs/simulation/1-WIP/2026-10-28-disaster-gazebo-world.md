# Changeset: Disaster-response Gazebo world

**Date**: 2026-10-28
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — one package (`surmap.simulation`) plus SDF/JSON/plan assets, integration-style file tests, no flight interface

## Workflow

- [wf 1] ✅ 2026-10-28 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Geodetic anchor, survivor poses, road kinds
  - [ ] SDF poses match ground truth; textures resolve
  - [ ] Survey plan is a 12 m lawnmower; launch script does not fly
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `surmap.simulation.disaster_world` loads ground truth, poses, and the plan
  - [ ] `disaster_block.sdf` scene, ground-truth JSON, QGC plan, procedural textures
  - [ ] `scripts/launch_disaster_sitl.sh` symlinks the world and starts stereo SITL
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/disaster-world.md` — scene, licences, ground truth, WSL2 launch
  - [ ] `docs/simulation/px4-sitl.md` — pointer at the disaster world
  - [ ] `docs/architecture.md` §2.3 and §4.3 — world and scoring ground truth
  - [ ] `docs/simulation/changelog/2026-10-28-disaster-world.md`
  - [ ] `1-WIP` removed
  - [ ] (optional) Test-quality pass — run if new tests land
  - [ ] (optional) Production readiness — run if a new public loader lands

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-10-28-disaster-gazebo-world-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## Prerequisites

### Deferred TODOs

| Item | Verdict | Disposition | Outcome |
|---|---|---|---|
| `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md` | — Unrelated | GPS on the live survey wire. This change only writes a world-frame and WGS84 scoring file. | |

### Code Issues

Scanned for `src/surmap/docs/code-issues/` and `docs/simulation/**/code-issues/`. Neither directory exists on `feat/PX4_sitl`.

## Stack Context

**Stack**: PX4 SITL simulation · this PR is **2 of 2** · [#18](https://github.com/uppin/surmap/pull/18)
**Branch**: `cursor/disaster-gazebo-world-6e61` · **Base**: `feat/PX4_sitl`
**Successor**: none — top of stack.
**Kind**: Feature · behaviour-adds — the `(Type, Behaviour)` pair from the header
**Workflow**: preset `feature` · planned by `/plan-red` · pass-2 = failing acceptance tests — the rows themselves are this changeset's `## Workflow`

Why the boundary falls here: PR #18 owns the stereo model, the capture dump, and the EuRoC export. This PR only adds a world the existing airframe can be spawned into, plus scoring data and an operator plan. It does not change capture, calibration, or export.

### Owned API surface

- `surmap.simulation.disaster_world` — ground-truth load, WGS84 conversion, SDF pose read, survey-plan load
- `docs/simulation/gz/worlds/disaster_block.sdf` and `disaster_block_materials/`
- `docs/simulation/gz/worlds/disaster_block_ground_truth.json`
- `docs/simulation/gz/worlds/disaster_block_survey.plan`
- `scripts/launch_disaster_sitl.sh`
- `docs/simulation/disaster-world.md`

### Green wave

**Wave:** 2 of 2
**Node:** n2
**Concurrent with:** none — this node is alone in its wave
**Blocks:** nothing

Real dependency edges:

    n1 (PR #18, stereo SITL bridge) → n2 (this world)

**Greenable independently?** yes — tests parse files in this repo. They do not launch Gazebo or PX4. The predecessor's stereo SDF is used only by the operator launch command, which this PR does not execute in CI.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `surmap.simulation` EuRoC export, `sitl_capture`, `sitl_dump` | PR #18 | implemented on `feat/PX4_sitl` | does not modify them |
| `docs/simulation/gz/x500_surmap_stereo`, `surmap_stereo_cam` | PR #18 | implemented | launch script symlinks the existing model; no SDF edit |
| `scripts/export_sitl_session.py`, `scripts/ros2/dump_sitl_capture.py` | PR #18 | implemented | not invoked and not changed |

**Greenable independently?** yes.

## Affected Packages

- **surmap**: [docs/architecture.md](../../../architecture.md) — §2.3 / §4.3 name the disaster world and its scoring file
  - [docs/simulation/px4-sitl.md](../px4-sitl.md) — pointer to the world runbook
  - [docs/simulation/disaster-world.md](../disaster-world.md) — new operator runbook (created at wrap, not linked while this file is in `1-WIP`)

## Related Feature Documentation

- [PRD](./PRD-2026-10-28-disaster-gazebo-world.md)

## Summary

Add a fictional civilian earthquake-and-flood Gazebo Harmonic block, a ground-truth JSON of people and roads in map ENU and WGS84, a 12 m lawnmower QGroundControl plan, and one launch command that starts the existing stereo airframe in that world.

## Background

The hackathon demo needs the simulated drone to fly over a search-and-rescue scene so stereo, detection, and SAM have texture, people, and blocked roads to score. PR #18 can record whatever world PX4 loads, but the only worlds it knows are PX4's. SurMap stays a passive payload: the plan is a file the operator uploads, and the launch script does not arm or command the vehicle.

## Scope

- Harmonic world `disaster_block` built from original SDF primitives and original procedural textures (no Fuel download at launch)
- Intact and partly collapsed buildings, rubble, tilted slabs, blocked and clear roads, a flooded avenue section, parked and overturned cars, standing / lying / waving figures
- Ground-truth JSON: map ENU plus lat/lon from the world's spherical coordinates (the PX4 SITL anchor)
- QGC plan covering the block at 12 m AGL and 4 m/s
- Launch script and WSL2 / WSLg instructions
- Tests that lock the geodetic conversion, poses, and plan without running Gazebo

## Technical Changes

### State A

- `surmap.simulation` converts a capture directory to EuRoC. It has no world, no geodetic helper, and no ground truth.
- PX4 SITL spawns `x500_surmap_stereo` into `default` unless `PX4_GZ_WORLD` names a file under `Tools/simulation/gz/worlds`.
- The stereo cameras look along the body +X axis. Survey altitude has to account for that.
- Architecture §2.3 records the Gazebo path and points at `px4-sitl.md` only.

### State B

- `docs/simulation/gz/worlds/disaster_block.sdf` is a static Harmonic world (`sdf` 1.9), name `disaster_block`, physics and magnetic field copied from PX4 `default.sdf`, spherical coordinates equal to that anchor (latitude 47.397971057728974, longitude 8.546163739800146, elevation 488, ENU, heading 0).
- Scene content, all original geometry: four urban quadrants (intact two-storey, partial collapse, low intact, rubble field), avenue and cross street, flood water, debris and fallen poles, four cars (one on its side), six humanoid figures in high-visibility colours. Sun light with shadows; diffuse colours set so a missing texture still reads. Albedo maps live in `disaster_block_materials/` and are original procedural PNGs.
- `disaster_block_ground_truth.json` lists each person (`standing`, `lying`, `waving`) and each scored road (`passable`, `flooded`, `blocked`) with map ENU metres and WGS84 lat/lon/alt. `surmap.simulation.disaster_world` loads it, checks the fixes against the anchor, and reads model poses out of the SDF.
- `disaster_block_survey.plan` is a QGC plan: takeoff, lawnmower waypoints at 12 m relative, RTL. Cruise speed 4 m/s. Yaw is left unset so PX4 faces the next waypoint and the forward cameras look along the leg.
- `scripts/launch_disaster_sitl.sh` exports the resource path, symlinks the stereo model, the world file, and the materials directory into the PX4 tree, and execs `PX4_GZ_WORLD=disaster_block PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500`. It does not set `HEADLESS`, so PX4 starts `gz sim -g` for WSLg.
- `docs/simulation/disaster-world.md` records licences, the scoring frame, and the WSL2 commands. Architecture and `px4-sitl.md` point at it.

### Delta

- New module, three world assets, one launch script, tests, and the runbook above.
- No change to the stereo model, the dumper, or the exporter.
- No actuator, setpoint, or mission upload API.

## Verification

**Method:** V1, fail→pass — acceptance tests for the scoring frame, SDF placement, and the survey plan
**Command:** `uv run pytest -q tests/test_disaster_world.py`
**Before:** module `surmap.simulation.disaster_world` missing; collection fails on import
**After:** the test module passes, including the 100 m north/east anchor literals, the six survivors and five road segments, static SDF poses, texture paths, the 12 m lawnmower, and a launch script with no flight commands

Full `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy`, and `uv run pytest -q` stay green. Gazebo is not on this VM; SDF well-formedness is the XML parse in the test. A `gz sdf -k` or headless screenshot is recorded here only if the tool actually runs.

## Testing Plan

### Testing Strategy

**Primary Test Approach:** unit tests over the public loader and the checked-in SDF, JSON, and plan. Gazebo is not a CI dependency.

### Testing Options Analysis

#### Option 1: File-level acceptance tests

**Test Level**: Unit
**Description**: Load the ground truth and the plan, parse the SDF, compare poses and geodetic fixes.

**Scope**:
- WGS84 offset of the PX4 anchor (independent numeric literals)
- Survivor ids, poses, and map points
- Passable, flooded, and blocked roads
- Every scored model static at that pose
- Albedo files exist beside the world
- Lawn-mower waypoint grid, altitude, speed, RTL
- Launch script text does not arm or upload a mission

**Assertions**:
- **100 m north** latitude is 47.398870511394634 and longitude is unchanged
- **Each scored model** xyz and yaw match the JSON within 1 mm / 1 mrad
- **Each waypoint** is within 5 cm of the contracted ENU grid at 12 m

#### Option 2: Launch Gazebo in CI

**Test Level**: E2E
**Description**: `gz sim -s` the world and grab a frame.

**Why not**: this VM has no `gz`, and CI does not install Harmonic. The operator runbook carries the manual launch. Not chosen.

## Acceptance Tests

- `tests/test_disaster_world.py` — the behaviours in the testing plan

## Decisions & Trade-offs

- **Primitives instead of Fuel.** Fuel person and collapsed-building meshes look more photographic, but they download at runtime and the names are easy to get wrong offline. Original primitives with procedural albedo maps launch with no network. High-visibility clothing and facade windows are there so a detector and SAM still have contrast.
- **PX4 anchor, fictional scene.** Moving the home latitude would also require a matching magnetic field. Keeping Zurich's SITL anchor avoids an EKF compass surprise. The docs say the block is not a real place.
- **12 m and a forward camera.** The stereo rig looks along +X. At 12 m the ground enters the frame about 20 m ahead, and 8 m roofs are cleared by 4 m. A higher lawnmower would mostly see sky.
- **Plan file, not a mission publisher.** Architecture §1 forbids flight commands in SurMap. QGroundControl uploads the plan.
- **Spawn stays at the origin.** The helipad is visual-only so contact matches PX4's default ground plane.

## Refactoring Needed

None at planning time. The new module is a loader, not a split of an existing file.

## Validation Results

*(filled when the gates run)*

## References

- [docs/simulation/px4-sitl.md](../px4-sitl.md)
- [docs/architecture.md](../../../architecture.md) §1, §2.3, §4.3
- PX4 `px4-rc.gzsim` and `PX4-gazebo-models/worlds/default.sdf` (anchor and physics)
- PR #18
