# Changeset: Trackpad PTZ for the simulation chase view

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one Rust crate, pure orbit module with unit tests, one input system

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion (target chosen by the developer: orbit chase view)
  - [x] Discovery companion written from the current input wiring
  - [x] State A / State B / Delta and Verification written
- [wf 2] ✅ 2026-11-04 `/plan-red` Red — failing unit tests, committed · 7 red @ `view_orbit::tests` (todo! skeleton)
  - [x] Scroll pans (yaw) and tilts (pitch, clamped) the orbit
  - [x] Pinch zooms the orbit distance (clamped); default orbit = today's chase offset
- [wf 3] ✅ 2026-11-04 `/green` Green — implement until every red test passes · 274 crate tests pass; live pan/tilt/pinch screenshots (see Verification)
  - [x] `view_orbit` module: scroll/pinch handlers and the offset computation
  - [x] `MouseWheel` + `PinchGesture` system feeding it; `chase_camera` uses the orbit
  - [x] Hints updated (`ui.rs` status line, page hint in `index.html`)
  - [x] Live check: trackpad scroll/pinch visibly orbits and zooms the view
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [x] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — controls note updated
  - [ ] Gates green: `cargo test` (crate), `ruff check`, `ruff format --check`, `mypy`, `pytest`

## Stack Context

**Stack**: sim dev stack · slug **`#sim-dev`** — this PR is **2 of 2**
**Branch**: `feat/sim-trackpad-ptz` · **Base**: `fix/dev-sim-prereqs`
**Successor**: none — top of stack
**Kind**: Feature · adds — the `(Type, Behaviour)` pair from the header
**Workflow**: preset `feature` · planned by `/plan-red`

### Owned API surface

`examples/bevy-sitl-poc/src/view_orbit.rs`, the chase-camera wiring in `main.rs`,
and the control hints in `ui.rs` / `index.html`.

### Green wave

**Wave:** 1 of 1
**Node:** n2
**Concurrent with:** none
**Blocks:** nothing

### Greenable independently?

**yes** — it builds on the predecessor's served page but implements none of it;
its tests drive only its own orbit module.

### Trunk-merge safety

**When this PR merges alone:** it sits on PR 1, so it never merges alone; the
simulation behaves as before until a trackpad gesture arrives. **Local dev data:**
none. **Production data:** none.

## Inherited Dependencies — do not implement here

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `scripts/dev.sh` sim prerequisites (`--sim-dist`, page build, asset fetch) | PR 1 (`fix/dev-sim-prereqs`) | implemented in the base branch | uses the served page to verify live; does not implement it |

**Greenable independently?** yes — no predecessor symbol is stubbed or driven by this PR's tests.

## Initial Discovery

Full codebase exploration that grounded this plan: [2026-11-04-sim-trackpad-ptz-initial-discovery.md](./2026-11-04-sim-trackpad-ptz-initial-discovery.md).

State A below is distilled from that file. Do not duplicate grep traces or file dumps here.

## State A

- The chase camera is fully automatic: fixed offset behind the drone, always
  `look_at` the drone. Flight is keyboard-only; no mouse, wheel or gesture input
  is read anywhere in the crate.

## State B

- Two-finger trackpad scroll pans (orbit yaw) and tilts (orbit pitch, clamped so
  the view stays above the ground plane) around the drone; pinch zooms the orbit
  distance (clamped 3–40 m). The drone stays centred; keyboard flight is unchanged.
- With no input the view is exactly today's chase view, so screenshot/record
  modes are unaffected.
- The status line and the page hint name the gestures.

## Delta

- `examples/bevy-sitl-poc/src/view_orbit.rs` (new): orbit state, gesture handlers, tests.
- `examples/bevy-sitl-poc/src/main.rs`: register the resource/system, orbit-aware chase.
- `examples/bevy-sitl-poc/src/ui.rs`, `examples/bevy-sitl-poc/index.html`: hint text.

## Verification

- `cargo test` in `examples/bevy-sitl-poc` — red before, green after.
- Python gates: `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy`, `uv run pytest -q`.
- Live: rebuilt page via `./scripts/dev.sh`, dispatch wheel/pinch in the browser
  pane and screenshot the view from a new angle and distance.

Executed 2026-11-04: rebuilt with `trunk build --public-url /sim/`, stack running via
`./scripts/dev.sh`; in the browser pane, synthetic `wheel` events on `#bevy-canvas`
orbited the view (house seen from successive sides), a vertical scroll tilted it, and a
ctrl+wheel pinch reframed it wider — four screenshots, all distinct, scene rendering
throughout. `cargo test`: 274 passed. Python gates: `ruff check`, `ruff format --check`,
`mypy` pass; `pytest -q`: 2276 passed, 10 skipped.
