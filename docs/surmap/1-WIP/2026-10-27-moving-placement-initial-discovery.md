# Initial discovery — retrospective placement + publication (n5)

Shared whole-work discovery:
[2026-10-27-moving-snippets-initial-discovery.md](./2026-10-27-moving-snippets-initial-discovery.md).

Node-specific findings:

- Design §4 steps 6–7: at RTAB flush, distribute the keyframe
  correction over stored VO increments (pose-graph-lite), place
  buffered keypoints in the map frame, confirm verdicts, publish
  `MovingObjectSnapshot` under `100 + track_id`.
- The sidecar (`src/surmap/slam/sidecar.py`) is batch: poses and
  cloud exist only at `flush()`; its EuRoC staging and
  own/shared-container teardown rules are inherited, not changed.
- The KITTI stereo snippet (n2 fixtures, design §6.2) is this
  node's acceptance vehicle through the real backend.
- Static-layer re-seeding uses n3's `StaticLayer` refresh at flush.
