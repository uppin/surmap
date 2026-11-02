"""Muse Wonder picks SAM concepts via structured output. No network."""

import json
from collections.abc import Mapping

import pytest

from surmap.labelling.meta_muse import (
    MetaMuseConceptClient,
    MetaMuseSceneError,
    clean_concept,
    parse_concepts,
)

_JPEG = bytes.fromhex("ffd8ffd9")


def _reply(text: str) -> dict[str, object]:
    return {
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }


class _Transport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.bodies: list[Mapping[str, object]] = []

    def post_json(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, object]
    ) -> Mapping[str, object]:
        assert url == "https://api.meta.ai/v1/responses"
        assert headers["Authorization"] == "Bearer k-123"
        self.bodies.append(body)
        return _reply(self.text)


def test_the_request_uses_responses_text_format_not_response_format() -> None:
    # Given a client and a structured reply
    transport = _Transport(json.dumps({"concepts": ["debris pile"]}))
    client = MetaMuseConceptClient(transport=transport, api_key="k-123", max_concepts=3)

    # When it proposes concepts for one frame
    concepts = client.propose(_JPEG)

    # Then the schema rides in text.format, and person leads the list
    body = transport.bodies[0]
    assert "response_format" not in body
    assert "tool_choice" not in body
    text = body["text"]
    assert isinstance(text, dict)
    fmt = text["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "sam_concepts"
    assert fmt["strict"] is True
    assert fmt["schema"]["required"] == ["concepts"]
    assert fmt["schema"]["additionalProperties"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["model"] == "muse-wonder-1.0"
    assert concepts == ("person", "debris pile")


def test_lists_negation_spatial_words_and_long_phrases_are_dropped() -> None:
    reply = json.dumps(
        {
            "concepts": [
                "Collapsed Building.",
                "no people",
                "car on the left",
                "roof and wall",
                "a very long phrase of words",
                "flooded road",
                "person",
                "debris #3",
                7,
            ]
        }
    )
    assert parse_concepts(reply, 8) == ("person", "collapsed building", "flooded road")


def test_the_list_is_capped_with_person_first() -> None:
    reply = json.dumps({"concepts": ["vehicle", "debris pile", "flooded road", "roof"]})
    assert parse_concepts(reply, 2) == ("person", "vehicle")


def test_a_reply_that_is_not_the_schema_is_an_error() -> None:
    with pytest.raises(MetaMuseSceneError):
        parse_concepts("person, car", 4)
    with pytest.raises(MetaMuseSceneError):
        parse_concepts(json.dumps({"labels": []}), 4)


def test_clean_concept_keeps_short_noun_phrases() -> None:
    assert clean_concept("  Fallen  tree ") == "fallen tree"
    assert clean_concept("person near car") == ""
    assert clean_concept("") == ""


def test_a_missing_key_fails_before_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = _Transport("{}")
    with pytest.raises(MetaMuseSceneError):
        MetaMuseConceptClient(transport=transport).propose(_JPEG)
    assert transport.bodies == []


def test_zero_concepts_is_refused() -> None:
    with pytest.raises(MetaMuseSceneError):
        MetaMuseConceptClient(transport=_Transport("{}"), api_key="k", max_concepts=0)
