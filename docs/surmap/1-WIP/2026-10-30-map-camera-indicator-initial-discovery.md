# Initial Discovery: camera indicator on the live floor plan

**Changeset**: [2026-10-30-map-camera-indicator.md](./2026-10-30-map-camera-indicator.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- The floor plan is drawn from `map` events (~3/s, `_map_event`): sampled
  cloud `[x, z, r, g, b]` and trajectory `[x, z]` of graph poses; nothing
  marks where the camera is now or which way it faces.
- Each live frame is released by `_Display` once its own `OdomUpdate`
  arrived (`frame_odometry`), so that frame's pose is known exactly when
  the frame is shown — a camera marker can ride on the frame event and
  stay in sync with the video.
- Poses are in RTAB-Map's optical-world frame (x right, y down, z
  forward); the camera's forward axis is the rotation's third column, its
  floor-plane heading `(r02, r22)`.
- The horizontal field of view follows from the display calibration:
  `2·atan(width / 2 / fx)`.

## Exploration 1: map event and frame release — 2026-10-30

**Agent**: parent Grep/Read
**Scope**: where a per-frame camera pose is available

### Sequence

1. Grep `def _map_event`, `def _floor_plane_trajectory` in `src/surmap/demo/server.py`.
2. Grep `last_odom_frame|def frame_odometry` in `src/surmap/slam/streaming.py`.

### Inspected files

#### `src/surmap/demo/server.py`

```python
"cloud_xy": _floor_plane_cloud(cloud),
"trajectory_xy": _floor_plane_trajectory(trajectory),
```

### Findings

The frame release path already holds the frame's `OdomUpdate`.
