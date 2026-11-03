# 2026-11-03 — The fire-eye review still ignores the rig's mount pitch

**Category:** Future enhancement
**Source:** PR #100, stack `#sim-disaster-2` n3
**Packages:** examples/bevy-sitl-poc
**Consent:** n/a — review tooling only
**Priority:** 4
**Status:** Open

## What is left

`shots.rs` `aim_overview_at_fire` places the `fire-eye.png` camera 40 m south of the first
ignition, 15 m up, and orients it with `looking_at` the ignition. A real rig there would look
along the drone's heading pitched down by the camera profile's mount pitch (35° for the ELP
profile). Wanted: the eye's orientation from the profile's mount (heading towards the fire, the
profile's pitch), so the still shows exactly what the rig would.

## Why it could not be done now

It affects only `--screenshot` review stills of fire scenes; the survey flight, the eyes that
`--record` captures, and RTAB-Map's calibration all use the profile's mount and are untouched.

## What was done instead

The fire eye uses the profile's intrinsics (`CalibratedProjection`) and the eye look
(`Lens::Still`), aimed by `looking_at`.

## When it becomes possible

Now.
