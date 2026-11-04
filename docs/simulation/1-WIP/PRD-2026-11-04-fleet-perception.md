# Only the active drone is mapped and segmented, each drone into its own map - PRD

**Date**: 2026-11-04
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Bevy disaster simulation ([bevy-simulation.md](../bevy-simulation.md)) — the live stereo stream
- **Related Feature**: [Survey agent](../../agent.md) — fleet tools
- **Related Feature**: Streaming RTAB-Map ([architecture.md](../../architecture.md) §4)

## Summary

The simulation page streams the **active drone's** stereo frames to the station. The station keeps
**one RTAB-Map session and one segmentation run per drone**. Only the active drone's frames are
processed; the other drones keep flying and nothing is computed for them.

When the agent switches the active drone, the previous drone's map is kept. Switching back resumes
that same map. Because its camera was away, RTAB-Map starts a new piece of the map, which joins
the earlier one once the drone sees a place it has already mapped.

The agent can ask how each drone's map and segmentation are doing.

## Proposed Changes

### What's Changing

- **Streaming from the page.** A page opened with `?bridge=ws://<station>:8773` streams the active
  drone's frames, at the camera's rate, to the station's stereo bridge. Each frame carries the
  drone's id. Frames are dropped, never queued without bound, when the link is slow. This is the
  live stream the simulation docs list as not yet built.
- **The bridge keeps a session per drone:**
  - an RTAB-Map backend, created the first time that drone's frames arrive;
  - a segmentation run on its left frames;
  - frame, posed, lost, keyframe and segmented-frame counts.

  A drone whose frames stop is idle; its backend and map stay alive. When its frames resume, they
  go into the same backend. At most four drone sessions are live per page. A fifth drone's frames
  are refused with a status message naming the limit.
- **The station starts the bridge** with `python -m surmap.agent --bevy-bridge-port 8773`.
- **On-page status.** The page shows the bridge's status for the active drone: its id, frames,
  keyframes and whether it is tracking.
- **New tool, `drone_map_status`.** It reports each drone's session: frames, posed, lost,
  keyframes, segmented frames, whether it is the drone being processed, and its last frame time.

### What's Staying the Same

- Recorded captures, `--record`, and the existing bridge protocol. A frame without a drone id is
  the single default drone, as today.
- Object points stay layered on RTAB-Map's output. Moving objects are never fused into the static
  map. SurMap still only consumes frames.

## Acceptance Criteria

1. Frames from two drones, interleaved in blocks as the active drone switches, go only to their
   own drone's map. Each map sees only its own drone's frames.
2. After a switch away and back, the first drone's frames continue in the same RTAB-Map session
   (same backend, counts continue). With the real sidecar, both drones' maps gain keyframes.
3. Segmentation runs on the processed drone's left frames only, counted per drone.
4. A frame without a drone id is processed as today, so recorded captures and old pages are
   unaffected.
5. A fifth drone is refused with a status naming the limit, and the first four keep working.
6. Closing the page finishes every drone session and closes every backend.
7. `drone_map_status` reports each drone's counts and which drone is being processed.
8. In Chrome, switching the active drone with `set_active_drone` moves the status overlay to the
   new drone, and `drone_map_status` shows both drones' maps (V4 procedure, recorded).

## Out of Scope

- Merging the per-drone maps into one fleet map (multi-session RTAB-Map across processes).
- Feeding the simulation's poses to RTAB-Map as odometry. The maps stay visual-odometry only,
  like a real drone.
- Real SAM in the agent process. Until the `agent-cli-sam-flags` TODO is done, the agent runs
  with the fake detector; the segmentation seam is the station's SAM detector interface.
