# Initial discovery — classification, keypoints, buffering (n4)

Shared whole-work discovery:
[2026-10-27-moving-snippets-initial-discovery.md](./2026-10-27-moving-snippets-initial-discovery.md).

Node-specific findings:

- Design §4 steps 3–5: verdict state machine (terminal +
  versioned), net/path + velocity coherence + area stability,
  LK-tracked keypoints from dynamic candidate points, one
  ego-motion-compensated Kalman in camera frame, observation
  buffer with VO increments.
- `surmap.motion.classify_motion` is extended, not replaced.
- Detector identity adoption reuses `surmap.detection` IoU
  tracker IDs (`IouTracker` in `src/surmap/detection/tracker.py`).
- Snippet acceptance (design §6.1): fire must not graduate,
  swarm tests caps/envelope, traffic tests graduation/identity.
  Threshold tuning uses each snippet's first half; assertions
  the second.
