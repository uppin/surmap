# Initial Discovery: Survey RPC over WebSocket, hosted on Modal

**Changeset**: [2026-11-03-survey-websocket-modal-hosting.md](./2026-11-03-survey-websocket-modal-hosting.md)
**Date**: 2026-11-03
**Passes**: 1

## Combined Conclusions

- **Connect-over-WebSocket already exists in the tree, unused.** `surmap.rpc.socket_rpc`
  (`SocketRpcPeer`, `AsgiWebSocketFrames`, `WebSocketFrames`, wire `surmap.transport.v1.SocketFrame`)
  multiplexes unary, client/server-streaming and bidi Connect calls over one socket, with
  auto-chunking and per-call byte bounds, and has unit tests (`tests/rpc/unit/socket_rpc/`). No
  server mounts it and no client dials it.
- **The server kit routes WebSockets.** `ServerDescription.websocket_routes` →
  `HypercornHost._mount` → `build_listener_app` dispatches `scope["type"] == "websocket"` by exact
  path; unknown paths are closed with 1008. The composed Connect apps are built in `_mount`
  (`apps[module.descriptor.full_name]`), so a WebSocket route that serves them needs them from
  the host, not from the description.
- **Hypercorn defaults**: `read_timeout=None`, `keep_alive_timeout=5.0`,
  `websocket_ping_interval=None`. Hypercorn itself does not cut an idle WebSocket, but nothing
  pings it either, so an idle-cutting proxy in front (Modal's edge) would.
- **Survey clients are synchronous and HTTP-bound.** `src/surmap/demo/remote.py` speaks raw h2c
  (`h2.H2Connection`, a reader thread) for the long `StreamSurvey`, and `http.client` send-all /
  read-all exchanges for `StreamDetections`, `StreamAnalysis` and unary `GetCapabilities`. Its
  docstring records why: the Connect Python clients cannot stream a request body against the
  Hypercorn host. `scripts/verify_cm5.py` and `scripts/verify_station.py` use `http.client` too.
  Callers: `src/surmap/demo/server.py` (`RemoteCm5Backend`, `RemoteDetectionSource`,
  `RemoteSamDetector`, `fetch_capabilities`) and `tests/test_demo_remote.py`.
- **Modal constraints** (see the changeset's Background): stable HTTPS URLs carry HTTP/1.1 and
  WebSockets only, with a 150 s cap per HTTP request; HTTP/2 needs a tunnel with a random URL; no
  Docker-in-Docker; tunnel/endpoint URLs are public.
- **GPS is not on the wire.** `surmap.types.GpsCheckpoint(t_ns, lat, lon, alt, accuracy_m)` exists
  and is used offline (EuRoC export, map snapshot). `Cm5Request.kind` is `config | frame` only. The
  open deferred item `src/surmap/docs/todo/2026-10-27-gps-on-survey-wire-proto.md` asks for exactly
  this. `_stream_survey` skips non-`frame` kinds after config, so adding a oneof case is
  backward-compatible for old servers.
- **RTAB-Map without Docker** is already supported: `scripts/build_rtabmap_native.sh` builds a
  pinned RTAB-Map 0.23.1 and the `surmap-rtabmap-stream` tool (uses `sudo apt-get`, `nproc`), and
  `cm5_main --rtabmap-native <binary>` runs it. A Modal image can run the same script as root.
- **Modal app pattern**: `src/surmap/survey/modal_sam_app.py` defines `app`/`image`/functions at
  module scope, is never imported by tests (CI has no `modal`), and `tests/test_modal_sam.py`
  checks it with the AST.

## Exploration 1: transport, servers, clients, Modal fit — 2026-11-03

**Agent**: parent Grep/Glob/Read
**Scope**: `src/surmap/rpc`, `src/surmap/survey`, `src/surmap/demo/remote.py`, `scripts/verify_*`,
`proto/surmap/survey/v1/survey.proto`, `docs/modal.md`, `docs/deployment.md`, `docs/architecture.md` §10

### Sequence

1. Read `docs/architecture.md` §1–§4, §10 — machine roles, Board/GPU API contracts.
2. Read `docs/modal.md`, `docs/deployment.md` — what already runs on Modal; CM5 flags; native RTAB-Map.
3. Read `docs/connectrpc.md` — the server kit layout; found `socket_rpc`.
4. Grep `SocketRpcPeer|socket_rpc` in `src/surmap` (outside the package) — no consumers.
5. Read `src/surmap/rpc/socket_rpc/{__init__,websocket,peer}.py` — API.
6. Grep `websocket` in `src/surmap/rpc/{description,_listener}.py`, `hosts/hypercorn.py` — routing.
7. `uv run python -c 'Config()'` — hypercorn timeout and ping defaults.
8. Grep `StreamSurvey|StreamAnalysis|StreamRegionPoints|StreamDetections` in `src scripts` — clients.
9. Read `src/surmap/demo/remote.py` — client transports.
10. Grep `RemoteCm5Backend|RemoteDetectionSource|RemoteSamDetector|fetch_capabilities` — callers.
11. Read `proto/surmap/survey/v1/survey.proto` lines 80–175 — request/response oneofs.
12. Read `src/surmap/survey/cm5_server.py` `_stream_survey` — where GPS would join poses.
13. Grep `GpsCheckpoint` in `src` — offline only; read the deferred GPS TODO.
14. Read `scripts/build_rtabmap_native.sh`, `src/surmap/survey/modal_sam_app.py`, `tests/test_modal_sam.py`.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `SocketRpcPeer\|socket_rpc` | `src/surmap` minus the package | none |
| Grep | `websocket` | `src/surmap/rpc` | `description.py:41 WebSocketRoute`, `_listener.py:52`, `hosts/hypercorn.py:68` |
| Grep | `StreamSurvey\|StreamAnalysis\|…` | `src scripts` | `demo/remote.py`, `scripts/verify_cm5.py`, `scripts/verify_station.py`, servers |
| Grep | `Remote*\|fetch_capabilities` | `src scripts tests` | `demo/server.py:72-77,988,1357-1376`, `tests/test_demo_remote.py` |
| Grep | `GpsCheckpoint` | `src` | `types.py:50`, `simulation/*`, `map/snapshot.py`, `mission/demo.py` |
| Glob | `tests/*modal*` | `tests` | `test_modal_sam.py`, `test_modal_muse.py` |

### Inspected files

#### `src/surmap/rpc/socket_rpc/peer.py`

**Why**: the API a server route and a client would use.
**Excerpt**:

```python
class SocketRpcPeer:
    def __init__(self, socket: FrameSocket, *, role: PeerRole,
                 applications: Mapping[str, ConnectASGIApplication[Any]] | None = None,
                 chunk_size: int = DEFAULT_CHUNK_BYTES, max_call_bytes: int = DEFAULT_MAX_CALL_BYTES) -> None:
    async def serve(self, *, when_ready: asyncio.Event | None = None) -> None:
    async def call_unary(...)
    def call_server_stream(...)
    def call_bidi_stream(...)
    async def close(self) -> None:
```

#### `src/surmap/rpc/hosts/hypercorn.py`

**Why**: where composed apps exist and WebSocket handlers are mounted.
**Excerpt**:

```python
for module in self._description.services:
    app = compose_service(module.descriptor, *bricks)
    apps[module.descriptor.full_name] = app
...
websocket_handlers = {route.path: route.handler(self._context) for route in self._description.websocket_routes}
```

#### `src/surmap/rpc/_listener.py`

**Why**: request dispatch and hypercorn config.
**Excerpt**:

```python
if scope_type == "websocket":
    ws_app = websockets.get(path)
    if ws_app is None:
        await send({"type": "websocket.close", "code": 1008})
...
config = Config()
config.bind = [f"fd://{bind_socket.fileno()}"]
```

#### `src/surmap/demo/remote.py`

**Why**: the clients to switch.
**Excerpt**:

```python
class _SurveyStream:
    """One long-lived `StreamSurvey` exchange over HTTP/2 (h2c).
    The Connect sync/async clients cannot stream a request body
    against the repo's Hypercorn host ..."""
def _exchange(address: str, path: str, requests: list[Any], timeout: float = 60.0) -> list[bytes]:
    connection = http.client.HTTPConnection(address, timeout=timeout)
```

#### `proto/surmap/survey/v1/survey.proto`

**Why**: where GPS joins the stream.
**Excerpt**:

```proto
message Cm5Request {
  oneof kind {
    Cm5StreamConfig config = 1;
    RawVideoFrame frame = 2;
  }
}
message Cm5Response {
  oneof kind { PointBatch points = 1; VideoFrameOut video = 2; OdomUpdateOut odom = 3; }
}
```

#### `src/surmap/survey/cm5_server.py`

**Why**: poses available per stream.
**Excerpt**:

```python
if request.WhichOneof("kind") != "frame":
    continue
...
result = slam.process_frame(pair)
for response in drain_odom():   # OdomUpdate with pose / map_pose per frame
    yield response
```

#### `scripts/build_rtabmap_native.sh`

**Why**: a Docker-free RTAB-Map for a Modal image.
**Excerpt**:

```bash
RTABMAP_TAG="${RTABMAP_TAG:-0.23.1}"
sudo apt-get install -y --no-install-recommends git cmake g++ libpcl-dev libopencv-dev ...
```

### Findings

- The protocol is in place; the gaps are a server route serving the composed Connect apps, a
  keepalive, an auth check, an asyncio client, and the callers switched to it.
- One socket per client session carries `StreamSurvey`, `StreamRegionPoints`, `StreamDetections`
  and `GetCapabilities`, so a region query always reaches the container that holds its frames.
- GPS needs one new oneof case per direction; the server joins a fix to the pose nearest in time.
- The build script needs a no-`sudo` path to run inside an image build as root.
