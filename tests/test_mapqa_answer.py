"""The viewer hook ``surmap.mapqa.answer(question, snapshot_path=...)``."""

from __future__ import annotations

import urllib.request

import pytest

from surmap.mapqa import ModelApiKeyMissing, answer
from tests.mapqa_fakes import EXAMPLE


def test_answer_uses_the_viewer_call_and_stays_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the rescue snapshot and no permission to call Meta
    monkeypatch.delenv("SURMAP_LIVE_META", raising=False)

    def refuse_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("offline answer must not call Meta")

    monkeypatch.setattr(urllib.request, "urlopen", refuse_network)

    # When the viewer asks where the person is
    result = answer("where is the person", snapshot_path=str(EXAMPLE))

    # Then the offline result cites that person in map-frame metres
    assert result == {
        "answer": "Matched 1 track(s): person (3).",
        "landmark_ids": ["3"],
        "highlight_points": [{"x": 18.4, "y": 24.2, "z": 9.5}],
    }


def test_answer_without_a_snapshot_path_names_no_landmarks() -> None:
    # Given the viewer has no snapshot file to hand over
    # When it still calls the hook
    result = answer("where is the person", snapshot_path=None)

    # Then nothing is cited and Meta is not required
    assert result == {
        "answer": "No semantic map snapshot is loaded.",
        "landmark_ids": [],
        "highlight_points": [],
    }


def test_live_meta_asks_through_mapqa_instead_of_the_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the live flag and no API key
    monkeypatch.setenv("SURMAP_LIVE_META", "1")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("SURMAP_MAPQA_MODEL", raising=False)

    def refuse_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a missing key must fail before any Meta request")

    monkeypatch.setattr(urllib.request, "urlopen", refuse_network)

    # When the viewer asks
    with pytest.raises(ModelApiKeyMissing):
        answer("where is the person", snapshot_path=str(EXAMPLE))
