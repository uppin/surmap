# Photo-real Bevy simulation with runtime content, verified against RTAB-Map

**Date:** 2026-11-03
**Feature:** Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md)) · PR #89

The browser PoC became a photo-real, fully declarative simulation and a stereo source
RTAB-Map is judged on. `scene.json` declares the whole block — environment, textured and
solid materials, elements (boxes, collapsed buildings, windowed buildings, survivors) and
glTF models — and the page loads it, every CC0 Poly Haven texture and model (pinned by
SHA-256, fetched by `scripts/fetch_sim_assets.py`, never committed) and an HDRI sky at
runtime: composing a simulation needs no rebuild. Look: tiled PBR with ARM maps and CPU mip
chains, HDRI skybox and image light on every camera (Bevy 0.18's `Atmosphere` serves only
one), cascaded shadows, haze, AgX, fixed exposure.

The stereo rig is one runtime camera profile (`cameras/*.camera.json`) for the renderer and
for RTAB-Map: the eyes render with its exact intrinsics, the capture and the wire hello carry
it, and the EuRoC `sensor.yaml` is derived from it. A native recorder flies the scripted
survey loop and writes captures through GPU readback; review stills come from
`--screenshot`.

Acceptance against the real sidecar over a committed 90-frame capture: every frame tracked,
odometry drift 2.7 % over 13.4 m with the map anchored once to the truth, dense polygon points
on a car within a quarter pixel of disparity of its true surface. Over the full 182 m loop
odometry closed to 0.81 %, but RTAB-Map's map-corrected pose did not — traced to the
streaming sidecar passing identity odometry covariance. With the developer's consent
("wrap the PR with TODO and we'll address the correctness in next PRs") that fix, the loop
acceptance, the live WebSocket stream, visual checkpoints V3–V5 and fisheye profiles are
recorded in `src/surmap/docs/todo/2026-11-03-*`.

Development: Muse Code (via `#muse`) wrote the red tests and the first contracts; the
planner owned every visual decision (asset picks from contact sheets, review of each
screenshot checkpoint) and implemented the rest after `#muse` was turned off.
