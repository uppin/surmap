# 2026-11-04 — Waving and lying people are not found by any on-board detector

**Category:** Deferred scope
**Source:** the rigged-people changeset, wrapped into `docs/simulation/changelog/2026-11-04-sim-rigged-people.md` (PR #107, stack `#sim-traffic` node 2/3)
**Packages:** bevy-sitl-poc, surmap
**Consent:** none asked — a `#yolo` run; the orchestrator's decision 3 says a bar still missed after three iterations is recorded here with its numbers
**Status:** Open

## What is left

The developer's bar (2026-11-04): on `earthquake-survivors` every pose is found by some profile in
at least 20 % of its in-view object-frames. Measured (score 0.3, whole loop, 200 frames at 1 Hz):
standing 27 % and sitting 47 % (ssdlite-mobiledet) pass; **waving 0/33 and lying 0/6** for all three
profiles. Pass (a), the shipped scene, beats #111's Cesium Man on every profile (ssdlite 65/113
against 38/113).

## Why it could not be done now

Three iterations were spent (full hi-vis tint: worse; survivors moved off the slabs that half hid
them; waving survivor turned to the route). What remains is the viewpoint: the survey loop sees a
waving survivor from above at 15-40 px, where the raised arm is not a feature of the COCO person
class, and a lying survivor as a 56 x 15 px sliver on grey tarmac. Routes round it that are wrong:
scaling the figures up (the truth box would stop being their height), putting them in saturated
colours the real world does not have, or dropping the poses.

## What was done instead

The numbers are in `docs/simulation/bevy-simulation.md` § *On-board detectors (measured)*. A lying
person's ground truth is a horizontal box (`actors::posed_person_truth`) and tracks carry `pose`,
so a better detector or a closer pass is scored per pose without further change.

## When it becomes possible

When the survey pass can come closer to a survivor it has reason to inspect (a hover or a descent
leg over a candidate — `docs/architecture.md` §1 keeps flight control out of scope, so this is a
survey-planning question), or when a detector trained on aerial or lying people joins the profiles.
