# Weather, wind-swept vegetation and an animated wildfire in the Bevy simulation

**Date:** 2026-11-03
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · Survey agent simulation tools ([agent.md](../../agent.md)) · PR #100

Scenarios gained weather — rain, fog and one wind — stands of procedural pines and dry grass that
sway in that wind (Feronia, with `bevy_eidolon` instancing for grass), and wildfires whose front
spreads downwind as a Huygens ellipse, drawn with GPU particles (`bevy_hanabi`): flames that lean
with the wind, embers, a smoke plume that bends downwind, scorched ground with a glowing front,
and charred trunks where the fire has passed. Every number of the look moved into runtime JSON
(`assets/fx/*.fx.json`, `assets/species/*.species.json`); Rust implements only the kinds.

The agent declares it with three new tools — `set_weather`, `add_fire`, `remove_fire` — and a
`vegetation` element; the station gained the `wildfire-edge` and `flood-street` presets and
validates the new fields by the renderer's rules. A capture of a burning scene records each
frame's fire perimeter in `fire_perimeter.jsonl`, read back as
`load_bevy_capture(...).fire_perimeters`. Review stills of a fire scene aim the overview at the
ignition and add a `fire-eye.png` through the rig's intrinsics.

Verified by unit tests on both sides, an agent turn on a real socket that builds a ridge fire,
a golden `wildfire-edge` scenario parsed by the renderer, and the planner's review of native
stills against a visual spec in two rounds: vegetation in the wind, rain and fog, smoke and the
burnt area passed; the flame front was accepted as a glow, with flame tongues left as a TODO.
Follow-ups are recorded in `src/surmap/docs/todo/2026-11-03-{flame-tongue-flipbook-sprites,
per-stand-grass-seed,fire-light-visibility,fire-perimeter-capture-end-to-end,fire-eye-mount-pitch}.md`.

Part of stack `#sim-disaster-2` (1 of 4): `main ← n3 #100 ← n4 #101 ← n5 #104 ← sweep`. Green
waves: n3 is wave 1 of 3, n4 wave 2, n5 wave 3. This PR blocks #101 (behaviour trees that drive
the wind and read the live fire); #104 (building presets with fire) needs both.
