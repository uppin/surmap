# Initial Discovery: Disaster-response Gazebo world

**Changeset**: [2026-10-28-disaster-gazebo-world.md](./2026-10-28-disaster-gazebo-world.md)
**Date**: 2026-10-28
**Passes**: 1

## Combined Conclusions

PR #18 (`feat/PX4_sitl`, head `42db14c`) is the Machine 3 bridge: Harmonic stereo models under `docs/simulation/gz/`, a passive capture → EuRoC exporter in `surmap.simulation`, and the WSL runbook `docs/simulation/px4-sitl.md`. It does not ship a world. PX4 launches whatever `${PX4_GZ_WORLDS}/${PX4_GZ_WORLD}.sdf` names, and `gz_env.sh` sets `PX4_GZ_WORLDS` to `Tools/simulation/gz/worlds` inside the PX4 tree (it overwrites a caller export). A SurMap world is therefore a file in this repo plus a symlink into that directory, the same pattern the stereo model already uses for `PX4_GZ_MODELS`.

The world name inside the SDF must equal the filename. PX4's `px4-rc.gzsim` spawns `file://$PX4_GZ_MODELS/$PX4_SIM_MODEL/model.sdf` into `/world/${PX4_GZ_WORLD}/create`. `PX4_SIM_MODEL=x500_surmap_stereo` with airframe `gz_x500` is the spawn that includes the 0.07 m forward-looking stereo rig. The cameras are not pitched down: a level multicopter sees ground only in the lower ~31° of an 80°×63° image, so a survey that is meant to show people has to stay low (about 12 m) and fly along the streets, not at a mapping altitude of tens of metres. Buildings in the block stay at or below 8 m so that altitude clears the roofs.

`default.sdf` in PX4-gazebo-models anchors spherical coordinates at latitude 47.397971057728974, longitude 8.546163739800146, elevation 488 m, ENU, WGS84, with magnetic field `6e-06 2.3e-05 -4.2e-05`. Matching that anchor keeps the SITL compass and home consistent. The block is a fictional civilian scene placed on that anchor, not a real incident and not a military model.

SurMap's scope boundary still holds: no flight commands in `src/surmap`. A QGroundControl `.plan` file is operator data. A launch script may only symlink resources and exec `make px4_sitl`. `gz` is not installed on this agent VM; proof is XML plus Python checks of poses, geodetic conversion, and the plan. `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md` is a different, still-open proto gap and is not part of this world.

No `docs/simulation/1-WIP/` changeset existed on the branch. README.md is out of scope for this change.

## Exploration 1: PX4 SITL branch and world launch — 2026-10-28

**Agent**: parent Grep/Glob/Read and GitHub fetches
**Scope**: `origin/feat/PX4_sitl` simulation tree, PX4 `px4-rc.gzsim`, `default.sdf`, architecture §2.3

### Sequence

1. `git fetch origin feat/PX4_sitl` — local `main` has no simulation tree.
2. `git ls-tree` on that branch for sim/px4/gazebo paths — models, runbook, exporter, tests.
3. Read `docs/simulation/px4-sitl.md`, both stereo SDFs, and `.agents/skills/px4-sitl-test/SKILL.md`.
4. `gh pr view 18` — base `main`, head `feat/PX4_sitl`, passive-bridge summary.
5. Fetch PX4 `ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim` and `gz_env.sh.in`.
6. Fetch `PX4-gazebo-models/worlds/default.sdf` for physics, sun, and spherical coordinates.
7. Read `docs/architecture.md` §1, §2.3, §4.3 on the branch (Gazebo path already recorded; no disaster world).
8. `gz` / `gz sdf` — not on PATH in this VM.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Glob | `docs/simulation/**/*` | workspace `main` | none |
| `git ls-tree` | sim, px4, gazebo, world | `origin/feat/PX4_sitl` | `docs/simulation/gz/`, `px4-sitl.md`, `surmap.simulation` |
| Grep | `spherical\|latitude` | `src/surmap` on `main` | no geodetic helper |

### Inspected files

#### `docs/simulation/px4-sitl.md` (on `feat/PX4_sitl`)

**Why**: launch contract this world has to extend.
**Excerpt**: `PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500`. Resource path includes `docs/simulation/gz`. SurMap must not publish flight commands. Stereo is 640×480, hfov 1.3962634 rad, baseline 0.07 m, forward (+X) optical axis.

#### `docs/simulation/gz/x500_surmap_stereo/model.sdf`

**Why**: confirm the rig is included, not redefined, by a world.
**Excerpt**: include of `x500` plus `model://surmap_stereo_cam` at `0.12 0 0.242`.

#### PX4 `px4-rc.gzsim`

**Why**: where a custom world file is actually opened.
**Excerpt**: `gz sim -r -s "${PX4_GZ_WORLDS}/${PX4_GZ_WORLD}.sdf"`, then GUI unless `HEADLESS` is set. Spawn service is `/world/${PX4_GZ_WORLD}/create`.

### Findings

- World file has to be symlinked to `~/PX4-Autopilot/Tools/simulation/gz/worlds/disaster_block.sdf`. `<world name="disaster_block">` must match.
- Textures referenced relatively from that directory need the same symlink treatment, because PX4 opens the symlink path.
- Default world has no `<plugin>` elements; systems come from PX4 `server.config`. This world should follow that, so plugins are not loaded twice.
- Ground truth can live as JSON plus a typed loader in `surmap.simulation` without a flight interface.
- A lawnmower at 12 m AGL, 4 m/s, lanes x = −24, −12, 0, 12, 24 between y = 18 and y = 100, covers a block whose people stand in the open streets within 8 m cross-track of a leg.
