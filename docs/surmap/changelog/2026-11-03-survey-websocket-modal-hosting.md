# Survey servers — RPC over WebSocket, GPS on the wire, hosted on Modal

**Date:** 2026-11-03
**Feature:** Survey servers (Board API / GPU API)

Both survey servers serve their Connect services over one WebSocket at `/connect` next to
Connect over HTTP, using the in-tree `surmap.rpc.socket_rpc` protocol. Every survey client in the
repo moved to the new asyncio `SurveyConnection`: the demo's remote adapters and both verify
scripts. The h2c and `http.client` paths are gone. A bearer token (`--auth-token` /
`SURMAP_SURVEY_TOKEN`) guards Connect calls and WebSocket upgrades, and sockets are kept alive
for proxies that drop idle connections. A long streamed call no longer holds its replies in
memory until it ends.

The CM5's `StreamSurvey` takes GPS: a `GpsFix` between frames is answered with a `GpsAnchorOut`
tied to the posed frame nearest in time. An idle stream keeps streaming what a live RTAB-Map
backend produces. Without `--calibration-dir`, the live mode takes each stream's camera
definitions from its config, and region queries reach that stream's own backend. That is how a
simulated drone is fed.

Two Modal apps run the servers as one-container web servers: `modal_cm5_app.py` (CPU, RTAB-Map
built natively) and `modal_station_app.py` (L4, SAM 3.1). `scripts/verify_cm5.py --simulated
[--hold-s S]` verifies a simulated drone. On Modal the CM5 app passed health, token refusal,
survey, GPS and region checks over `wss://`, with one stream held for 205 s. The station app has
not run on Modal yet.

Docs: [connectrpc.md](../../connectrpc.md#connect-over-one-websocket),
[deployment.md](../../deployment.md#running-by-hand), [modal.md](../../modal.md) §5,
[architecture.md](../../architecture.md) §10.

Closes `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md`.
