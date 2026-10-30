"""The civilian demo snapshot and the local loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from surmap.mapqa import SnapshotError, load_snapshot
from tests.mapqa_fakes import EXAMPLE


def test_demo_snapshot_is_a_civilian_rescue_scene() -> None:
    # Given the checked-in disaster snapshot
    text = EXAMPLE.read_text(encoding="utf-8").lower()

    # Then it describes a humanitarian scene and nothing military
    assert "collapsed" in text
    assert "roof" in text
    assert "blocked" in text
    assert "vehicle" in text
    assert "soldier" not in text
    assert "rifle" not in text
    assert "missile" not in text
    assert "artillery" not in text
    assert "weapon" not in text
    assert "military" not in text


def test_loader_reads_the_demo_snapshot_layers() -> None:
    # Given the demo file
    snapshot = load_snapshot(EXAMPLE)

    # Then landmarks and the moving person stay in their own layers
    assert snapshot.origin is not None
    assert snapshot.origin.lat == 37.0
    assert [item.id for item in snapshot.landmarks] == ["1", "2", "4"]
    assert [item.id for item in snapshot.dynamic] == ["3"]
    assert snapshot.dynamic[0].label == "person"
    assert snapshot.dynamic[0].motion == "moving"
    assert snapshot.landmarks[0].xyz.x == 18.0
    assert snapshot.landmarks[0].mask_points is None


def test_loader_rejects_a_snapshot_with_the_wrong_schema(tmp_path: Path) -> None:
    # Given a file that claims a different schema
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"schema": "other", "origin": None, "landmarks": [], "dynamic": []}),
        encoding="utf-8",
    )

    # When it is loaded
    with pytest.raises(SnapshotError, match="surmap.semantic_map_snapshot.v1"):
        load_snapshot(path)
