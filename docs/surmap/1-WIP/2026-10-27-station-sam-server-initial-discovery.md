# Initial Discovery — station SAM server (n5)

## Combined Conclusions

- Whole-work pass: see Exploration 1 (copied from the stack discovery).
- The server is the station twin of n4: same config-first BIDI input
  shape (n1), enforced by n3's `AnalysisGate`, answering with n1's
  `SamFrameDetections` keyed by the sender-assigned `frame_id`.
- Concurrency is the design point: under `EVERY_FRAME` frames are
  analyzed serially in arrival order (lag accepted); under
  `BEST_EFFORT_DROP` a second concurrent analysis is never started — a
  frame arriving while one is in flight is skipped, and no response is
  emitted for it (the drop is visible as a missing `frame_id`, counted
  server-side by the gate). Responses therefore carry `frame_id` so the
  requester can reconcile.
- Real SAM 3.1 arrives later behind n3's `SamDetector` port; tests use
  `InMemorySamDetector` and a controllably slow fake.
- Deferred-work scan: no records; nothing carries into Prerequisites.

## Exploration 1 — whole-work pass (2026-10-27)

Sequence: read `pyproject.toml`, `README.md`, `docs/architecture.md`
(§§2–6, 10), `docs/connectrpc.md`, `proto/surmap/transport/v1/socket_rpc.proto`,
`src/surmap/types.py`, `src/surmap/slam/{base,fake}.py`,
`scripts/gen_socket_rpc.py`, `src/surmap/rpc/{compose,description}.py`,
`tests/rpc/echo_service.py`, `tests/test_slam.py`; grepped `overstack`
across `.agents/ docs/ src/ tests/ scripts/`; listed `docs/`, `src/surmap/`,
`tests/`; checked `gh` auth, default branch (`main`), and the
deferred-work directories.

Established: no survey/SAM service exists; SAM is station-only
(§3.1); the ConnectRPC kit serves BIDI from a descriptor; ports ship
with in-memory adapters (`SlamBackend`/`InMemorySlamBackend`). State A
in the changeset is distilled from this.
