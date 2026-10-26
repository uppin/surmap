---
name: hexagon-testable-architecture
description: Apply hexagonal (ports & adapters) architecture for testable code, using SurMap's SLAM backend as the reference example — a protocol (port), a native adapter (RTAB-Map), and an in-memory adapter for tests and simulation. Use when introducing a dependency on hardware, a native library, a model or an external service, or when a component is hard to test because it reaches such a dependency directly.
---

# Hexagonal Architecture (Ports & Adapters) — SurMap Pattern

SurMap already contains the canonical example. New hardware, native or
service dependencies should follow the same shape.

## The reference hexagon: `src/surmap/slam/`

| Role | SurMap example |
|---|---|
| **Port** (what the domain needs) | `SlamBackend` protocol in `slam/base.py`: `process_frame(frame) -> FrameResult`, `trajectory()`, `close()` |
| **Primary adapter** (real dependency) | `RtabmapBackend` in `slam/rtabmap.py`: loads the system RTAB-Map binding at runtime, raises `RtabmapUnavailable` with install guidance when absent |
| **Test/simulation adapter** | `InMemorySlamBackend` in `slam/fake.py`: fixed pose, no points, records its trajectory; used by tests and session replay |
| **Domain** (never imports the dependency) | `geometry.to_map_frame`, `motion.classify_motion`, and the contracts in `types.py` — pure functions and dataclasses |

## Rules

1. **The domain speaks contracts, not vendor types.** Pipeline code consumes
   `StereoFramePair`, `Pose`, `Detection`, `ObjectPoints` (`types.py`). A
   detector's native output, SAM's masks and the Models API's responses are
   translated into contracts at the adapter edge.
2. **One port per dependency seam.** Object detection (Coral Edge TPU),
   segmentation (SAM 3.1 on the base station), labelling (Models API) and
   GPS/session storage each get a protocol like `SlamBackend` before a
   second implementation appears.
3. **Every port ships with an in-memory adapter.** If a change cannot be
   tested without the Pi, the Coral, RTAB-Map or the network, the adapter
   is missing — add it, as `fake.py` does, instead of mocking internals.
4. **Optional dependencies fail by name.** Follow `RtabmapUnavailable`:
   a specific exception saying what is missing and how to install it,
   raised where the adapter is constructed.
5. **No dependency reaches upward.** Adapters import the domain; the domain
   imports nothing from adapters. RTAB-Map output is registration data —
   and, per the product boundary, never a control signal.

## When to introduce a hexagon

- A new sensor, native library, model runtime or network service enters.
- A test needs `@pytest.mark.skip` because hardware is absent — that is the
  smell this pattern removes.
- Two implementations must coexist (real flight sessions vs synthetic
  simulation sessions, §2.3: indistinguishable in format, different source).

Worked detail and anti-patterns: `REFERENCE.md`.
