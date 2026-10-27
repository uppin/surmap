# Initial Discovery — CM5 incremental point emitter (n2)

## Combined Conclusions

- Whole-work pass: see Exploration 1 (copied from the stack discovery).
- `FrameResult.static_points` is a per-frame tuple of map-frame `Vec3`
  (`src/surmap/slam/base.py`); `ObjectPoints` carries per-track map-frame
  points (`src/surmap/types.py`). Nothing deduplicates points across
  frames today — every frame's points would be resent in full.
- The emitter is pure domain logic over `Vec3`: it needs no proto types
  (designation arrives as an `int`), so it is startable in wave 1 against
  n1's planned designation constants only at the signature level.
- Deferred-work scan: no `src/surmap/docs/{todo,code-issues,deferred-answers}/`;
  nothing carries into this node's Prerequisites.

## Exploration 1 — whole-work pass (2026-10-27)

Sequence: read `pyproject.toml`, `README.md`, `docs/architecture.md`
(§§2–6, 10), `docs/connectrpc.md`, `proto/surmap/transport/v1/socket_rpc.proto`,
`src/surmap/types.py`, `src/surmap/slam/{base,fake}.py`,
`scripts/gen_socket_rpc.py`, `src/surmap/rpc/{compose,description}.py`,
`tests/rpc/echo_service.py`, `tests/test_slam.py`; grepped `overstack`
across `.agents/ docs/ src/ tests/ scripts/`; listed `docs/`, `src/surmap/`,
`tests/`; checked `gh` auth, default branch (`main`), and the
deferred-work directories.

Established: no survey/SAM service, proto, tracker, or SAM code exists;
the ConnectRPC kit composes services from protobuf descriptors; domain
contracts (`Vec3`, `ObjectPoints`, `SlamBackend`) already exist. State A
in the changeset is distilled from this.
