"""Red tests for n2: snippet registry, oracle converters, KITTI staging."""

from __future__ import annotations

from types import ModuleType

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


def _fetch_module() -> ModuleType:
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_moving_snippets.py"
    spec = importlib.util.spec_from_file_location("fetch_moving_snippets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_moving_snippets"] = module
    spec.loader.exec_module(module)
    return module


def test_central_directory_parser_handles_zip64_extra() -> None:
    """The KITTI image zips are zip64: sizes/offsets live in extra fields."""
    import struct

    fetch = _fetch_module()
    name = b"training/image_02/0020/0000000001.png"
    extra = struct.pack("<HHQQQ", 0x0001, 24, 700_000, 650_000, 5_000_000_000)
    record = (
        b"PK\x01\x02"
        + struct.pack(
            "<HHHHHHIIIHHHHHII",
            20,
            45,
            0,
            8,
            0,
            0,
            0,
            0xFFFFFFFF,
            0xFFFFFFFF,
            len(name),
            len(extra),
            0,
            0,
            0,
            0,
            0xFFFFFFFF,
        )
        + name
        + extra
    )
    entries = fetch.parse_central_directory(record)
    entry = entries[name.decode()]
    assert entry.method == 8
    assert entry.compressed_size == 650_000
    assert entry.local_offset == 5_000_000_000


def test_kitti_calib_becomes_euroc_sensor_yaml() -> None:
    yaml_text = kitti_sensor_yaml(KITTI_CALIB, width=1242, height=375)
    assert "resolution: [1242, 375]" in yaml_text
    assert "721.5377" in yaml_text
