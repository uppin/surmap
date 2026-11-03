# Survey RPC over WebSocket, hosted on Modal

**Date:** 2026-11-03
**Status:** 🚧 In Progress
**Type:** Feature
**Behaviour:** adds
**Packages:** surmap
**Complexity:** High — a new transport on both survey servers and every survey client, a
contract change (GPS on the wire), and two new Modal deploy targets; touches `surmap.rpc`,
`surmap.survey`, `surmap.demo`, `scripts/` and `proto/`.

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — changeset, initial discovery · this file + discovery companion
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 30 red (23 failing + 3 modules not importable), 17 unchanged green
- [wf 3] ✅ 2026-11-03 `/green` Green — implement until every red test passes · 31 red → green; full suite 1778 passed, 10 skipped, 1 pre-existing (`test_survey_cm5_rtabmap_e2e`, fails on untouched main)
  - [x] `surmap.rpc`: Connect-over-WebSocket route that serves a host's composed Connect apps (`ServerDescription.connect_websocket_path`, `socket_rpc.connect_websocket_app`)
  - [x] `surmap.rpc`: keepalive — the route sends an empty socket frame every `websocket_keepalive_s` (hypercorn's own pings linger up to one interval after close and hold shutdown for its 3 s graceful timeout)
  - [x] `surmap.rpc`: bearer-token check on Connect HTTP and the WebSocket upgrade (401 via the ASGI denial response); health routes exempt
  - [x] `surmap.rpc.socket_rpc`: a long streamed call no longer holds every reply until it ends (collector and peer buffer trimmed) — found during green, 100 MiB stream peaked at 401 MiB before
  - [x] `surmap.survey.ws_client`: asyncio client — dial `ws://` / `wss://` with the token, typed CM5 and station calls over one `SocketRpcPeer`
  - [x] Survey proto: `GpsFix` on `Cm5Request`, `GpsAnchorOut` on `Cm5Response`; regenerate bindings
  - [x] CM5 `StreamSurvey`: each fix answered with an anchor carrying the map position of the pose nearest in time
  - [x] `cm5_main` / `station_main`: serve `/connect` over WebSocket, `--auth-token` / `SURMAP_SURVEY_TOKEN`
  - [x] `cm5_main.describe(argv)`: `--slam-backend streaming` without `--calibration-dir` — every stream brings its camera definitions (no default backend)
  - [x] `StreamRegionPoints` answered by the open survey stream's own backend (`build_description(stream_regions=True)`)
  - [x] `surmap.demo.remote` on the asyncio WebSocket client (h2c and `http.client` paths removed); each adapter runs its connection on its own event-loop thread
  - [x] `scripts/verify_cm5.py` / `scripts/verify_station.py` on the WebSocket client, URL addresses, `--token`; a refused stream fails its check instead of crashing
  - [x] `scripts/build_rtabmap_native.sh` runs as root without `sudo` (image builds)
  - [x] Modal apps `modal_cm5_app.py` (CPU, native RTAB-Map) and `modal_station_app.py` (GPU, SAM 3.1): `web_server`, one container, token secret; commands in `surmap.survey.modal_hosting`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs, then open the PR ready ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/modal.md` — hosting the CM5 sim and the station, the token secret, URLs
  - [ ] `docs/deployment.md` — WebSocket endpoint, auth flag, verify scripts' URL form
  - [ ] `docs/connectrpc.md` — the WebSocket route, keepalive, auth, bounded memory on long streams
  - [ ] `docs/architecture.md` §10 — transport and GPS on the Board API
  - [ ] Close `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md`
  - [ ] Changelog entry in `docs/surmap/changelog/`

## Initial Discovery

[2026-11-03-survey-websocket-modal-hosting-initial-discovery.md](./2026-11-03-survey-websocket-modal-hosting-initial-discovery.md)
— the Connect-over-WebSocket protocol is already in `surmap.rpc.socket_rpc` with no consumer; the
server kit already routes WebSockets; every survey client is synchronous over h2c or `http.client`.

## Prerequisites

### Deferred TODOs

| Record | Verdict | Outcome |
|---|---|---|
| `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md` | **In scope** — the simulated drone sends GPS over RPC | closed at wrap |
| `src/surmap/docs/todo/2026-10-27-live-ros2-connectrpc-bridge.md` | Not in path (ROS 2 bridge) | — |
| `src/surmap/docs/code-issues/oversized-file-demo-server.md` | Touched only at its Remote* call sites; no restructure needed | — |

## Summary

The simulated drone (the CM5 survey server, with stereo frames and GPS fed by an external
simulator over RPC) and the base station can run as Modal containers. Both servers serve their
Connect services over one WebSocket per client, which Modal carries on a stable HTTPS URL, and
every survey client (the demo's remote adapters, the verify scripts) talks to them that way with
an asyncio client.

## Background

Modal's stable endpoint URLs carry HTTP/1.1 and WebSockets; each HTTP request is capped at 150 s.
HTTP/2 only reaches a container through a tunnel, which has a random URL per container. The
survey services are bidi streams that last a whole survey, which Connect over HTTP needs HTTP/2
for. Connect multiplexed over one WebSocket removes both limits, and also guarantees that
`StreamRegionPoints` reaches the container whose ring buffer holds the frames sent on
`StreamSurvey`, because both calls ride the same socket. Modal endpoint URLs are public, so the
servers need a bearer token. Modal cannot run Docker inside a container, so the CM5 image builds
RTAB-Map natively. There is no Coral on Modal; the CM5 app runs `--detector none` (or
`--coral-cpu`).

## Scope

In:
- Server: WebSocket route, keepalive pings, bearer auth — in `surmap.rpc`, used by `cm5_main` and `station_main`.
- Client: one asyncio WebSocket client for both services; the demo adapters and verify scripts switched to it.
- Contract: GPS fixes in, GPS anchors out, on `StreamSurvey`.
- Deploy: two Modal app files plus a no-`sudo` native RTAB-Map build.

Out:
- The agent server (`surmap.agent`) and the chat UI stay on Connect over HTTP.
- Connect over HTTP stays served on both survey servers (on-prem deploys keep working); only the clients switch.
- MAVLink / UDP ingestion; flight control of any kind (architecture §1).
- Session persistence on a Modal Volume — the CM5 server keeps no session store today.

## Technical Changes

### State A (Current)

- `surmap.rpc.socket_rpc` is a complete Connect-over-WebSocket peer with no consumer.
- `cm5_main` / `station_main` serve Connect over HTTP (h1/h2c) on hypercorn; no auth.
- Survey clients: raw h2c (`StreamSurvey`), `http.client` (`StreamDetections`, `StreamAnalysis`,
  `GetCapabilities`), all synchronous with threads.
- `Cm5Request` carries config and frames only.
- `scripts/build_rtabmap_native.sh` assumes `sudo`.

### State B (Target)

- `HypercornHost(..., connect_websocket_path="/connect", auth_token=..., websocket_ping_interval_s=...)`:
  the path serves every composed Connect app through a `SocketRpcPeer` (acceptor role) per
  socket; hypercorn pings sockets; when a token is set, Connect HTTP requests and WebSocket
  upgrades without `Authorization: Bearer <token>` are refused (HTTP 401 / close before accept);
  `/health/*` stays open.
- `surmap.survey.ws_client.SurveyConnection`: `async with SurveyConnection.open(url, token=...)`
  dials once and exposes `capabilities(service)`, `stream_survey(requests)`,
  `stream_detections(requests)`, `stream_region_points(queries)`, `stream_analysis(requests)` as
  async iterators. `host:port` means `ws://host:port/connect`; `http(s)://` maps to `ws(s)://`.
- `Cm5Request.gps` (`GpsFix`: `t_ns`, `lat`, `lon`, `alt_m`, `accuracy_m`) → `Cm5Response.gps_anchor`
  (`GpsAnchorOut`: the fix, plus `frame_id` and `map_position` of the posed frame nearest in time
  within 0.5 s, absent otherwise).
- `surmap.demo.remote` runs its calls on one background asyncio loop over `SurveyConnection`; its
  public classes and the demo server call sites keep their shapes.
- `src/surmap/survey/modal_cm5_app.py`, `src/surmap/survey/modal_station_app.py`: `@modal.web_server`
  on port 8080/8081 running the existing mains bound to `0.0.0.0` with `/connect`,
  `max_containers=1`, long `timeout`, the `surmap-survey` secret providing `SURMAP_SURVEY_TOKEN`.

### Delta (What's Changing)

| Path | Change |
|---|---|
| `src/surmap/rpc/hosts/hypercorn.py`, `src/surmap/rpc/_listener.py` | WebSocket Connect route, ping interval, auth |
| `src/surmap/rpc/socket_rpc/serve.py` (new) | ASGI WebSocket handler that runs an acceptor peer over given apps |
| `src/surmap/survey/ws_client.py` (new) | asyncio survey client |
| `proto/surmap/survey/v1/survey.proto`, `src/surmap/survey/v1/survey_pb2.py{,i}` | GPS messages |
| `src/surmap/survey/cm5_server.py` | GPS anchors |
| `src/surmap/survey/cm5_main.py`, `station_main.py` | `/connect`, `--auth-token` |
| `src/surmap/demo/remote.py` | WebSocket client; h2c and `http.client` removed |
| `scripts/verify_cm5.py`, `scripts/verify_station.py` | WebSocket client, URLs, `--token` |
| `scripts/build_rtabmap_native.sh` | `sudo` only when not root |
| `src/surmap/rpc/_asgi_internal.py`, `src/surmap/rpc/socket_rpc/peer.py` | streamed replies forwarded and forgotten, not held until the call ends |
| `src/surmap/survey/gps.py`, `src/surmap/survey/endpoint.py`, `src/surmap/slam/regions.py` (`StreamRegionRouter`) (new / extended) | GPS anchoring, endpoint constants, per-stream region routing |
| `src/surmap/survey/modal_hosting.py` (new) | what the Modal apps run (typed, tested) |
| `pyproject.toml` | the two new Modal app modules join `modal_sam_app` in the mypy override (CI has no `modal`) |
| `src/surmap/survey/modal_cm5_app.py`, `modal_station_app.py` (new) | Modal deploy targets |

## Verification

**Behaviour — V1 fail→pass.** New acceptance tests drive real hypercorn hosts on loopback through
real `websockets` connections: unary and bidi Connect calls over `/connect`, an idle socket kept
open by pings, auth refusals, CM5 survey + region points + GPS anchors and station analysis
through `SurveyConnection`, and the demo remote adapters against those servers.
**Command:** `uv run pytest -q tests/rpc/it/test_connect_websocket.py tests/test_survey_ws_client.py tests/test_survey_gps.py tests/test_demo_remote.py tests/test_modal_survey_apps.py tests/test_survey_region_points.py tests/test_verify_cm5.py tests/test_verify_station.py`
**Before:** red @ the Red commit — `tests/rpc/it/test_connect_websocket.py` 6 failed
(`ServerDescription` has no `connect_websocket_path`; `HypercornHost` has no `auth_token`),
`tests/test_survey_gps.py` 4 failed (`survey_pb2` has no `GpsFix`), `tests/test_demo_remote.py` 9
failed and `tests/test_verify_{cm5,station}.py` 4 failed (no `auth_token` on the host the switched
tests start), and `tests/test_survey_ws_client.py`, `tests/test_modal_survey_apps.py`,
`tests/test_survey_region_points.py` not importable (`surmap.survey.ws_client`,
`surmap.survey.modal_hosting`, `cm5_main.describe` missing).
**After:** all pass; full gates green.

**Modal hosting — V4 (needs consent).** No harness here reaches Modal. Procedure:
1. `modal secret create surmap-survey SURMAP_SURVEY_TOKEN=<token>`.
2. `modal deploy src/surmap/survey/modal_cm5_app.py` and `modal_station_app.py`; note the two `modal.run` URLs.
3. `uv run python scripts/verify_cm5.py wss://<cm5-url> --token <token>` and `uv run python scripts/verify_station.py wss://<station-url> --token <token>`.
4. One survey stream held open for more than 150 s (`--frames` large enough) to prove the WebSocket is not cut at the HTTP cap.
5. `modal app stop` both apps.
Evidence: the scripts' output (rates, device line), the stream's duration.
**Approved:** pending — to be asked before the Wrap row.

## Testing Plan

- Real sockets, no mocks of the transport: hypercorn on `127.0.0.1:0`, `websockets` client, the
  in-memory SLAM/detector adapters the servers already default to.
- The Modal app files are checked with the AST (CI never imports `modal`), as `tests/test_modal_sam.py` does.
- Existing `tests/test_demo_remote.py` cases are switched to the new transport rather than duplicated.

## Acceptance Tests

### surmap

- `tests/rpc/it/test_connect_websocket.py`
  - a unary call over `/connect` reaches the composed service
  - a bidi call interleaves requests and responses over one socket
  - an idle socket stays open past the proxy idle window because the host pings it
  - with a token set: a WebSocket without it is refused, with it is served; Connect HTTP without it answers 401; health stays open
- `tests/test_survey_ws_client.py`
  - `SurveyConnection` reports CM5 and station capabilities
  - a CM5 survey streams points back while frames are still being sent
  - region points for a frame sent on the same connection's survey stream
  - station analysis answers one response per frame with its `frame_id`
  - `host:port`, `http://`, `https://` addresses resolve to the `/connect` WebSocket URL
- `tests/test_survey_gps.py`
  - a GPS fix after a posed frame is answered with that frame's map position
  - a fix with no pose within 0.5 s is answered without a map position
  - a server that predates GPS (frames only) still serves a stream that carries fixes (oneof skip)
  - region points reach the backend built for the open survey stream (same connection)
- `tests/test_survey_region_points.py` — the live mode without a calibration dir serves streaming SLAM and region points; the sidecar mode still needs one (replaces "the live mode needs a calibration dir", a requirement this change lifts)
- `tests/test_demo_remote.py` — existing scenarios over the WebSocket endpoint; the detection source reaches a token-guarded CM5
- `tests/test_verify_cm5.py`, `tests/test_verify_station.py` — the server-backed checks over the WebSocket endpoint
- `tests/rpc/unit/socket_rpc/test_socket_rpc_long_streams.py` — a 100 MiB bidi stream keeps the serving side under 32 MiB peak (added in green: the leak was found while wiring the transport)
- `tests/test_modal_survey_apps.py` — both app files define `app` and a `web_server` function with `max_containers=1`, read the `surmap-survey` secret, and run the right main with `/connect`

## Decisions & Trade-offs

- **GPS in-band on `StreamSurvey`**, not a separate stream: same clock and ordering as frames, one
  call for the simulator, and the anchor needs the stream's poses anyway.
- **Bearer token, not Modal proxy auth**: proxy auth headers are Modal-specific; a server-side
  token works the same on Modal and on-prem.
- **Clients switch fully to WebSocket; servers keep HTTP too**: on-prem consumers outside this repo
  keep working, and nothing in the repo still needs the HTTP path.
- **One PR**, as asked.
- **Calibration over RPC.** No camera calibration is committed, and a simulated drone already
  sends its camera definitions in `Cm5StreamConfig`, so the live mode no longer requires
  `--calibration-dir`; without it, a stream that brings none is refused.
- **Native RTAB-Map in the CM5 image** so the simulated drone produces real poses and region points.
