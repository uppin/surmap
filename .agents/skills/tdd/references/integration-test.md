---
description: Integration test guidelines for SurMap
---

# Integration Tests

- Cover the seams unit tests cannot: stereo/geometry/motion pipelines wired
  together, SLAM backend interface against its in-memory implementation,
  recorded-session replay.
- Still hermetic by default: no real camera, GPS, Edge TPU or RTAB-Map
  install required in CI. Native/hardware paths sit behind adapters and are
  exercised with fakes or recorded fixtures.
- Keep integration tests fast and deterministic; mark genuinely slow or
  hardware-bound checks explicitly rather than letting them slow the suite.
- Run the full gate before handoff: `uv run pytest -q`,
  `uv run ruff check src tests`, `uv run mypy`.
