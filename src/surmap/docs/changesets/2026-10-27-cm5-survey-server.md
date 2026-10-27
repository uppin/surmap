# CM5 survey server

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `stream_survey` and `cm5_service_module` in
`surmap.survey.cm5_server`, plus the `ObjectPointSource` port and its
in-memory adapter. Frames pair by `frame_id`; scene points take
designation 1, object points their per-object designation, all through
the incremental emitter; requested channels echo as video.
Verification: V1 fail→pass handler integration tests (385 passed at
wrap, mypy strict and Ruff clean).
