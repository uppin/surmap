# 2026-11-04 — Who is in the earthquake-survivors morning-after scene

**Kind:** Product
**Source:** `docs/simulation/1-WIP/2026-11-04-sim-rigged-people.md` (PR #107, stack `#sim-traffic` node 2/3)
**Asked by:** `/green` row 3 — `[G]` n2, Haiku 5.5 (under `#yolo`, no supervisor relay)
**Status:** Awaiting review

## Question

The `earthquake-survivors` preset builds on the shipped block. The block's seven standing survivors
(`survivor-1` … `survivor-7` in `scene.json`) would stay, or give way to the cast the changeset names
(a survivor lying by `collapsed-0`, one sitting on the rubble of `collapsed-2`, one waving from
`collapsed-3`, two rescuers walking between them). `tests/test_sim_people_manifest.py` pins the
person poses as exactly `lying, sitting, standing, standing, waving`, so the seven cannot stay.

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) | Keep the seven standing survivors and add the five | Breaks the pinned pose list in the red test; would need the test changed |
| b) **(recommended, picked)** | The seven give way to the five | Matches the pinned pose list and the changeset's cast; the shipped scene itself is untouched |

**Asker's pick:** b) — the changeset names the cast, and the red test pins the count.

## Decision

Built: `src/surmap/simulation/people.py` `earthquake_survivors` drops the block's `kind: person`
elements and adds `survivor-lying` (−3, 29; first −8, 26), `survivor-sitting` (18, 52, z 1.0), `survivor-waving`
(9, 83, facing -60 degrees; first 16, 83, z 1.0 — half inside the slab, moved after the detector cross-check), and `rescuer-1` / `rescuer-2` on a `repeat` of two `follow_path` legs at 1.4 m/s.
Positions are chosen by hand from the footprints in `scene.json`; the rubble heights (z 1.0) are not
measured. The golden `tests/fixtures/sim_scenario/earthquake-survivors.json` is written from it.

## What was built on it

`src/surmap/simulation/people.py` (`earthquake_survivors`, `validate_person_look`),
`tests/fixtures/sim_scenario/earthquake-survivors.json`, `src/surmap/simulation/scenario_manifest.py`
(`load_presets`). Tests that pin it: `tests/test_sim_people_manifest.py`, `tests/test_sim_people_e2e.py`,
`examples/bevy-sitl-poc/src/scene_manifest/tests.rs` (`the_survivors_scenario_…`).

## To override

Change the cast list in `earthquake_survivors` and regenerate the golden from the preset (the same
step as the golden's first write). A different count changes the pinned pose list in
`test_the_survivors_preset_has_people_lying_sitting_and_waving_and_rescuers_walking`. The shipped
`scene.json` and `earthquake-block` are not affected.
