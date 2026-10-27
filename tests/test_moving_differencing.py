"""Red tests for n3: static-layer differencing and moving areas."""

from __future__ import annotations

from surmap.moving.areas import (
    AreaObservation,
    AreaTracker,
    min_area_px,
    simplify_polygon,
)
from surmap.moving.config import MovingConfig
from surmap.moving.differencing import StaticLayer, tau
from surmap.types import Vec3

CONFIG = MovingConfig()


def _grid(cx: float, cy: float, n: int = 40) -> tuple[Vec3, ...]:
    return tuple(Vec3(cx + (i % 8) * 0.05, cy + (i // 8) * 0.05, 10.0) for i in range(n))


def test_tau_grows_with_depth_and_pose_drift() -> None:
    assert tau(20.0, 0.0, CONFIG) > tau(5.0, 0.0, CONFIG)
    assert tau(10.0, 0.02, CONFIG) > tau(10.0, 0.0, CONFIG)


def test_fast_car_still_forms_a_cluster_each_frame() -> None:
    """Issue-1 regression: 3 m/frame motion must not need voxel recurrence."""
    layer = StaticLayer(CONFIG)
    layer.seed(_grid(0.0, 0.0))
    for frame in range(3):
        clusters = layer.difference(frame, frame * 200_000_000, _grid(3.0 * frame, 5.0))
        assert len(clusters) == 1
        assert len(clusters[0].points) >= CONFIG.min_cluster_points


def test_differenced_movers_are_not_absorbed_into_the_layer() -> None:
    layer = StaticLayer(CONFIG)
    layer.seed(_grid(0.0, 0.0))
    car = _grid(9.0, 9.0)
    layer.difference(1, 0, car)
    assert not layer.is_occupied(car[0])


def test_noise_sized_cluster_is_filtered() -> None:
    layer = StaticLayer(CONFIG)
    layer.seed(_grid(0.0, 0.0))
    assert layer.difference(1, 0, _grid(9.0, 9.0, n=5)) == ()


def test_dwell_needs_several_frames_to_join_the_layer() -> None:
    layer = StaticLayer(CONFIG)
    point = Vec3(1.0, 1.0, 5.0)
    layer.observe_frame([point])
    assert not layer.is_occupied(point)
    layer.observe_frame([point])
    assert not layer.is_occupied(point)
    layer.observe_frame([point])
    assert layer.is_occupied(point)


def test_absorbed_ghost_decays_away() -> None:
    layer = StaticLayer(CONFIG)
    ghost = Vec3(2.0, 2.0, 5.0)
    layer.seed([ghost])
    assert layer.is_occupied(ghost)
    far = _grid(30.0, 30.0)
    for frame in range(80):
        layer.difference(frame, frame, far)
    assert not layer.is_occupied(ghost)


def test_differencing_is_within_frame_budget() -> None:
    """Design budget: 5 Hz on one CM5 core; 4k points far under 200 ms.

    Workload as designed: a dense surface layer (stereo points on
    mapped surfaces), movers a minority of the frame. (A sparse
    random layer turns the test into nearest-neighbour search
    over empty space; that adversarial case measures ~0.15 s on
    this host and is recorded in the changeset.)
    """
    import time

    layer = StaticLayer(CONFIG)
    layer.seed(Vec3(x * 0.1, y * 0.1, 0.0) for x in range(200) for y in range(200))
    frame = [Vec3(x * 0.1, y * 0.1, 0.0) for x in range(0, 200, 3) for y in range(0, 200, 3)]
    frame = frame[:3960] + list(_grid(10.0, 10.0))
    layer.difference(0, 0, frame)  # warm-up
    start = time.perf_counter()
    clusters = layer.difference(1, 1, frame)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05, f"differencing took {elapsed:.3f}s for 4000 points"
    assert len(clusters) == 1  # the mover grid, nothing else


def test_min_area_scales_down_with_depth() -> None:
    assert min_area_px(20.0, CONFIG) < min_area_px(10.0, CONFIG)
    assert min_area_px(20.0, CONFIG) <= 60.0


def test_simplify_polygon_caps_vertices() -> None:
    polygon = tuple((float(i), float((i * i) % 7)) for i in range(200))
    simplified = simplify_polygon(polygon, epsilon_px=2.0, config=CONFIG)
    assert 0 < len(simplified) <= CONFIG.max_polygon_vertices


def test_area_tracker_keeps_identity_for_nearby_polygon() -> None:
    tracker = AreaTracker(CONFIG)
    first = AreaObservation(1, ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)), 5.0, 6.0, 50)
    second = AreaObservation(2, ((2.0, 0.0), (12.0, 0.0), (12.0, 10.0)), 5.0, 6.0, 50)
    far = AreaObservation(2, ((300.0, 200.0), (310.0, 200.0), (310.0, 210.0)), 5.0, 6.0, 50)
    assert tracker.update(first).track_id == tracker.update(second).track_id
    assert tracker.update(far).track_id != tracker.update(first).track_id
