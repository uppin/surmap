# oversized-file: examples/bevy-sitl-poc/src/world.rs

**Location:** `examples/bevy-sitl-poc/src/world.rs`
**Category:** oversized-file
**Detected:** 2026-11-04 by `/pr-wrap` step 4 (file-length gate)
**Metrics:** 496 → 566 lines (limit 500)
**Restructure:** required — left for the `#drone-fleet` sweep node (stack-shared file)
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)

## Measurement history

| Run | Lines | Note |
|---|---|---|
| 2026-11-04 | 496 → 566 | `pr-1-drone-fleet` (#116): `Builder::nest` (pad rim, deck, H) and the `Nests` resource; left for the #drone-fleet sweep node — later stack PRs edit this file too, so splitting it here would conflict every node above |

## What would close it

Move each element builder family (nests, water, vehicles) into `world/<family>.rs` submodules, leaving `world.rs` as the `Builder` dispatch.
