# Changeset: The dev simulation page runs an optimised engine

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Infra
**Behaviour**: preserves
**Complexity**: 1 — one manifest line, no code

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-ft-dev` Plan — changeset with a V3 `## Verification` and its before-output · this file
- [wf 2] ✅ 2026-11-04 `/green` Implement — the recorded command produces the planned after-output · `bevy_pbr opt-level=3`, `bevy_sitl_poc opt-level=1`
  - [x] `[profile.dev.package."*"] opt-level = 3` in `examples/bevy-sitl-poc/Cargo.toml`
  - [x] After-output recorded
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — the dev page's build profile

## Initial Discovery

Shared with [the station changeset's discovery](./2026-11-04-sim-never-waits-on-station-initial-discovery.md)
(*The dev page is barely optimised*).

## Technical Changes

### State A (Current)

`scripts/dev.sh` builds the sim page with trunk's dev profile (since #142, for incremental
rebuilds). `[profile.dev] opt-level = 1` applies to every crate, so Bevy, Rapier, Hanabi and
Feronia run at opt-level 1 in the page the chat embeds.

### State B (Target)

Dependencies build at opt-level 3 in the dev profile; the PoC's own crate stays at 1 and keeps
its incremental rebuilds. Dependencies rebuild once, then are cached.

## Verification

**Method:** V3 — the compiler flags cargo passes for an engine crate and for the PoC crate
**Command:** `cd examples/bevy-sitl-poc && touch src/main.rs && cargo build --target wasm32-unknown-unknown -v 2>&1 | grep -oE "Running .*--crate-name (bevy_pbr|bevy_sitl_poc) .*-C opt-level=[0-9]" | grep -oE "crate-name [a-z_]+|opt-level=[0-9]" | paste - -`
(after a clean dependency build; `touch` makes the PoC crate print its flags)
**Before:**

```text
crate-name bevy_pbr	opt-level=1
crate-name bevy_sitl_poc	opt-level=1
```

**After:**

```text
crate-name bevy_pbr	opt-level=3
crate-name bevy_sitl_poc	opt-level=1
```
