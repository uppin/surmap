# Changeset: the autopilot advances instead of replaying from t = 0

**Date**: 2026-11-04
**Status**: 🚧 In Progress
**Type**: Refactor
**Behaviour**: preserves
**Complexity**: 2 — one Rust module set (`fleet/`, `record.rs`), two call sites, an existing
incremental autopilot proven equal to the replay; characterisation tests plus a deterministic
step count

Discovery: `2026-11-04-autopilot-incremental-initial-discovery.md` · PRD: none — behaviour-preserving

## Workflow

- [wf 1] ✅ 2026-11-04 `/plan-tdd-migration` Plan — changeset, initial discovery · these files
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create changeset
- [wf 2] ✅ 2026-11-04 `/plan-tdd-migration` Preservation tests — green against the baseline, and the step-count before-state, committed · baseline 362 tests; +3 characterisation (green on State A) +2 measurements = 367 passed, 2 `#[ignore]`d after-bounds red; before (a) 35 994 000 · (b) 5 005 000 steps
  - [x] Baseline: `cargo test --locked` green, count recorded
  - [x] A deterministic step counter the measurement reads (see `## Verification`)
  - [x] Characterisation tests (green before and after; see `## Verification`)
  - [x] V3 before-output recorded in `## Verification`
- [wf 3] ⬜ `/green` Implement — the recorded command produces the planned after-output, preservation tests still green ·
  - [ ] `FleetLog` keeps one checker `Autopilot` per drone and answers `check` from it (no `phase_when` replay)
  - [ ] The recorder keeps one `Autopilot` per drone for `viewed_pose` (no `state_at` replay per frame)
  - [ ] `state_at` / `phase_when` stay only as the test oracle, or are removed if nothing else uses them
  - [ ] Gates green; `cargo test --locked`; `cargo check --locked --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
  - [ ] `docs/simulation/bevy-simulation.md` — *The fleet and its autopilot*: the recorder and the log advance incrementally
  - [ ] `docs/simulation/changelog/2026-11-04-autopilot-incremental.md`
  - [ ] Lint, type-check and tests green
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

**Workflow override:** the Refactor kind's `restructure` preset expects a `plan.jsonl` of
refactoring intents. This is an algorithm change (replace a replay with an incremental cache),
which no intent expresses. So the rows follow the `migration` shape (preservation tests → change
→ wrap), and the proof is a V3 measurement as `pr-stack` § *Node kinds* prescribes for performance
work. Developer's request (2026-11-04): "yes, please resolve the autopilot issue".

## Initial Discovery

Full codebase exploration that grounded this plan: [initial-discovery.md](./2026-11-04-autopilot-incremental-initial-discovery.md).

## Background

PR #133's review (finding R1) found that two `#drone-fleet` call sites replay the autopilot from
`t = 0`:

- `viewed_pose`, for every recorded frame;
- `FleetLog::check`, for every pushed command.

A recording's cost therefore grows quadratically with its length (about 36 M steps for 10 min at
10 Hz), as does a long live session's push cost. The developer asked to resolve it.

## Technical Changes

### State A (Current)

- `record.rs:256` calls `viewed_pose(fleet, t_s)` per frame, which calls
  `state_at(home, id, log, t_s) = Autopilot::new(id, home).advance(log, t_s)`. That replays from the
  pad every time.
- `FleetLog::check` (`log.rs:185`) calls `phase_when(home, id, log, at_s)`, which also replays from
  the pad.
- `Autopilot::advance` is incremental and rewinds by replay when `t` decreases. It equals
  `state_at` at every moment (an existing test).

### State B (Target)

- **`FleetLog`** holds a per-drone checker `Autopilot`. `check(at_s, …)` advances that drone's
  checker to `due_step(at_s)`, applying the entries due by then, and reads its phase. The answer is
  identical to `phase_when`, because `OutOfOrder` guarantees `at_s` never decreases. A refused
  command is not appended, and that changes nothing in the checker either.
  - A `FleetLog` built `from_jsonl` builds its checkers as it pushes, so it pays the same linear
    cost.
  - `Clone` / equality semantics of `FleetLog` stay what the tests need. If the checker must not
    take part in `PartialEq`, compare entries only.
- **The recorder** keeps a `HashMap<drone id, Autopilot>` (a `ViewedPoses` cache, or a cache
  argument to a `viewed_pose_with(&mut cache, fleet, t)`). Each frame advances the active drone's
  autopilot to `t_s`.
  - An earlier `t` rewinds by replay, as `advance` already does, so a still at `--at t` is
    unaffected.
  - The pure `viewed_pose(fleet, t)` stays, as the oracle the tests compare against.
- **No change** to any pose, phase, refusal, frame line or log line. The fleet log format, the
  wire and the live `Fleet.autopilots` are untouched.

## Verification

**Method:**

- **V1-characterisation.** These tests are green before the change and stay green after. They
  would fail if the incremental path diverged.
  - `the_recorders_cached_pose_equals_the_replayed_pose_on_every_frame`: the sortie fixture, 10 Hz
    over 0–60 s, with `set_active` switches included. Each frame's cached `Viewed` equals
    `viewed_pose`.
  - `every_push_decides_as_a_fresh_replay_would`: the sortie plus a scripted sequence that hits
    every `RefusalReason`. Each `push` result equals the decision computed by a fresh `phase_when`
    oracle, applied to a copy of the log.
  - `a_rewound_recorder_still_matches_the_replay`: frames at 30 s, then 10 s.
- **V3.** A deterministic count of autopilot steps executed, read through a test-only counter
  (e.g. a `#[cfg(test)]` thread-local incremented in `step`), for two workloads:
  - (a) recording 6000 frames at 10 Hz over a 600 s log for two drones;
  - (b) 1000 pushes spaced 0.5 s apart.

**Command:** `cd examples/bevy-sitl-poc && cargo test --locked fleet -- --nocapture` (the
measurement tests print their counts and assert the after-bound).
**Before** (recorded in row 2, State A `8401744`; baseline `cargo test --locked` 362 passed):

```text
V3 (a) recording 6000 frames at 10 Hz over 600 s, two drones: 35994000 steps
V3 (b) 1000 pushes 0.5 s apart: 5005000 steps
```

The step counter is `autopilot::counting_steps`, a `#[cfg(test)]` thread-local incremented in
`step`. The after-bounds are the two `#[ignore]`d tests
`recording_six_thousand_frames_takes_one_pass_per_drone` (at most 24 000) and
`pushing_a_thousand_commands_takes_one_pass_over_the_log` (at most 11 000); they are red today, and
row 3 removes the `ignore`s. The characterisation tests run against a seam added in row 2: a
`ViewedPoses` recorder cache whose State A body still replays.

**After:** (a) at most 12 000 + 2 · 6000 steps (one pass per drone, plus slack); (b) at most
10 000 + 1000 steps. Exact bounds are set from the code in commit 2 and asserted.

## Prerequisites

| Item | Verdict |
|---|---|
| `examples/bevy-sitl-poc/docs/code-issues/oversized-file-world.md` | — unrelated (`world.rs` is untouched) |
| `todo/2026-11-04-fleet-obstacle-avoidance.md` | — unrelated |

## Decisions & Trade-offs

- **The recorder keeps its own cache rather than reading `Fleet.autopilots`.** The live set
  follows `SimClock::now()`, while the recorder pins `SimTime` per frame. Sharing one would couple
  the two clocks.
- **The pure oracles stay for tests.** `state_at` and `phase_when` are the definitions the cached
  paths must equal. Keeping them makes the characterisation tests meaningful.
- **The step counter is test-only**, so production has no instrumentation cost.
