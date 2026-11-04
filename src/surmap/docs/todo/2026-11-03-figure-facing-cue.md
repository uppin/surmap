# 2026-11-03 — A front cue on the person figure, so its heading shows

**Category:** Future enhancement
**Source:** PR #101, stack `#sim-disaster-2` n4 (2 of 4), Wrap row — the planner's B1 review
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — future enhancement (the visual spec's facing and yaw easing are implemented; only their visibility is missing)
**Status:** Open

## What is left

A person is a capsule with a sphere head (`world.rs`, `Capsule3d::new(0.17, 1.05)` and
`Sphere::new(0.13)`), which looks the same from every side. `actors.rs` turns each figure to its
heading with the yaw eased over `yaw_ease_s` (visual spec § *People*), but in stills and
recordings nothing shows which way a figure faces, so the turn and its easing are invisible.
Wanted: a front cue — for example a visor on the head or a backpack on the back — whose shape,
size, offset and material come from `assets/behaviour/person.figure.json` (new fields beside
`yaw_ease_s`, `bob_m`, `steps_per_s`, `reference_speed_m_s`), never from Rust constants.

## Why it could not be done now

The visual spec this PR was built to names only "the existing capsule-and-head figure, rotated
each frame to face its heading". A cue is a new visual decision, and the visual spec makes the
planner its owner; adding one at wrap time would grow a reviewed diff with a look nobody
reviewed. The B1 review approved the checkpoint as it is (the three evacuees in the grass at
t = 60 and the front pushed north-east by the veered wind).

## What was done instead

Figures turn and bob as specified (`actors.rs` `animate_figures`, `yaw_at`, `bob`; unit tests in
`actors/tests.rs` pin the eased turn, the short way round, the facing in Bevy space and the bob).
The facing is real in the transform; only the mesh does not reveal it.

## When it becomes possible

Now: a planner's visual-spec line for the cue's look, then a figure-JSON field set and a
`people.png` still to review it.
