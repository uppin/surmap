# 2026-11-04 — The autopilot advances instead of replaying from t = 0 (PR #138)

- `FleetLog` checks each pushed command against a per-drone checker `Autopilot` that continues from
  its last check. A refused command that had advanced the checker past a later accepted one rewinds
  it by replay.
- The recorder's `ViewedPoses` keeps one `Autopilot` per drone for the viewed pose, instead of
  `state_at` per frame.
- `state_at`, `phase_when` and `viewed_pose` stay as the `#[cfg(test)]` oracle the incremental paths
  must equal.
- Behaviour is unchanged: no pose, phase, refusal, frame line or log line differs.
- Measured (autopilot steps, test-only counter): recording 6000 frames at 10 Hz over 600 s for two
  drones went from 35 994 000 to 17 996; 1000 pushes 0.5 s apart went from 5 005 000 to 10 000.
- Resolves PR #133's review finding R1.
- Decided without review:
  - the recorder keeps its own cache instead of reading `Fleet.autopilots`;
  - the step counter is test-only;
  - the rows follow the migration shape, not the `restructure` preset, because no refactoring
    intent expresses an algorithm change.
