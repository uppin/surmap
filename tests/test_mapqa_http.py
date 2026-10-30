"""POST /ask for the web viewer, plus the opt-in live Meta call."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from surmap.mapqa import MapQa, start_mapqa_server
from tests.mapqa_fakes import (
    EXAMPLE,
    RecordingTransport,
    answer_json,
    client,
    request_json,
    rescue_map,
    responses_reply,
)


def _post(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object], dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            parsed: object = json.loads(response.read().decode())
            assert isinstance(parsed, dict)
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, {str(key): value for key, value in parsed.items()}, headers
    except urllib.error.HTTPError as exc:
        parsed = json.loads(exc.read().decode())
        assert isinstance(parsed, dict)
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return exc.code, {str(key): value for key, value in parsed.items()}, headers


def test_post_ask_returns_the_viewer_contract() -> None:
    # Given a server bound to the rescue map
    transport = RecordingTransport(
        [responses_reply(answer_json("On the roof.", ["3"], [(37.11, -122.21)]))]
    )
    # When the viewer posts a question
    with start_mapqa_server(client(rescue_map(), transport), host="127.0.0.1", port=0) as server:
        status, body, headers = _post(server.url + "/ask", {"question": "Where is the person?"})

    # Then the response is the ask contract and a browser on another origin may read it
    assert status == 200
    assert body == {
        "answer": "On the roof.",
        "landmark_ids": ["3"],
        "highlight_points": [{"lat": 37.11, "lon": -122.21}],
    }
    assert headers["access-control-allow-origin"] == "*"


def test_post_ask_loads_snapshot_path(tmp_path: Path) -> None:
    # Given a second snapshot whose only id is the van
    path = tmp_path / "van.json"
    path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    transport = RecordingTransport(
        [responses_reply(answer_json("The van is at the curb.", ["4"], [(36.9, -121.9)]))]
    )
    # When the viewer names that file
    with start_mapqa_server(client(rescue_map(), transport), host="127.0.0.1", port=0) as server:
        status, body, _headers = _post(
            server.url + "/ask",
            {"question": "Where is the vehicle?", "snapshot_path": str(path)},
        )

    # Then the citation is validated against that file
    assert status == 200
    assert body["landmark_ids"] == ["4"]
    assert "vehicle" in str(request_json(transport)["input"])


def test_post_ask_rejects_a_missing_question() -> None:
    # Given a running server
    transport = RecordingTransport([])
    # When the body has no question
    with start_mapqa_server(client(rescue_map(), transport), host="127.0.0.1", port=0) as server:
        status, body, _headers = _post(server.url + "/ask", {})

    # Then the viewer gets a client error and the model is not called
    assert status == 400
    assert body["error"]
    assert transport.calls == []


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 to call the Meta Model API",
)
def test_live_ask_prints_the_map_answer() -> None:
    # Given the demo snapshot and a real MODEL_API_KEY
    asked = MapQa(EXAMPLE)

    # When a responder asks where the person is
    answer = asked.ask("Where is the person who may need rescue, and what blocks the road?")

    # Then the validated answer is printed for the operator
    print(json.dumps(answer.as_dict(), indent=2))
    assert answer.answer.strip()
    assert answer.landmark_ids
    assert answer.highlight_points
