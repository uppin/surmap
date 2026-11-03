# 2026-11-03 — Live WebSocket stream from the browser simulation

**Category:** Deferred scope (changeset milestone M6)
**Source:** PR #89, stack `#sim-disaster` n1
**Packages:** examples/bevy-sitl-poc, surmap.simulation, scripts
**Consent:** Developer, 2026-11-03: "let's wrap the PR with TODO and we'll address the correctness in next PRs".
**Priority:** 2
**Status:** Open

## What is left

The wasm WebSocket client (`?bridge=ws://127.0.0.1:8773`) sending `wire::encode_hello`
and `encode_pair` from `Readback` of the eye targets at `rate_hz`, the RTAB-Map status
overlay from the bridge's replies (visual spec §8), and `scripts/serve_bevy_sim.py`
(static `dist/` + `assets/` on one origin, bridge on 8773, `--record`). Then the V4
recorded live run in Chrome.

## What exists

Wire format with byte-exact goldens shared by Rust and Python; `BevyStreamSession` and
`serve_bevy_bridge` (tested over loopback); the native `--record` path that produces
the same capture the bridge would; the camera profile carried in the hello.
