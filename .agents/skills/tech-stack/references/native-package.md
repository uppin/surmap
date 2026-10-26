---
description: Native and system-provided dependencies — the RTAB-Map pattern
---

# Native / System-Provided Dependencies

Some dependencies cannot be pip/uv installed. RTAB-Map is the template:

- It has no official PyPI package, so it is **not** a `pyproject.toml`
  dependency. The system RTAB-Map build (or the ROS 2 `rtabmap` packages)
  provides the binding module.
- `surmap.slam.RtabmapBackend` loads that module at runtime and raises
  `RtabmapUnavailable` with install guidance when it is absent.
- Tests and simulation use `surmap.slam.InMemorySlamBackend` instead, so the
  suite never requires the native install.

Apply the same shape to any future native dependency:

1. Keep it out of the installable dependency list; document the system
   prerequisite in `README.md`.
2. Isolate it behind an adapter/interface so the rest of the code depends on
   the interface, not the native API.
3. Provide an in-memory/fake implementation for tests and simulation.
4. Fail with a named, actionable error (what is missing, how to install it),
   never a bare `ImportError` deep in a call stack.
