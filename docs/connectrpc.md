# ConnectRPC client/server support (`surmap.rpc`)

ConnectRPC (connect-python) serving and calling for SurMap's Python code —
for example, the base station calling services on the on-board computer, or
a survey service exposing its API to the base station and simulation
machine. Imported as a product-blind serving kit and adapted to this repo:
no product, company or internal-infrastructure names remain, and the code
follows SurMap's stack (Python 3.11+, uv, Ruff, mypy strict, pytest).

## Layout

| Path | What |
|---|---|
| `src/surmap/rpc/compose.py` | Compose a service from **bricks**; coverage gaps/overlaps are refused by name |
| `src/surmap/rpc/description.py` | `ServerDescription` — services, HTTP and WebSocket routes, closeables; static shape, lazy dependencies |
| `src/surmap/rpc/hosts/` | `HypercornHost` (real sockets) and `InMemoryHost` + `ServiceClient` (in-process, for tests) |
| `src/surmap/rpc/asgi.py` | In-process Connect driver: unary, server/client streaming, bidi |
| `src/surmap/rpc/socket_rpc/` | Connect over one WebSocket, multiplexed both directions (`SocketRpcPeer`: serving half in `peer.py`, calling half in `_calls.py`, shared call state in `_types.py`); `connect_websocket_app` serves a host's services on a WebSocket path |
| `src/surmap/rpc/http_rule/` | `google.api.http` REST transcoding over the Connect services |
| `src/surmap/rpc/routes.py` | Shared `/health/is_alive` and `/metrics` (Prometheus text format) routes |
| `src/surmap/rpc/testkit/` | `RecordingBrick`, HTTP stub host for tests |
| `proto/surmap/transport/v1/socket_rpc.proto` | The socket-RPC frame protocol (`surmap.transport.v1`) |
| `src/surmap/transport/v1/socket_rpc_pb2.py` | Generated bindings (checked in; see below) |
| `proto/surmap/survey/v1/survey.proto` | The survey streaming contract (`surmap.survey.v1`): CM5 + station BIDI services, including `Cm5SurveyService.StreamRegionPoints` (dense points under a SAM polygon) and `CameraCalibrationService.StreamCalibration` (checkerboard calibration: capture plan first, then stereo frames in, per-view feedback (filled viewpoint) + next-pose suggestion out, solved calibration on finish; detection/solving in the OpenCV sidecar `surmap.calibration.opencv_sidecar`, enabled with `cm5_main --calibration`; see [camera-calibration.md](camera-calibration.md)) |
| `src/surmap/survey/v1/survey_pb2.py` | Generated bindings (checked in; regenerate with `scripts/gen_survey_rpc.py`) |
| `proto/surmap/agent/v1/*.proto` | The survey agent's tool and chat services (`surmap.agent.v1`); see [agent.md](agent.md) |
| `src/surmap/agent/proto/` | Generated bindings and descriptor set (checked in; regenerate with `scripts/gen_agent_rpc.py`) |

## Shape of use

```python
description = ServerDescription(services=(ServiceModule(descriptor, bricks),),
                                http_routes=health_routes(is_draining))
host = InMemoryHost(description, context)      # tests / simulation
reply = await host.client(descriptor).unary("Unary", request, headers)
# or, for real sockets:
host = HypercornHost(description, context, port=8080)
```

A method no brick claims, or two bricks claim, is a composition error at
mount time — never a runtime 404.

## Connect over one WebSocket

`ServerDescription(connect_websocket_path="/connect")` makes `HypercornHost`
serve every composed service a second way: over one WebSocket at that path,
one `SocketRpcPeer` (acceptor role) per socket, calls multiplexed by stream id
(`surmap.transport.v1.SocketFrame`). Connect over HTTP keeps working beside it.
Clients dial with a dialer `SocketRpcPeer` over `WebSocketFrames`; the survey
services wrap that as `surmap.survey.ws_client.SurveyConnection`.

Why it exists: bidi Connect over HTTP needs HTTP/2 end to end, and some hosts
(Modal's web endpoints) carry only HTTP/1.1 and WebSockets, with a cap per
HTTP request. A WebSocket carries bidi streams for as long as the socket lives,
and every call on it reaches the same server process.

- **Greeting.** The server's first frame is empty; a dialer waits for it
  before calling. Empty frames carry no request or response, and peers skip
  them.
- **Keepalive.** `HypercornHost(websocket_keepalive_s=20.0)` sends an empty
  frame on every socket that often, so a proxy that drops idle connections
  keeps it. The task ends with its socket. Hypercorn's own
  `websocket_ping_interval` is not used: its ping loop outlives a closed socket
  by up to one interval and holds shutdown for the graceful timeout.
- **Auth.** `HypercornHost(auth_token=...)` requires
  `Authorization: Bearer <token>` on Connect over HTTP (else 401) and on the
  WebSocket upgrade. A tokenless socket is accepted, told the text frame
  `unauthorized`, then closed with 4401. The refusal travels inside the socket
  because a proxy in front can turn an HTTP 401 on the upgrade into an error of
  its own (Modal answers 500) and rewrite close codes (Modal sends 1000).
  `/health/*` and other plain routes stay open.
- **Long streams.** A streamed call forwards each reply and forgets it: neither
  the ASGI collector nor the peer keeps the replies it already sent
  (`tests/rpc/unit/socket_rpc/test_socket_rpc_long_streams.py`: 100 MiB through
  one bidi call under 32 MiB peak).
- **Frame size.** Bodies travel in 256 KiB chunks, under the `websockets`
  default of 1 MiB per message and Modal's 2 MiB. Clients should not negotiate
  `permessage-deflate`; Modal refuses it.

## Regenerating the bindings

After editing the `.proto`:

```bash
uv run --with "grpcio-tools==1.76.0" python scripts/gen_socket_rpc.py
uv run --with "grpcio-tools==1.73.1" python scripts/gen_agent_rpc.py   # surmap.agent.v1
```

The generated module and stub are checked in and excluded from Ruff
(per-file ignores in `pyproject.toml`); mypy reads the generated `.pyi`.

## Dependency notes

- `connectrpc==0.12.1` is pinned, as in the source import.
- `protobuf` is held at `>=6.33,<7` and `protobuf-py==0.5.0`: newer
  `protobuf-py` releases removed `protobuf.wkt.api_pb`, which
  connectrpc 0.12.1 imports, and protobuf 7 gencode cannot load under
  the 6.x runtime. Revisit both pins when connectrpc is upgraded.
- Tests for the kit live under `tests/rpc/` (359 tests repo-wide pass).
  Two source tests were not imported: they asserted against a specific
  product's generated service descriptors, which do not exist here; the
  generic convention they covered is exercised on fixture services in
  `tests/rpc/unit/http_rule/test_http_proto_conventions.py`.
