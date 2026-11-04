# 2026-11-04 — Simulated drones on their nests, flown by a kinematic autopilot (#drone-fleet 2/5, PR #117)

- The drones on each nest now spawn docked on its pad (`fleet.rs`). When a scene has nests, the
  legacy keyboard drone is removed. Scenes without nests are unchanged.
- The fleet log (`fleet/log.rs`) is a simulation-time-stamped JSONL of `launch`, `set_route`,
  `detour`, `recall` and `set_active`. It checks each command against the drone's phase and keeps
  refusals without applying them.
- The kinematic autopilot (`fleet/autopilot.rs`) is pure and steps every 0.05 s. Its phases are
  Docked, Climbing, Cruising, Detouring, Hovering, Returning and Landing. Its limits are 2 m/s
  climb, 2.5 m/s² horizontal acceleration, 60°/s turn rate and 1 m/s landing. The runtime
  `Autopilot` equals `state_at` at every `t`.
- The active drone drives the rig, the chase camera and the status line. The UI lists the fleet.
  Recordings take `pose_enu` from `viewed_pose(t)` and, with a fleet, write `drone_id` to
  `frames.jsonl`, which `CapturedFrame.drone_id` reads.
- `--fleet-log <path>` replays a log for stills and recordings. The fixture is
  `tests/fixtures/fleet/survey-sortie.fleet.jsonl`.
- Decided without review: no obstacle avoidance or drone-to-drone separation
  (`src/surmap/docs/todo/2026-11-04-fleet-obstacle-avoidance.md`). The legacy drone is removed when
  nests exist. Drones are kinematic, with no dynamics, wind or battery.
- No file this PR touched reaches 500 lines (`shots.rs` is at 499), so nothing was split or left
  for the sweep node.
