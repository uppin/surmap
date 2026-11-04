# 2026-11-03 — `fire_perimeter.jsonl` from a real capture, loaded end to end

**Category:** Future enhancement
**Source:** PR #100, stack `#sim-disaster-2` n3
**Packages:** examples/bevy-sitl-poc, surmap
**Consent:** n/a — follow-up verification of shipped code
**Priority:** 2
**Status:** Open

## What is left

Record a short capture of a burning scenario
(`BEVY_ASSET_ROOT=$PWD cargo run --release -- --record cap --frames 20 --start 10 --scenario
wildfire-edge`), load it with `surmap.simulation.bevy_capture.load_bevy_capture`, and assert
`fire_perimeters` has one entry per recorded frame with the `front-1` polygon growing. Commit it
as a small fixture plus a test if it is cheap enough, as `tests/fixtures/bevy_sim_capture` is.

## Why it could not be done now

The writer (`record.rs`, `fire.rs` `perimeter_line`) and the reader (`bevy_capture.py`) are each
tested against the same line format, but no `--record` run with a fire was made in this PR: the
visual checkpoints used `--screenshot`, and a capture is a long native GPU run.

## What was done instead

`fire_perimeter.jsonl` is written beside a capture only when the scene has fires (absent
otherwise, which the loader reads as no perimeters). Unit tests pin the line format on both
sides.

## When it becomes possible

Now; the stack's later nodes (#101 behaviour trees, #104 building fires) record fires too and can
carry it.
