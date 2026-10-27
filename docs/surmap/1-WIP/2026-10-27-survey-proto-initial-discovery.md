# Initial Discovery — survey proto contracts (n1)

## Combined Conclusions

- No survey/SAM protobuf service exists. The only proto is
  [socket_rpc.proto](../../../proto/surmap/transport/v1/socket_rpc.proto)
  (`surmap.transport.v1`, WebSocket framing, no service definitions).
- ConnectRPC serving is product-blind kit in `src/surmap/rpc/`:
  `compose_service(descriptor, *bricks)` derives endpoints from a protobuf
  `ServiceDescriptor` (all four method kinds), `ServerDescription` /
  `InMemoryHost` / `HypercornHost` host it. A new service therefore needs a
  `.proto`, generated bindings (`*_pb2`), and a descriptor — bricks are
  looked up by method name.
- Generated bindings pattern: `scripts/gen_socket_rpc.py` runs
  `grpc_tools.protoc` with `--proto_path=proto`, outputs checked in under
  `src/`, excluded from Ruff in `pyproject.toml`, read by mypy via `.pyi`.
- Domain contracts already exist as dataclasses in `src/surmap/types.py`
  (`Vec3`, `Pose`, `StereoFramePair`, `Detection`, `Track`, `ObjectPoints`)
  and the SLAM port in `src/surmap/slam/base.py` (`SlamBackend`,
  `FrameResult`). No detector/tracker or SAM code exists yet.
- Deferred-work scan (Step 2b): `src/surmap/docs/{todo,code-issues,deferred-answers}/`
  do not exist; no cross-package record names `surmap`. Nothing to carry as
  Prerequisites. The package has never been code-issue analyzed — noted,
  not clean.
- `overstack` references occur only under `.agents/` (the pr-stack skill,
  plan/add/split/fix/merge stack commands, and `roadmap-cli issue sync`
  lines in `repoint`/`squash-pr`/`yolo-pr-stack`). No `overstack`,
  `issue create/sync`, or `run-cli` tooling exists in this repo.

## Exploration 1 — whole-work pass (2026-10-27)

Sequence: read `pyproject.toml`, `README.md`, `docs/architecture.md`
(§§2–6, 10), `docs/connectrpc.md`, `proto/surmap/transport/v1/socket_rpc.proto`,
`src/surmap/types.py`, `src/surmap/slam/{base,fake}.py`,
`scripts/gen_socket_rpc.py`, `src/surmap/rpc/{compose,description}.py`,
`tests/rpc/echo_service.py`, `tests/test_slam.py`; grepped `overstack`
across `.agents/ docs/ src/ tests/ scripts/`; listed `docs/`, `src/surmap/`,
`tests/`; checked `gh` auth, default branch (`main`), and the
deferred-work directories.

Findings are distilled in Combined Conclusions above. State A in the
changeset is drawn from this file.
