"""Regression: the live Ask path from the viewer through ``surmap.mapqa``.

The model replies with WGS84 ``{lat, lon}`` highlight points. The viewer
needs map-frame ``{x, y, z}``. ``surmap.mapqa.answer`` converts by
looking the cited ids up in the snapshot, so the viewer must not see
``lat``/``lon`` and must not raise.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from surmap.mapqa import client as mapqa_client
from surmap.mapqa.qa import _responses_bytes
from surmap.viewer.ask import answer_map_question
from surmap.viewer.snapshot import read_snapshot
from tests.mapqa_fakes import EXAMPLE, answer_json


def test_live_ask_with_lat_lon_highlights_reaches_the_viewer_as_map_metres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the live flag, a key, and a Meta reply citing track 3 in lat/lon
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.delenv("SURMAP_MAPQA_MODEL", raising=False)
    monkeypatch.setenv("SURMAP_USAGE_LOG", "/dev/null")
    sent: list[str] = []

    def fake_post(self: object, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        del self, headers, body
        sent.append(url)
        return _responses_bytes(
            answer_json("The person is on the roof.", ["3"], [(37.000218, -122.000166)])
        )

    monkeypatch.setattr(mapqa_client.UrllibTransport, "post", fake_post)

    # When the viewer's POST /ask handler answers through the live path
    result = answer_map_question(
        "where is the person", read_snapshot(EXAMPLE), snapshot_path=str(EXAMPLE)
    )

    # Then Meta was called once and the points are the snapshot's x/y/z
    assert sent == ["https://api.meta.ai/v1/responses"]
    body = result.as_json()
    assert body["answer"] == "The person is on the roof."
    assert body["landmark_ids"] == ["3"]
    assert body["highlight_points"] == [{"x": 18.4, "y": 24.2, "z": 9.5}]
