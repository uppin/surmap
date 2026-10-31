# SAM region → dense 3D points — PRD

**Date**: 2026-10-31
**PRD Type**: Enhancement
**Status**: 🚧 In Progress
**Changeset**: [2026-10-31-sam-region-points.md](./2026-10-31-sam-region-points.md)

## Affected Features

- **Primary**: Survey streaming contract (`proto/surmap/survey/v1/survey.proto`,
  `Cm5SurveyService`) — a new BIDI rpc, `StreamRegionPoints`.
- **Primary**: RTAB-Map streaming sidecar (`deploy/rtabmap-stream/main.cpp`,
  `src/surmap/slam/stream_protocol.py`, `src/surmap/slam/streaming.py`) — protocol v4
  region requests answered from a time-bounded ring of rectified pairs.
- **Primary**: CM5 server (`src/surmap/survey/cm5_server.py`, `cm5_main.py`) — serves
  the rpc; gains a live (streaming) RTAB-Map backend mode so poses exist during the stream.
- **Primary**: Browser demo (`src/surmap/demo/`) — a SAM result's mask polygons are
  queried and the region's shape is drawn on the 3D point-cloud pane, replacing the
  previous one.

## Summary

Given a frame id, the channel SAM segmented, and a mask polygon on that channel's image,
the CM5 streams back **every** 3D point stereo can recover inside the polygon, in the map
frame. The shape is computed from that one frame only — no accumulation across frames or
queries — so it appears instantly and reflects exactly what SAM outlined.

## Background

The overlay in the demo shows RTAB-Map's odometry inlier keypoints: sparse corner
features (`Vis/MaxFeatures` 1000), typically 0–30 per SAM mask. RTAB-Map's own 2D→3D
link exists only for those features and only on the left image. The keyframe cloud the
sidecar emits is voxel-downsampled to 5 cm, depth-capped, and keyframe-only. None of these
can give a detailed surface for an arbitrary SAM region on an arbitrary frame.

Dense stereo can: the sidecar already holds the properly rectified pair (full distortion
model) and the frame's pose. Recomputing disparity (OpenCV SGBM) for the polygon's pixels
on demand gives up to one point per pixel inside the mask.

SAM runs on the base station, seconds after the frame; the CM5 must therefore keep recent
frames available and say explicitly when a frame is gone.

## Proposed Changes

### What's Changing

- **Contract** — `rpc StreamRegionPoints(stream RegionQuery) returns (stream RegionPoints)`
  on `Cm5SurveyService`. A query carries `query_id`, `frame_id`, `channel` (0 left /
  1 right — asserts which image SAM segmented), the size of the image the polygon is in,
  and the polygon. Responses repeat `query_id`/`frame_id`/`channel`, carry a status and
  map-frame points, chunked, with `final` on the last chunk of a query.
- **Status is explicit, never a guess**: `OK`, `FRAME_EXPIRED` (not / no longer in the
  ring), `NO_POSE` (tracking was lost on that frame), `INVALID_QUERY` (channel not 0/1,
  fewer than 3 vertices, zero image size).
- **Depth is referenced to the requested channel**: a channel-1 polygon is matched with
  the right image as reference, so the polygon maps pixel-exactly on either channel.
- **Sidecar protocol v4** — a `region` request/response pair; the hello carries the ring
  length in seconds (default 10 s).
- **CM5** — `--slam-backend streaming` runs the live sidecar; it serves `StreamSurvey`
  poses and `StreamRegionPoints`. A server with no region source rejects the stream.
- **Demo** — each SAM result's masks are queried; a `region` SSE event carries the
  points; the 3D pane draws the latest region shape over the cloud, replacing the
  previous one. `--sam-fake` runs a fake SAM (fixed polygon) so the path works without a
  GPU; `--sam-device` keeps using real SAM 3.1.

### What's Staying the Same

- RTAB-Map's map: region points are a read-only layer, never written back (scope
  guardrail, `AGENTS.md`). Moving objects are not fused into the static scene.
- `StreamSurvey`, `StreamDetections`, `StreamMovingAreas`, their messages and
  designations. The batch sidecar and the CM5's `sidecar` / `inmemory` modes.
- The keyframe cloud's 5 cm downsampling and depth cap (it is the live floor-plan feed).

## Acceptance Criteria

1. A region query for a buffered, tracked frame returns map-frame points that, projected
   back into the queried channel with that frame's pose, all fall inside the polygon.
2. A region query returns far more points than RTAB-Map's sparse keypoints inside the
   same polygon (dense, not sparse).
3. The same physical region queried on channel 0 and on channel 1 yields point sets whose
   median nearest-neighbour distance is small (both channels land on the same surface).
4. A query for a frame older than the ring, or never sent, returns `FRAME_EXPIRED`; a lost
   frame returns `NO_POSE`; channel 2 or a 2-vertex polygon returns `INVALID_QUERY`.
5. Points of one query are never mixed into another query's response.
6. Large regions are chunked; the last chunk of each query has `final = true`.
7. In the demo with `--sam-fake`, every SAM result is followed by a `region` event whose
   points the 3D pane draws, replacing the previous region.
8. No new Python dependency; gates green (ruff, format, mypy strict, pytest).

## Out of Scope

- Multi-frame fusion of a region (deliberately: "instant shape without accumulation").
- Meshing the region (`organizedFastMesh`) — a follow-up once the point stream is proven.
- Station-side consumption (the station calling the CM5 with its SAM output).
