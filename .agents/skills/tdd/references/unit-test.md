---
description: Unit test principles for SurMap
---

# Unit Tests

- pytest, under `tests/`, mirroring the module under test
  (`src/surmap/geometry.py` → `tests/test_geometry.py`).
- Test behaviour through the public API; inject dependencies so units run
  without hardware, native libraries or the network. For the SLAM backend,
  test against `surmap.slam.InMemorySlamBackend`, not RTAB-Map.
- One behaviour per test, named for the behaviour it pins down.
- Typed like production code: mypy strict covers `tests/` too.
- Write them fluent where it aids reading — load the `fluent-tests` skill;
  bar in `skills/testing/references/fluent-style.md`.
