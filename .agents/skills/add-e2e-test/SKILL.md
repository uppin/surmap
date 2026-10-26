---
name: add-e2e-test
description: Creates end-to-end tests for the SurMap survey pipeline following the session-replay pattern — a recorded or synthetic session in, a semantic map (or map layer) out. Group by survey intent and reuse one session fixture per intent; fold new coverage into an existing replay test before adding a new session. Use when adding pipeline-level coverage, replay tests, or ground-truth geometry checks.
---

# Add an End-to-End (Session-Replay) Test

SurMap's end-to-end surface is not a UI. It is the pipeline:

```text
recorded / synthetic session (stereo pairs + GPS checkpoints, §5 format)
  -> SLAM backend trajectory        (InMemorySlamBackend in tests)
  -> object points in the map frame (surmap.geometry.to_map_frame)
  -> motion split                   (surmap.motion.classify_motion)
  -> map layers: static merged, moving kept as timestamped tracks
```

A test at this level proves one **survey intent**: e.g. "a parked car ends up
in the static layer at the GPS-anchored position the ground truth says", or
"a walking person stays a track and never enters the static layer".

## Rules

1. **One session fixture per intent.** Reuse the session that already covers
   the intent; add frames/checkpoints to it rather than recording a new one.
   Synthetic sessions must be indistinguishable in format from a recorded
   real session (`docs/architecture.md` §2.3, §5).
2. **No hardware, no native RTAB-Map.** Drive the pipeline through
   `surmap.slam.InMemorySlamBackend` (fixed-pose) or a stub binding like
   `tests/test_slam.py`'s `StubSession`. The real `RtabmapBackend` is covered
   by its adapter tests, including `RtabmapUnavailable` when the binding is
   absent.
3. **Assert on map outcomes, not internals.** Positions within a stated
   tolerance of ground truth, layer membership (static vs track), track
   identity over time — not call counts or private state.
4. **Deterministic.** Fixed timestamps (`t_ns`), fixed calibration ID, no
   wall clock, no network, no model downloads. Detector and SAM outputs are
   fixtures (recorded `Detection` lists, recorded masks), never live models.
5. **Name the intent.** `test_parked_car_merges_into_static_layer_at_known_position`,
   not `test_pipeline_3`.

## Shape

```python
def test_moving_person_stays_a_track_and_out_of_the_static_layer() -> None:
    session = load_session_fixture("person-crossing")  # stereo pairs + GPS, §5 format
    result = run_pipeline(session, backend=InMemorySlamBackend())

    assert result.static_layer.track_ids == ()
    track = result.tracks.single(label="person")
    assert track.motion is Motion.MOVING
    assert track.observations[-1].centroid is within_metres(2.0, of=ground_truth_end)
```

Keep the fluent style: load the `fluent-tests` skill, bar in
`skills/testing/references/fluent-style.md`. Run with
`uv run pytest -q -k replay` plus the full gates
(`uv run ruff check src tests`, `uv run mypy`) before handoff.
