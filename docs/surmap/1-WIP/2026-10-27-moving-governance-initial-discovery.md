# Initial discovery — resource governance (n6)

Shared whole-work discovery:
[2026-10-27-moving-snippets-initial-discovery.md](./2026-10-27-moving-snippets-initial-discovery.md).

Node-specific findings:

- Design §5: per-stage counters, hard caps, degradation ladder
  (5 Hz→2 Hz, keypoints 16→8, detector-labelled only, off),
  layer-memory counter against the 2 M-voxel cap.
- Design §2 budgets: ≤1 CPU core, ≤256 MB, live areas ≤1 s,
  snapshots ≤2 s after flush returns.
- The CM5-profile gate replays EuRoC + KITTI in a 4-core
  container-limited profile with the RTAB sidecar active,
  following the repo's existing E2E teardown discipline.
