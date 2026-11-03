# 2026-11-03 — Loop-closure acceptance over the full Bevy survey loop

**Category:** Deferred scope
**Source:** PR #89, stack `#sim-disaster` n1
**Packages:** surmap.simulation, tests, examples/bevy-sitl-poc
**Consent:** Developer, 2026-11-03: "let's wrap the PR with TODO and we'll address the correctness in next PRs".
**Priority:** 1
**Status:** Open

## What is left

A real-sidecar test over the closed 182 m `survey-loop` (`--record <dir> --frames 487
--rate-hz 4 --start 0 --jpeg`): every frame tracked, odometry end drift ≤ 1.5 %, RTAB-Map
detects the closure at the return to the start, and the correction it applies there is
near zero (the world is perfect and odometry already closes to 0.8 %).

## Why it could not be done now

The capture is 73 MB — too large to commit — and CI runners have no GPU to record it.
The repo's pattern for large fixtures is a GitHub release asset pinned by SHA-256
(`scripts/fetch_rtabmap_fixture.py`, `fixtures-euroc-v1`); publishing one is the
developer's call. And the map-corrected track is wrong until
`2026-11-03-sidecar-odometry-covariance.md` is fixed, so the closure assertion would
fail for that bug, not for the simulation.

## When it becomes possible

After the covariance fix, with the loop capture published as a release asset (or
recorded smaller: 2 Hz, lower JPEG quality) and fetched by the CI sidecar job.
