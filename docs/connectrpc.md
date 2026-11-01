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
| `src/surmap/rpc/socket_rpc/` | Connect over one WebSocket, multiplexed both directions (`SocketRpcPeer`) |
| `src/surmap/rpc/http_rule/` | `google.api.http` REST transcoding over the Connect services |
| `src/surmap/rpc/routes.py` | Shared `/health/is_alive` and `/metrics` (Prometheus text format) routes |
| `src/surmap/rpc/testkit/` | `RecordingBrick`, HTTP stub host for tests |
| `proto/surmap/transport/v1/socket_rpc.proto` | The socket-RPC frame protocol (`surmap.transport.v1`) |
| `src/surmap/transport/v1/socket_rpc_pb2.py` | Generated bindings (checked in; see below) |
| `proto/surmap/survey/v1/survey.proto` | The survey streaming contract (`surmap.survey.v1`): CM5 + station BIDI services, including `Cm5SurveyService.StreamRegionPoints` (dense points under a SAM polygon) |
| `src/surmap/survey/v1/survey_pb2.py` | Generated bindings (checked in; regenerate with `scripts/gen_survey_rpc.py`) |

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

## Regenerating the bindings

After editing the `.proto`:

```bash
uv run --with "grpcio-tools==1.76.0" python scripts/gen_socket_rpc.py
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
