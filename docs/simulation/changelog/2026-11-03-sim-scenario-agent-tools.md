# Simulation scenarios built by the agent, served by the station

**Date:** 2026-11-03
**Feature:** Survey agent simulation tools ([agent.md](../../agent.md)) · Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · PR #91

The survey agent can now build the world it surveys. `SimulationTools` search Poly Haven,
ambientCG and Sketchfab (CC0 / CC BY only — every hit carries its licence verdict; NC, ND and SA
are refused with the clause), download accepted assets into the station's library with each
file's SHA-256, and compose scenarios from the earthquake-block or empty-lot preset with library
models and the simulation's element kinds. Scenarios are the simulation's own `scene.json`
manifests, validated by the renderer's rules and stored in SQLite with every edit as a new
version; CC BY authors are credited per scenario.

The agent server serves the scenarios, the library and the simulation's assets under `/sim/`
on one origin (and the built page with `--sim-dist`); the page opens `?scenario=<id>`, natively
`--scenario <id>`. Verified with a scripted agent turn on a real socket (the station then serves
the manifest and the byte-identical GLB), a golden scenario the Rust renderer's tests parse, and
a scenario built through the tools against live Poly Haven, rendered natively.

Developer's split (2026-11-03): weather with an animated wildfire, and behaviour trees, follow
in their own stacked PRs.
