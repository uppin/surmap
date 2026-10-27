"""Red tests for n4: verdicts, keypoints, buffering."""

from __future__ import annotations

from surmap.moving.buffer import Observation, ObservationBuffer
from surmap.moving.classify import AreaStats, Verdict, VerdictMachine
from surmap.moving.config import MovingConfig
from surmap.moving.keypoints import ConstantVelocityFilter, select_keypoints
from surmap.types import Vec3

CONFIG = MovingConfig()
RIGID = AreaStats(8, 2_000_000_000, 3.0, 3.2, 0.9, 0.05)
OSCILLATING = AreaStats(8, 2_000_000_000, 0.1, 2.0, 0.2, 0.8)
SPARSE = AreaStats(2, 200_000_000, 0.3, 0.3, 0.9, 0.05)


def test_rigid_stats_graduate_to_rigid_mover() -> None:
    machine = VerdictMachine(CONFIG)
    assert machine.update(1, RIGID).verdict is Verdict.RIGID_MOVER


def test_published_rigid_verdict_never_flaps_to_oscillating() -> None:
    """A decelerating car traverses the oscillation band; terminal stays."""
    machine = VerdictMachine(CONFIG)
    machine.update(1, RIGID)
    assert machine.update(1, OSCILLATING).verdict is Verdict.RIGID_MOVER


def test_oscillating_stats_mark_oscillating_terminal() -> None:
    machine = VerdictMachine(CONFIG)
    assert machine.update(2, OSCILLATING).verdict is Verdict.OSCILLATING
    assert machine.update(2, RIGID).verdict is Verdict.OSCILLATING


def test_sparse_evidence_stays_unknown_and_versions_only_on_change() -> None:
    machine = VerdictMachine(CONFIG)
    first = machine.update(3, SPARSE)
    again = machine.update(3, SPARSE)
    graduated = machine.update(3, RIGID)
    assert first.verdict is Verdict.UNKNOWN
    assert again.version == first.version
    assert graduated.version == first.version + 1


def test_select_keypoints_covers_extent_within_cap() -> None:
    points = tuple(Vec3(float(i), float(i % 3), 5.0) for i in range(100))
    chosen = select_keypoints(points, CONFIG)
    assert 0 < len(chosen) <= CONFIG.max_keypoints
    assert all(point in points for point in chosen)
    assert points[0] in chosen or points[-1] in chosen


def test_filter_smooths_jitter_and_predicts() -> None:
    filt = ConstantVelocityFilter()
    out = [
        filt.update(i * 100_000_000, Vec3(1.0 + (0.1 if i % 2 else -0.1), 0.0, 5.0))
        for i in range(10)
    ]
    assert abs(out[-1].x - 1.0) < 0.1
    assert filt.predict(1_100_000_000).z == 5.0


def test_buffer_evicts_outside_window() -> None:
    buffer = ObservationBuffer(window_ns=3_000_000_000)
    for i in range(5):
        buffer.add(
            1,
            Observation(
                t_ns=i * 1_000_000_000,
                keypoints=(Vec3(0.0, 0.0, 5.0),),
                centroid=Vec3(0.0, 0.0, 5.0),
                velocity=Vec3(0.0, 0.0, 0.0),
                vo_translation=Vec3(0.0, 0.0, 0.0),
            ),
        )
    kept = buffer.observations(1)
    assert kept[0].t_ns >= 1_000_000_000
    assert len(kept) == 4
