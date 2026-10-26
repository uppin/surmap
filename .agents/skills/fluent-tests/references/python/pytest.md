# Fluent Tests in Python (pytest) — SurMap

SurMap's suite is pytest under `tests/`, typed (mypy strict covers tests),
with contracts from `src/surmap/types.py`. Write tests that read as the
specification of the survey behaviour they pin down.

## Shape: Given / When / Then, one behaviour per test

```python
def test_static_object_points_land_in_the_map_frame() -> None:
    # Given a stereo pair seen from a camera 10 m east of the map origin
    frame = StereoFramePair(1, 1_000_000, "left.png", "right.png", "cal-1")
    pose = Pose(Vec3(10.0, 0.0, 0.0))

    # When the backend registers the frame
    result = InMemorySlamBackend(pose).process_frame(frame)

    # Then the trajectory records that pose for that frame
    assert result.pose == pose
```

## Builders for contracts, with sensible defaults

Hide irrelevant defaults behind a small factory; override only what the test
is about (as `tests/test_slam.py` does with `_frame()`):

```python
def a_detection(frame_id: int = 1, label: str = "car", score: float = 0.9) -> Detection:
    return Detection(frame_id, (0.0, 0.0, 10.0, 10.0), label, score, "edgetpu-ssd-v2")
```

## Domain assertions read as English

Prefer a named helper over arithmetic inline in the assert:

```python
assert centroid_is_within(observed.centroid, expected=Vec3(4.0, 5.0, 6.0), metres=0.5)
assert track.motion is Motion.MOVING  # never baked into the static layer
```

## Rules

- Test through the public API (`SlamBackend` protocol, `to_map_frame`,
  `classify_motion`); fake at the adapter seam (`InMemorySlamBackend`, stub
  RTAB-Map bindings), never mock the unit under test.
- Deterministic: fixed `t_ns`, fixed calibration, recorded fixtures for
  detector/SAM output. No hardware, network or live models.
- Names state the survey behaviour: `test_moving_person_stays_out_of_the_static_layer`.
- Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`.
