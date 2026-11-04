# dev.sh ensures the simulation prerequisites

**Date:** 2026-11-04
**Feature:** Bevy simulation ([bevy-simulation.md](../bevy-simulation.md)) · PR #135

`./scripts/dev.sh` now serves the simulation page at `/sim/` by default and ensures
everything it needs before starting any service: `uv` and `yarn` on PATH, the chat
UI's `node_modules`, the simulation's pinned textures, models and HDRI fetched and
hash-verified, and a page build addressed under `/sim/` — rebuilt with
`trunk build --public-url /sim/` when missing or built for another prefix. A missing
tool or a failed fetch stops the script with an actionable message instead of
starting a stack whose simulation cannot load.

This fixes the black-canvas simulation: the agent previously served no page at
`/sim/` at all, and the checked-out build addressed its WASM from the server root,
which 404s under `/sim/`. Verified live — every asset returns 200 and the
house-and-tree scene renders in the browser — and by seven new tests in
`tests/test_dev_script.py` covering serving, rebuild, fetch ordering and
fail-before-start.
