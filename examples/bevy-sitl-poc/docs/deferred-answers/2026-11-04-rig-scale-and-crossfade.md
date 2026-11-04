# 2026-11-04 — How a rig is scaled to a height and how its clips crossfade

**Kind:** Technical
**Source:** `docs/simulation/1-WIP/2026-11-04-sim-rigged-people.md` (PR #107, stack `#sim-traffic` node 2/3)
**Asked by:** `/green` row 3 — `[G]` n2, Haiku 5.5 (under `#yolo`, no supervisor relay)
**Packages:** bevy-sitl-poc
**Status:** Awaiting review

## Question

Two numbers the changeset leaves to the code. (1) `rig_scale` must give exactly 0.9 for a 1.62 m
person on a 1.8 m rig (`a_person_is_scaled_to_their_height`), and an f32 division of the two heights
gives the neighbouring float. (2) The walk→run crossfade needs a width; `RigDef` has no field for it,
and the red tests pin that the walk is still exactly 1.0 at 1.2 m/s with `run_above_m_s` 2.2.

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) | Round both heights to the millimetre, then divide in f64 | Exact for every millimetre height; no new field |
| b) | Add a `rig_scale` epsilon or a rounding step to the test instead | Changes a red test: not allowed |
| c) **(picked)** | Crossfade over a quarter of the walk→run gap either side of `run_above_m_s` | Derived from the rig's own ground speeds; no new field; both clips are shown only inside the band |
| d) | A new `crossfade_m_s` field in `RigDef` | Breaks the test's struct literal (it lists every field) |

**Asker's pick:** a) for scale and c) for the crossfade — the rig block keeps the fields the changeset names.

## Decision

`rig_scale` reads both heights as millimetre values (`src/figure_anim.rs`), so a 1.62 m person on
a 1.8 m rig is 0.9 exactly. `locomotion` crossfades over `(run_ground − walk_ground) / 4` either side of
`run_above_m_s`. The renderer eases the weights over `blend_s` of simulation time (`src/actors/rig.rs`
`drive_rigs`). Neither has been seen on a screen: there is no pinned rig asset yet.

## What was built on it

`examples/bevy-sitl-poc/src/figure_anim.rs` (`rig_scale`, `locomotion`), `src/actors/rig.rs`
(`drive_rigs`). Tests that pin it: `src/figure_anim/tests.rs` (`a_person_is_scaled_to_their_height`,
`walking_crosses_into_running_with_weights_that_sum_to_one`, `a_posed_person_who_moves_walks`).

## To override

For (a): change `rig_scale` to a plain f32 division and drop the scale test's exact equality — a test
change, so the developer decides. For (c): replace the band in `locomotion` with another rule over the
same fields; the weight-sum and rate tests still hold for any band that stays inside the walk→run gap.
