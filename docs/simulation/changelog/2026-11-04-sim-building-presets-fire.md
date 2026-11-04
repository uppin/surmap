# Building presets on Overture's vocabulary, districts and building fires in the Bevy simulation

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #104

Buildings in a scenario now take wall and roof presets named after Overture's
`facade_material` / `roof_material` values — the vocabulary of the station map's
`overture-buildings` layer; no Overture geometry is imported, by the developer's choice. Eleven
facades and fourteen roofs ship, textured with 17 Poly Haven and 3 ambientCG CC0 sets, each with
a charred `burnt` variant; facades carry punched windows (recess, frame) or glass curtain walls
(mullions, spandrels). Roofs are flat with a parapet, gabled, hipped or pyramidal. A district —
`old-town`, `downtown`, `industrial`, `suburban`, or any `.district.json` file — is a rectangle
with a weighted mix of facades, roofs, shapes, colour palettes, a floor height and window
ratios; each building inside draws its style deterministically from the district's seed and its
own id, and its own fields win. Legacy `material` buildings render as before.

Buildings burn floor by floor (`building_fire.rs`, pure and stepped): a fire climbs and descends
from its ignition floor, burns each floor out, ignites a neighbour after a continuous exposure
within a distance that grows downwind, and is lit by a wildfire's burnt area. Burning floors lose
their panes, glow orange behind the windows, show flames at every window and a dark plume from
the top burning floor; burnt floors are charred and sooted. Burning footprints fill the
behaviour runtime's `World.burning_areas`, so people flee burning buildings. Every number is
runtime JSON: the presets, `building/look.json` (roof shapes, interior, shopfront, glow inset,
soot, the fire light), `building/fire.json` (spread and glow) and two new fx files with a new
`emit_radius_m` field.

The agent gained six tools — `list_building_presets`, `set_district`, `remove_district`,
`style_building`, `add_building_fire`, `remove_building_fire` — and the station two presets,
`district-showcase` and `downtown-blaze`. Building handlers moved into
`simulation_building_tools.py`, shared plumbing into `simulation_core.py`; `ScenarioStore` takes
`assets_dir=` to list added preset files. Captures add `building_fires.jsonl`, read as
`load_bevy_capture(...).building_fires`. Stills take `--look-at <district id>` and aim at the
first building fire. Asset fetching sends a user agent (ambientCG refuses urllib's) and
downloads each ambientCG zip once per run.

Verified by unit tests on both sides (presets, resolution, the fire model, manifest rules, the
golden `downtown-blaze` scenario parsed by the renderer), an agent turn on a real socket, and the
planner's review of native stills: D1 (the four districts) passed in one round; D2 (the blaze at
t = 15, 120, 400, 900) passed after one round of JSON corrections — orange glow at 3.5, flame
tongues, a continuous plume, and the neighbour's ignition moved from 65 s to 364.9 s. Follow-ups:
texture character, per-window glow variation, pre-warmed smoke in stills and district-resolved
fire floors were done in the sweep ([2026-11-04-sim-disaster-2-sweep.md](2026-11-04-sim-disaster-2-sweep.md)); legacy buildings burning stays recorded in
`src/surmap/docs/todo/2026-11-04-legacy-buildings-burn.md`.

Part of stack `#sim-disaster-2` (3 of 4): `main ← n3 #100 ← n4 #101 ← n5 #104 ← sweep`. Green
waves: n3 is wave 1 of 3, n4 wave 2, n5 wave 3. This PR needs #100 (the fire spec, fx loader,
emitters and wind) and #101 (`World.burning_areas` and the wind tree); it blocks nothing but the
sweep.
