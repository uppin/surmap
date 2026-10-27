"""Red tests for n2: snippet registry, oracle converters, KITTI staging."""

from __future__ import annotations

import pytest

from surmap.moving.candidates import CandidateCluster
from surmap.moving.snippets import (
    kitti_sensor_yaml,
    parse_purdue_refined_gt,
    parse_visdrone_mot,
    snippet_specs,
)
from surmap.types import Vec3

_P = "7.215377e+02 0 6.095593e+02"
KITTI_CALIB = (
    f"P0: {_P} 0 0 7.215377e+02 1.728540e+02 0 0 0 1 0\n"
    f"P1: {_P} -3.875744e+02 0 7.215377e+02 1.728540e+02 0 0 0 1 0\n"
    f"P2: {_P} 4.485728e+01 0 7.215377e+02 1.728540e+02 0 0 0 1 0\n"
    f"P3: {_P} -3.395741e+02 0 7.215377e+02 1.728540e+02 0 0 0 1 0\n"
)


def test_registry_covers_all_four_scenes() -> None:
    specs = snippet_specs()
    scenes = {spec.scene for spec in specs}
    assert scenes == {"traffic", "fire", "swarm", "stereo"}
    assert all(spec.source_url.startswith("https://") for spec in specs)
    assert all(spec.license for spec in specs)


def test_candidate_cluster_rejects_empty_points() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        CandidateCluster(frame_id=1, t_ns=0, points=(), depth_min_m=1.0, depth_max_m=2.0)


def test_candidate_cluster_keeps_depth_range() -> None:
    cluster = CandidateCluster(
        frame_id=7,
        t_ns=42,
        points=(Vec3(0.0, 0.0, 5.0),),
        depth_min_m=4.0,
        depth_max_m=6.0,
    )
    assert cluster.depth_min_m == 4.0
    assert cluster.depth_max_m == 6.0


def test_visdrone_mot_rows_become_oracle_boxes() -> None:
    text = "1,3,100,50,60,30,1,4,0,0\n2,3,102,52,61,31,1,4,0,0\n"
    boxes = parse_visdrone_mot(text)
    assert len(boxes) == 2
    assert boxes[0].track_id == 3
    assert boxes[0].left == 100.0
    assert boxes[1].frame_index == 2


def test_purdue_refined_gt_rows_become_oracle_boxes() -> None:
    text = "1 2 300 200 24 18\n2 2 305 202 24 18\n"
    boxes = parse_purdue_refined_gt(text)
    assert len(boxes) == 2
    assert boxes[0].track_id == 2
    assert boxes[0].width == 24.0


def test_kitti_calib_becomes_euroc_sensor_yaml() -> None:
    yaml_text = kitti_sensor_yaml(KITTI_CALIB, width=1242, height=375)
    assert "resolution: [1242, 375]" in yaml_text
    assert "721.5377" in yaml_text
