# 2026-11-04 — The #drone-fleet stack's browser runs in Chrome (V4)

**Category:** Deferred scope
**Source:** #drone-fleet (n3, PR #119: the fleet link's V4; n5's browser stream procedure joins it)
**Packages:** surmap, examples/bevy-sitl-poc
**Consent:** Developer, 2026-11-04: "please wrap n3. I'll do browser testing after the stack is merged".
**Priority:** 2
**Status:** Open

## What is left

### n3 — the fleet link in a live page (PR #119)

1. `cd examples/bevy-sitl-poc && trunk build index.html --release`.
2. `uv run python scripts/fleet_link_smoke.py --sim-dist examples/bevy-sitl-poc/dist --preset earthquake-fleet`.
   The script prints the page URL and waits for a `hello`.
3. Open the printed `/sim/?scenario=<id>&fleet=1` in Chrome.
4. The script sends a sortie: it launches `nest-sw-d1`, sends a `detour` at +15 s, launches
   `nest-ne-d1` and sends `set_active` for it, then sends `recall` to both. It prints each
   `applied` (`seq`, `at_s`) and the telemetry phases.
5. Capture the evidence: the script's full log, a screenshot with two drones airborne and the feed
   on `nest-ne-d1`, and the exported `--fleet-log` file. Replay that file natively
   (`--screenshot … --at <t>`): it must show the drones where the browser showed them at the same
   simulation time.

### n5 — the browser stream (PR #121)

Deferred with the same consent as n3 (developer, 2026-11-04: browser testing after the stack
is merged). V1 + V3 accepted for the wrap; this procedure is the V4 evidence.

1. `cd examples/bevy-sitl-poc && trunk build index.html --release`.
2. Start the agent with the streaming RTAB-Map image available:
   `uv run python -m surmap.agent --sim-dist examples/bevy-sitl-poc/dist --bevy-bridge-port 8773 --sam-fake`.
3. Open `/sim/?scenario=<earthquake-fleet>&fleet=1&bridge=ws://127.0.0.1:8773` in Chrome.
4. Through the chat (or `scripts/fleet_link_smoke.py`):
   1. launch `nest-sw-d1` and `nest-ne-d1`, with `nest-sw-d1` active for 60 s;
   2. `set_active_drone nest-ne-d1` for 60 s;
   3. switch back to `nest-sw-d1` for 30 s;
   4. call `drone_map_status`.
5. Evidence: screenshots of the status overlay (`MAP <drone> · <n> frames · <k> keyframes ·
   tracking`) before and after each switch, and the `drone_map_status` output. It must show
   two drones with keyframes, `processing` on the active one, and `nest-sw-d1`'s frames
   continuing (not restarting) after the switch back.

## Why it could not be done now

No CI harness runs a WebGPU page with a live WebSocket
(`2026-11-03-bevy-visual-checkpoints-v3-v5.md`: the browser runtime is unverified in CI), and the
run needs a person at Chrome. The developer chose to do the browser runs once, after the whole
stack has merged, instead of once per PR.

## What was done instead

- n3 was verified by V1 and V3. V1 covers the station and codec: 74 pytest tests over a real
  agent server and a fake page, plus `cargo test --locked link` (18). V3 is
  `cargo check --locked --target wasm32-unknown-unknown` with `fleet/link_wasm.rs` compiled in.
- `scripts/fleet_link_smoke.py` flew the whole sortie against a scripted fake page: 6 applied,
  both drones docked, a 6-line export.
- The wasm glue (`fleet/link_wasm.rs`: the socket, the command queue drained into
  `FleetLog::push`, the telemetry timer) has not run in a browser yet.
- n5 was verified by V1 and V3. V1 covers routing, wire goldens, the loopback bridge with two
  drones, the status tool, and the real-sidecar e2e (both sessions gain keyframes, the first
  drone resumes in the same backend). V3 is
  `cargo check --locked --target wasm32-unknown-unknown` with `fleet/bridge_wasm.rs` compiled in.
- The wasm stream (`fleet/bridge_wasm.rs`: the `?bridge=` socket, eye `Readback` →
  `encode_pair` with the active drone id, the status overlay) has not run in a browser yet.

## When it becomes possible

When the `#drone-fleet` stack (n1–n5) has merged to `main`: build the page from `main` and run
both procedures.
