# Initial Discovery — station SAM analysis policy (n3)

## Combined Conclusions

- Whole-work pass: see Exploration 1 (copied from the stack discovery).
- No SAM code, detector port, or scheduling policy exists. SAM 3.1 is a
  base-station GPU job (architecture §3.1) whose throughput on the target
  card is unverified — the policy must therefore treat SAM as a scarce,
  possibly slow resource behind a port, with an in-memory fake for tests.
- The two approved modes differ only in admission: `EVERY_FRAME` queues
  and accepts lag; `BEST_EFFORT_DROP` skips a frame when the analyzer is
  busy and counts the drop. That decision is pure policy over a busy flag
  and can be unit-tested without any server or GPU.
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

Established: no survey/SAM service, proto, tracker, or SAM code exists;
domain contracts already exist; SAM runs only on the base station.
State A in the changeset is distilled from this.
