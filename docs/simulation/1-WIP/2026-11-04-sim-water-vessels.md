# Changeset: boats and ships on the water

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 3 — two vehicle classes on n1's runtime, a pure sea-state model, water-surface
validation in renderer and station, a preset; one native visual checkpoint

PRD: `PRD-2026-11-04-sim-water-vessels.md` · Discovery:
`2026-11-04-sim-water-vessels-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-pr-stack` Plan — PRD, changeset, initial discovery · these files (`/plan-pr-stack` pass 1)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Build and baseline healthy (`uv run mypy`, `uv run pytest -q`, `cargo test --locked`)
  - [ ] Stubs this node owns (`sea.rs`, `VehicleClass::{Boat, Ship}`, `BoxElement.water`, `Medium`, Python water rules)
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Pin CC0 boat and ship glTF (Kenney *Watercraft Kit*, CC0, or equivalent); `fetch_sim_assets.py` verifies them
  - [ ] Rust `scene_manifest.rs`: `water` on `box`; vessel classes; validation (start on water, every `move_to`/`follow_path` point on water, no `wander`/`flee_from_fire` in a vessel's tree)
  - [ ] Rust `sea.rs` (pure): `sea_state(wind)` and `vessel_motion(class, sea, t_s, phase) -> (heave_m, pitch_rad, roll_rad)`
  - [ ] Rust runtime: vessels driven by n1's `Drive`, held at the water box's top + heave, pitched/rolled; no wheels
  - [ ] Python `scenario_manifest`: same rules; preset `flood-rescue`; golden fixture parsed by Rust
  - [ ] Proto/handler: `VehicleElement.class` accepts `boat`/`ship`; `BoxElement` gains `water`; regenerated code; docs table
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (tests + native still of `flood-rescue` reviewed)
  - [ ] `docs/simulation/bevy-simulation.md` — *Vehicles* → vessels and sea state; `docs/agent.md`
  - [ ] `docs/simulation/changelog/2026-11-04-sim-water-vessels.md`
  - [ ] Lint (`ruff --no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack `sim-traffic` (slug `sim-traffic`) — **3 of 3** · PR `#pending`.
**Kind:** Feature · adds — **Workflow:** feature preset; pass-2 route `/plan-red` Steps 7–9.
Branch `pr-3-sim-traffic`, base `pr-2-sim-traffic`; successor none — top of stack.
Seam: n1's vehicle classes and spawning, extended by a `Medium::Water` branch and `sea.rs`.
**Owned API:** `VehicleClass::Boat` / `Ship`, `Medium`, `BoxElement.water`, `sea.rs`
(`SeaState`, `sea_state`, `vessel_motion`), the vessel validation rules (Rust and Python),
`boat`/`ship` class files, preset `flood-rescue`, proto `BoxElement.water`.

### Green wave

**Wave:** 2 of 2 · **Node:** n3 · **Concurrent with:** none · **Blocks:** nothing ·
**Needs:** n1 — the `vehicle` element, `Drive` kinematics, vehicle spawning and track `kind`, which
vessels are driven by.
Edges: `n1 → n3`; nothing from n2.
**Greenable independently?** no — its runtime and acceptance tests drive n1's `Drive` and vehicle
spawning; waits on n1's Green row. Pure `sea.rs` and validation tests can be greened earlier.

### Inherited Dependencies — do not implement here

| Symbol | Owner | During this PR's green | This PR instead |
|---|---|---|---|
| `Element::Vehicle`, `Vehicle`, `VehicleClass`, `VehicleDef`, `Drive`, vehicle spawn | n1 | stub until n1 greens | adds two classes and the water branch; never edits `Drive`'s limits |
| track `kind` / `yaw_deg`, `BevyCapture.object_kinds` | n1 | stub | relies on them for `boat`/`ship` |
| proto `VehicleElement`, Python `vehicle` kind | n1 | stub | extends the class set only |
| `Person.pose`, rig, `figure_anim.rs` | n2 | stub | not used |

**Greenable independently?** no — waits on n1.

### Trunk-merge safety

Additive: `water` optional on `box` (absent = today's rendering); new classes only. Manifest
version 1, no SQLite schema change, no production data. Assets fetched, git-ignored.

## Background

The developer (2026-11-04): "We should support ships, boats too." Planned as n3 of `#sim-traffic`
on n1's vehicles.

## State A (before, after n1)

`vehicle` element with road/rail classes driven by `Drive` over behaviour trees; water is a `box`
with material `water` and no semantics; `flood-street` is rain and fog over the block, no water.

## State B (after)

### In the manifest

```json
{"kind": "box", "id": "floodwater", "material": "water", "size_m": [10, 160, 0.6],
 "position_enu": [0, 45, 0.0], "water": true}
{"kind": "vehicle", "id": "rescue-boat-1", "class": "boat", "position_enu": [0, 0, 0],
 "behaviour": {"node": "repeat", "child": {"node": "follow_path",
   "enu": [[0, 110], [0, 10]], "speed_m_s": 4.0}}}
```

A vessel's `position_enu[2]` is ignored: it floats on the top of the water box under its start.

### Class files

`boat`: 5 m, max 8 m/s, accel 1.5, brake 1.0, turn 25°/s; `ship`: 60 m, 7 m/s, 0.1, 0.08, 2°/s
(planned). Both `medium: water`, `draft_m`, and `wave_response` (motion gain, ≈ 1 for a 5 m boat,
≈ 0.1 for a 60 m ship).

### Sea state (`sea.rs`, pure, deterministic)

`sea_state(wind)` → significant wave height and period from the weather's wind speed (fetch-limited,
capped for small water); `vessel_motion` sums three seeded sinusoids (phase per id via
`phase_of`) for heave, pitch and roll, scaled by `wave_response` — so motion grows with wind and
shrinks with length. Calm wind → still water. Evaluated on `SimClock`, so stills replay.

### Validation (renderer and station alike)

A vessel must start inside a `water: true` box's footprint; every `move_to`/`follow_path` point of
its tree must lie inside one; its tree may not contain `wander` or `flee_from_fire`; a road/rail
class may not start on water. Refused by name.

### Preset `flood-rescue`

`flood-street` plus `floodwater` over the avenue (0.6 m), two rescue boats shuttling its length,
and a survivor (n2's poses when n2 has landed, a standing person otherwise) waiting at its north end.

## Verification

- **V1** — Rust: `vessel_motion` within bounds, grows with wind, ship < boat, zero in calm,
  deterministic; a vessel driven 120 s stays at the surface ± heave; validation (off-water start,
  path leaving water, forbidden nodes, road class on water) and the golden `flood-rescue.json`.
  Python: the same validation, preset, `add_element` boat; acceptance over the preset's tracks.
- **Supporting evidence (not a rung)** — native still `--screenshot <dir> --at 20 --scenario
  flood-rescue`, reviewed at wrap.

## Prerequisites

Deferred-work scan: `2026-11-03-bevy-visual-checkpoints-v3-v5.md` — ℹ unrelated. Nothing blocks.

## Decisions & Trade-offs

- An explicit `water: true` on a box instead of inferring water from the material name: material
  keys are free-form scenario data.
- Paths validated against water at load rather than clamped at runtime: a refused scenario with a
  reason beats a boat silently stopping at a kerb; `wander`/`flee_from_fire` are excluded because
  their points are not known at load.
- Kinematic wave motion, not buoyancy physics: deterministic, cheap, wasm-friendly; enough for a
  survey camera.
