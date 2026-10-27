# Initial Discovery — CM5 survey server (n4)

## Combined Conclusions

- Whole-work pass: see Exploration 1 (copied from the stack discovery).
- The server composes three owned-elsewhere pieces: n1's
  `Cm5SurveyService` descriptor, `SlamBackend` (existing port,
  `InMemorySlamBackend` as test adapter), and n2's emitter. Object points
  need a new port in the SLAM hexagon's shape: `ObjectPointSource`
  protocol + in-memory adapter, defined here; the Coral detector/tracker
  and stereo reconstruction that will implement it on hardware are not in
  this stack.
- Pairing: input frames arrive per channel; a stereo pair is complete
  when both channels for one `frame_id` have arrived. Only then does the
  SLAM backend run. Video passthrough re-emits the exact frames of the
  channels named in the stream config, under designations 2/3.
- Serving: `compose_service` + `InMemoryHost` give an in-process BIDI
  test path; handlers can also be driven directly as async generators.
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

Established: no survey/SAM service or tracker exists; `SlamBackend` is
the hexagon reference (port + native adapter + in-memory fake); the
ConnectRPC kit serves BIDI from a descriptor. State A in the changeset
is distilled from this.
