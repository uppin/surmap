# Initial Discovery: the autopilot's replay from t = 0

**Changeset**: [2026-11-04-autopilot-incremental.md](./2026-11-04-autopilot-incremental.md)
**Date**: 2026-11-04
**Passes**: 1

## Combined Conclusions

Two production call sites rebuild an autopilot at the pad and replay every 0.05 s step from
`t = 0`:

- `viewed_pose` → `state_at`, once per recorded frame (`record.rs:256`);
- `FleetLog::check` → `phase_when`, once per pushed command (`log.rs:185`).

A recording of `n` frames at `r` Hz therefore costs Σ of the steps to each frame, which is
O(n² / r · 20). A live session's k-th push costs O(t_k / 0.05). The review (finding R1, PR #133's
discovery) measured a 10-min 10 Hz recording at about 36 M steps.

`Autopilot` already advances incrementally: `advance(log, t)` continues from its last step, and
falls back to replaying from the pad when `t` goes backwards. It is proven equal to `state_at` by
`fleet::autopilot::tests::the_incremental_autopilot_matches_the_replayed_one`. Both call sites move
forward in time:

- recording frames have increasing `t_at(frame)`;
- `FleetLog::check` refuses `at_s` earlier than the last entry (`OutOfOrder`).

So both can keep one incremental autopilot per drone and give the same answers.

`Fleet.autopilots` is the live app's set, advanced by `fly_fleet` to `SimClock::now()`. Its time is
not the recorder's `t_at(frame)` (the recorder pins `SimTime` per frame), so the recorder keeps its
own cache rather than reading `Fleet.autopilots`.

## Exploration 1: call sites — 2026-11-04

**Agent**: parent Grep/Read on `origin/main` `f2fa941`

### Sequence

1. Grep `state_at|phase_when|fn viewed_pose|fn push` in `fleet.rs`, `fleet/log.rs`, `fleet/autopilot.rs`, `record.rs`
2. Read `fleet/autopilot.rs` 330–420 (`state_at`, `phase_when`, `Autopilot`)
3. Read `fleet.rs` 55–70 (`Fleet`), 120–175 (`viewed_pose`, `viewed_body`)
4. Read `fleet/log.rs` 175–195 (`check`)
5. Grep `viewed_pose|viewed_body` callers; read `record.rs` 245–262
6. Read `.agents/skills/pr-stack/SKILL.md` 415–425 (performance work's verification)

### Inspected files

#### `examples/bevy-sitl-poc/src/fleet/autopilot.rs`

```rust
pub fn state_at(home: Home, id: &str, log: &FleetLog, t_s: f32) -> DroneState {
    Autopilot::new(id, home).advance(log, t_s)                 // from the pad, every call
}
pub(super) fn phase_when(home: Home, id: &str, log: &FleetLog, at_s: f32) -> Phase {
    let mut pilot = Autopilot::new(id, home);                  // from the pad, every call
    let due = due_step(at_s);
    pilot.run_to(log, due);
    pilot.apply_due(log, due);
    pilot.state.phase
}
impl Autopilot {
    pub fn advance(&mut self, log: &FleetLog, t_s: f32) -> DroneState {
        let steps = steps_until(t_s);
        if steps < self.steps { *self = Self::new(&self.id, self.plan.home); }   // rewind = replay
        self.run_to(log, steps);
        self.state
    }
    fn apply_due(&mut self, log: &FleetLog, k: usize) { /* applies entries with due_step(at_s) <= k, once */ }
}
```

#### `examples/bevy-sitl-poc/src/fleet.rs:140-150`

```rust
pub fn viewed_pose(fleet: Option<&Fleet>, t_s: f32) -> Viewed {
    let drone = fleet.and_then(|fleet| {
        let id = fleet.active_at(t_s)?;
        let (_, home) = fleet.log.drones().iter().find(|(drone, _)| drone == id)?;
        Some((id, state_at(*home, id, &fleet.log, t_s)))
    });
    …
}
```

#### `examples/bevy-sitl-poc/src/fleet/log.rs:177-186`

```rust
fn check(&self, at_s: f32, command: &FleetCommand) -> Result<(), RefusalReason> {
    …
    if let Some(last) = self.entries.last().filter(|last| !(at_s >= last.at_s)) {
        return Err(RefusalReason::OutOfOrder { previous_at_s: last.at_s });
    }
    let phase = phase_when(*home, id, self, at_s);
```

#### `examples/bevy-sitl-poc/src/record.rs:256`

`let viewed = viewed_pose(fleet.as_deref(), t_s);`, once per recorded frame.

### Findings

- Both quadratic sites move forward in time, so an incremental autopilot per drone gives the same
  answers.
- `phase_when` runs to `due_step(at_s)` and applies the due entries. A cached checker does the
  same, continuing from its last step. Entries appended later are stamped at or after `at_s`, so the
  checker sees them in order.
- `pr-stack` § *Node kinds*: "Performance work preserves the contract and changes the measurement.
  Its verification is the measurement (rung V3), with the before-state recorded."
