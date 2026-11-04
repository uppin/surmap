# Behaviour trees driving people and the wind in the Bevy simulation

**Date:** 2026-11-03
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #101

People in a scenario now act by declarative behaviour trees — wander, follow a path, move to a
point, flee a fire, wait, react to the wind or to another body — and the wind has a tree of its
own whose `set_wind` ramps veer and strengthen it over time, so n3's vegetation, fire spread,
flame lean and smoke follow it. A tree is inline JSON on a `person` element or on
`weather.wind`; the renderer and the station validate it by the same rules per target. The
runtime is a small pure Rust module ticked at a fixed 10 Hz in simulation time, so a run
replays identically; figures turn to their heading with an eased yaw and bob while they walk,
from `assets/behaviour/person.figure.json`.

The agent declares and edits trees with three new tools — `set_behaviour`,
`update_behaviour_node` (by node `id`) and `get_behaviour` — and `PersonElement` gained `skin`.
The station gained the `wildfire-evacuation` preset: `wildfire-edge` with three evacuees who
wander and flee the front, and a westerly that veers to 300° at 10 m/s from 20 s. Every capture
records `object_tracks.jsonl` — each frame's wind and every person's position and running
action — read back as `load_bevy_capture(...).object_tracks` and `.wind`; a still of a scene
with people adds `people.png`. `World.burning_areas` is the seam through which other burning
ground (n5's burning buildings) is fled like a wildfire front.

Verified by unit tests on both sides (every node kind, determinism, a fleeing person never in
the burnt area, the wind ramp, the golden `wildfire-evacuation` scenario parsed by the
renderer), an agent turn on a real socket, native recordings showing the evacuees flee and the
wind veer (275° at 25 s, ≈ 287° at 36.9 s) with no evacuee inside the burnt area over 40–70 s,
and the planner's review of native stills at t = 10 and t = 60 in two passes. At wrap,
`behaviour.rs`, `actors.rs` and `scenario_manifest.py` were split below 500 lines and their
`dead_code` allows removed. Follow-ups, both done in the sweep ([2026-11-04-sim-disaster-2-sweep.md](2026-11-04-sim-disaster-2-sweep.md)): a front cue so the turn
shows (the figure's visor) and a pre-existing timing test that failed under load (now measured in
process CPU time).

Part of stack `#sim-disaster-2` (2 of 4): `main ← n3 #100 ← n4 #101 ← n5 #104 ← sweep`. Green
waves: n3 is wave 1 of 3, n4 wave 2, n5 wave 3. This PR needs #100 (the wind and fire models it
reads and drives) and blocks #104 (building presets with fire, which fills `burning_areas`).
