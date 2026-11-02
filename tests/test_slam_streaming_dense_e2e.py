"""Real-container e2e: the journalled dense buffer answers a region as the live sidecar did."""

import time
from dataclasses import dataclass

import numpy as np
import pytest

from surmap.demo.datasets import scaled_sensor_yaml
from surmap.slam.dense import DenseBufferRegionSource, DenseFrame, RegionRig
from surmap.slam.regions import RegionQuery, RegionResult, RegionStatus
from surmap.slam.streaming import StreamingRtabmapBackend
from tests.test_slam_streaming_e2e import FIXTURE, _require_prepared
from tests.test_slam_streaming_regions_e2e import CENTRE, _box_polygon, _feed_fixture, _xyz

SAM_LIKE_OUTLINE = (
    (121.3, 80.6),
    (180.2, 66.4),
    (255.7, 92.1),
    (231.4, 128.8),
    (190.5, 112.2),
    (176.9, 166.3),
    (128.4, 151.7),
)


@dataclass(frozen=True)
class Journalled:
    """Regions asked live of one recent frame, and what the sidecar journalled for them."""

    rig: RegionRig
    dense: list[DenseFrame]
    left: RegionResult
    left_again: RegionResult
    right: RegionResult
    outline: RegionResult
    left_query: RegionQuery
    right_query: RegionQuery
    outline_query: RegionQuery


@pytest.fixture(scope="module")
def journalled() -> Journalled:
    manifest = _require_prepared()
    timestamps = manifest["frame_timestamps_ns"]
    assert isinstance(timestamps, list)
    cam0 = (FIXTURE / "mav0" / "cam0" / "sensor.yaml").read_text(encoding="utf-8")
    cam1 = (FIXTURE / "mav0" / "cam1" / "sensor.yaml").read_text(encoding="utf-8")
    backend = StreamingRtabmapBackend(
        cam0_yaml=scaled_sensor_yaml(cam0, 376, 240),
        cam1_yaml=scaled_sensor_yaml(cam1, 376, 240),
        dense_journal=True,
    )
    target = len(timestamps) - 5
    left_query = RegionQuery(1, target, 0, 376, 240, _box_polygon(CENTRE))
    right_query = RegionQuery(3, target, 1, 376, 240, _box_polygon(CENTRE))
    # A SAM-like outline: slanted edges, a concave notch, fractional vertices.
    outline_query = RegionQuery(4, target, 0, 376, 240, SAM_LIKE_OUTLINE)
    try:
        _feed_fixture(backend, timestamps)
        deadline = time.monotonic() + 30
        while backend.frame_odometry(target) is None and time.monotonic() < deadline:
            backend.poll_updates()
            time.sleep(0.05)
        left = backend.region_points(left_query, timeout=10.0)
        left_again = backend.region_points(
            RegionQuery(2, target, 0, 376, 240, left_query.polygon), timeout=10.0
        )
        right = backend.region_points(right_query, timeout=10.0)
        outline = backend.region_points(outline_query, timeout=10.0)
        rig = backend.region_rig
        assert rig is not None
        return Journalled(
            rig,
            backend.poll_dense(),
            left,
            left_again,
            right,
            outline,
            left_query,
            right_query,
            outline_query,
        )
    finally:
        backend.close()


def assert_same_region(offline: RegionResult, live: RegionResult) -> None:
    assert live.status is RegionStatus.OK and offline.status is RegionStatus.OK
    assert abs(len(offline.points) - len(live.points)) <= 0.02 * len(live.points)
    centroid_gap = np.linalg.norm(_xyz(offline).mean(axis=0) - _xyz(live).mean(axis=0))
    assert float(centroid_gap) < 0.01


def test_each_queried_frame_and_channel_is_journalled_once(journalled: Journalled) -> None:
    # Given / When the same left region was asked twice and the right one once
    # Then the sidecar computed and journalled each channel's disparity once
    assert [(frame.frame_id, frame.channel) for frame in journalled.dense] == [
        (journalled.left_query.frame_id, 0),
        (journalled.left_query.frame_id, 1),
    ]
    assert journalled.left_again.points == journalled.left.points


def test_the_journal_answers_the_left_region_as_the_live_sidecar_did(
    journalled: Journalled,
) -> None:
    # When the left region is asked of the journalled dense buffer
    offline = DenseBufferRegionSource(journalled.rig, journalled.dense).region_points(
        journalled.left_query
    )

    # Then it matches the live answer
    assert_same_region(offline, journalled.left)


def test_the_journal_answers_the_right_region_as_the_live_sidecar_did(
    journalled: Journalled,
) -> None:
    offline = DenseBufferRegionSource(journalled.rig, journalled.dense).region_points(
        journalled.right_query
    )

    assert_same_region(offline, journalled.right)


def test_the_journal_covers_a_sam_outline_pixel_for_pixel_like_the_live_sidecar(
    journalled: Journalled,
) -> None:
    # When a slanted, concave outline is asked of the journalled dense buffer
    offline = DenseBufferRegionSource(journalled.rig, journalled.dense).region_points(
        journalled.outline_query
    )

    # Then it is the live answer point for point (to float32 rounding)
    live = journalled.outline
    assert live.status is RegionStatus.OK and len(live.points) > 1_000
    assert len(offline.points) == len(live.points)
    np.testing.assert_allclose(_xyz(offline), _xyz(live), atol=1e-3)
