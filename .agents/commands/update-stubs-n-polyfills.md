---
description: Analyze and update stub/fake implementations
---

## Update Stubs and Fakes

Keep test doubles in `tests/` and `src/surmap/` honest against the real
dependencies they stand in for. SurMap's canonical example is the SLAM seam:
`RtabmapBackend` wraps the system RTAB-Map binding (no PyPI package), and
tests use `InMemorySlamBackend` plus stub bindings instead.

### 1. Identify what is stubbed and why

- The real dependency and where it is loaded (e.g. `_load_binding` in
  `src/surmap/slam/rtabmap.py`).
- The port it sits behind (`SlamBackend` protocol in `src/surmap/slam/base.py`).
- Which tests use the fake, and what behaviour they rely on.

### 2. Compare the fake against the real adapter

Read the real adapter and the fake side by side. Check: method signatures,
return contracts (`FrameResult` fields), error behaviour
(`RtabmapUnavailable` when the binding is absent or has no factory), and
lifecycle (`close()` semantics, `closed` flag). `tests/test_slam.py`'s
`StubSession` is the model: it asserts the arguments it receives and
returns contract-shaped values.

### 3. Update the fake

- Match the port, not the vendor API: fakes implement `SlamBackend`,
  never RTAB-Map's native surface.
- Record what tests need to assert (trajectory, calls, closed state);
  return fixed, deterministic values — no randomness, no wall clock.
- If the real adapter gained a behaviour the fake cannot express, say so
  and extend the port deliberately rather than bolting vendor details on.

### 4. Verify

```bash
uv run pytest -q          # includes the adapter tests against stub bindings
uv run ruff check src tests
uv run mypy               # strict, covers tests too
```

Report: which fake changed, which contract drift it fixes, and which
tests prove the fake and the real adapter agree on the port.
