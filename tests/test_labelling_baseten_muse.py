"""Baseten Muse Spark Open labels one JPEG crop for a disaster-response survey."""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import pytest
from PIL import Image

from surmap.labelling import InMemoryLabelClient, LabelClient, ObjectLabel
from surmap.labelling.baseten_muse import (
    BasetenApiKeyMissing,
    BasetenLabelError,
    BasetenMuseLabelClient,
    HttpResponse,
)
from surmap.types import Vec3

_API_KEY = "baseten-test-key"
_MODEL_ID = "meta-models/muse-spark-open-1026"
_CROP_JPEG = b"\xff\xd8\xff\xd9"
_ROOF = Vec3(12.5, -3.0, 1.25)
_REASONING = "label: parked car\nThe reasoning must not become the label."


@dataclass(frozen=True)
class RecordedPost:
    url: str
    headers: dict[str, str]
    body: bytes


class RecordingTransport:
    """HTTP seam that records one POST and never opens a socket."""

    def __init__(self, response_body: bytes, status: int = 200) -> None:
        self._response_body = response_body
        self._status = status
        self.posts: list[RecordedPost] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> HttpResponse:
        self.posts.append(RecordedPost(url, dict(headers), body))
        return HttpResponse(self._status, self._response_body)


def _completion(content: str) -> bytes:
    payload = {
        "object": "chat.completion",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": _REASONING,
                }
            }
        ],
    }
    return json.dumps(payload).encode()


def _client(transport: RecordingTransport) -> BasetenMuseLabelClient:
    return BasetenMuseLabelClient(api_key=_API_KEY, transport=transport, env={})


def _json_object(body: bytes) -> dict[str, object]:
    parsed: object = json.loads(body)
    assert isinstance(parsed, dict)
    return {str(key): value for key, value in parsed.items()}


def _image_data_url(payload: Mapping[str, object]) -> str:
    messages = payload["messages"]
    assert isinstance(messages, list)
    for message in messages:
        assert isinstance(message, dict)
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            assert isinstance(part, dict)
            if part.get("type") != "image_url":
                continue
            image = part.get("image_url")
            assert isinstance(image, dict)
            url = image.get("url")
            assert isinstance(url, str)
            return url
    raise AssertionError("request had no image_url part")


def _block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("urlopen was called")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


def test_fake_transport_labels_a_crop_via_baseten(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a JPEG crop and a client whose HTTP transport stays in memory
    _block_sockets(monkeypatch)
    reply = "label: collapsed roof\nA roof slab lying across the road."
    transport = RecordingTransport(_completion(reply))
    client = _client(transport)

    # When the crop is labelled
    observed = client.label_object(_CROP_JPEG, "roof", _ROOF)

    # Then Muse on Baseten is asked for the crop, and the label is the assistant text
    assert isinstance(client, LabelClient)
    assert len(transport.posts) == 1
    post = transport.posts[0]
    parsed = urlparse(post.url)
    assert parsed.hostname == "inference.baseten.co"
    assert parsed.path == "/v1/chat/completions"
    assert post.headers["Authorization"] == f"Bearer {_API_KEY}"
    assert _API_KEY.encode() not in post.body
    payload = _json_object(post.body)
    assert payload["model"] == _MODEL_ID
    image_url = _image_data_url(payload)
    assert image_url.startswith("data:image/jpeg;base64,")
    encoded = image_url.removeprefix("data:image/jpeg;base64,")
    assert base64.b64decode(encoded) == _CROP_JPEG
    assert observed == ObjectLabel(
        label="collapsed roof",
        description="A roof slab lying across the road.",
        confidence=None,
        model_id=_MODEL_ID,
        raw_text=reply,
    )


def test_request_asks_for_low_reasoning_and_plain_text() -> None:
    # Given a client using the default reasoning setting
    transport = RecordingTransport(_completion("label: debris\nRubble in the road."))
    client = _client(transport)

    # When a crop is labelled
    client.label_object(_CROP_JPEG, "debris", _ROOF)

    # Then the call asks for low reasoning and does not request JSON mode
    payload = _json_object(transport.posts[0].body)
    assert payload["reasoning_effort"] == "low"
    assert "response_format" not in payload
    assert "enable_thinking" not in transport.posts[0].body.decode()
    assert "json_object" not in transport.posts[0].body.decode()


def test_reply_without_a_label_prefix_uses_the_first_line() -> None:
    # Given a reply that names the object on its first line
    reply = "debris pile\nRubble blocking the clinic road."
    transport = RecordingTransport(_completion(reply))
    client = _client(transport)

    # When the crop is labelled
    observed = client.label_object(_CROP_JPEG, "car", _ROOF)

    # Then that first line is the label, not the reasoning text
    assert observed == ObjectLabel(
        label="debris pile",
        description="Rubble blocking the clinic road.",
        confidence=None,
        model_id=_MODEL_ID,
        raw_text=reply,
    )


def test_a_stated_confidence_is_parsed_from_the_reply() -> None:
    # Given a reply that states a confidence after another number
    reply = "label: white van\n2 vehicles are visible.\nconfidence: 0.64"
    transport = RecordingTransport(_completion(reply))
    client = _client(transport)

    # When the crop is labelled
    observed = client.label_object(_CROP_JPEG, "car", _ROOF)

    # Then the confidence is the stated number, and the reasoning label is ignored
    assert observed == ObjectLabel(
        label="white van",
        description="2 vehicles are visible.\nconfidence: 0.64",
        confidence=0.64,
        model_id=_MODEL_ID,
        raw_text=reply,
    )


def test_a_number_in_the_reply_is_the_confidence_when_none_is_named() -> None:
    # Given a reply with a number and no confidence field
    reply = "label: rubble\nAbout 3 metres of debris across the road."
    transport = RecordingTransport(_completion(reply))
    client = _client(transport)

    # When the crop is labelled
    observed = client.label_object(_CROP_JPEG, "debris", _ROOF)

    # Then that number is the confidence
    assert observed == ObjectLabel(
        label="rubble",
        description="About 3 metres of debris across the road.",
        confidence=3.0,
        model_id=_MODEL_ID,
        raw_text=reply,
    )


def test_prompt_frames_a_civilian_disaster_response() -> None:
    # Given a coarse detector label and a map-frame position
    transport = RecordingTransport(_completion("label: collapsed roof\nA roof slab."))
    client = _client(transport)

    # When the crop is labelled
    client.label_object(_CROP_JPEG, "roof", _ROOF)

    # Then the prompt is a civilian disaster-response request, not a flight task
    body = transport.posts[0].body.decode()
    assert "civilian disaster-response" in body
    assert "search-and-rescue" in body
    assert "Do not propose flight" in body
    assert "Coarse detector label: roof" in body
    assert "x=12.500 y=-3.000 z=1.250" in body


def test_missing_api_key_raises_before_any_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no Baseten key and a socket that would fail the test if opened
    _block_sockets(monkeypatch)
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)

    # When the client is constructed
    with pytest.raises(BasetenApiKeyMissing, match="BASETEN_API_KEY"):
        BasetenMuseLabelClient()

    # Then construction fails before urlopen (the patched socket was not called)


def test_blank_api_key_raises_before_the_transport_is_used() -> None:
    # Given a blank key and a transport that records every POST
    transport = RecordingTransport(_completion("label: debris\nRubble."))

    # When the client is constructed with that key
    with pytest.raises(BasetenApiKeyMissing, match="BASETEN_API_KEY"):
        BasetenMuseLabelClient(
            api_key="   ", transport=transport, env={"BASETEN_API_KEY": _API_KEY}
        )

    # Then no request was sent
    assert transport.posts == []


def test_http_error_does_not_include_the_api_key() -> None:
    # Given Baseten rejects the call and echoes the key in the body
    body = json.dumps({"error": f"rejected {_API_KEY}"}).encode()
    transport = RecordingTransport(body, status=401)
    client = _client(transport)

    # When the crop is labelled
    with pytest.raises(BasetenLabelError, match="HTTP 401") as raised:
        client.label_object(_CROP_JPEG, "roof", _ROOF)

    # Then the failure names the status and not the key
    assert _API_KEY not in str(raised.value)


def test_empty_assistant_content_is_not_read_from_reasoning() -> None:
    # Given a completion whose answer is empty and whose reasoning names an object
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "  ",
                    "reasoning_content": _REASONING,
                }
            }
        ]
    }
    transport = RecordingTransport(json.dumps(payload).encode())
    client = _client(transport)

    # When the crop is labelled
    with pytest.raises(BasetenLabelError, match="content") as raised:
        client.label_object(_CROP_JPEG, "roof", _ROOF)

    # Then the reasoning text is not adopted as the label
    assert "parked car" not in str(raised.value)


def test_empty_crop_is_refused_before_the_transport_is_used() -> None:
    # Given a client and an empty crop
    transport = RecordingTransport(_completion("label: debris\nRubble."))
    client = _client(transport)

    # When the empty crop is labelled
    with pytest.raises(BasetenLabelError, match="JPEG"):
        client.label_object(b"", "roof", _ROOF)

    # Then no request was sent
    assert transport.posts == []


def test_in_memory_client_returns_the_label_it_was_given() -> None:
    # Given a label already recorded for this object
    expected = ObjectLabel(
        label="debris pile",
        description="Rubble blocking the clinic road.",
        confidence=None,
        model_id=_MODEL_ID,
        raw_text="debris pile",
    )
    client = InMemoryLabelClient(expected)

    # When another crop is labelled
    observed = client.label_object(_CROP_JPEG, "car", Vec3(1.0, 2.0, 3.0))

    # Then the recorded label is returned without a network client
    assert isinstance(client, LabelClient)
    assert observed == expected


_LIVE = os.environ.get("SURMAP_LIVE_BASETEN") == "1" and bool(os.environ.get("BASETEN_API_KEY"))


@pytest.mark.skipif(
    not _LIVE,
    reason="set SURMAP_LIVE_BASETEN=1 and BASETEN_API_KEY to call Baseten",
)
def test_live_baseten_labels_a_jpeg_crop() -> None:
    # Given a real JPEG crop and the process Baseten key
    image = Image.new("RGB", (32, 32), (180, 40, 40))
    crop = _jpeg_bytes(image)
    client = BasetenMuseLabelClient()

    # When the crop is labelled on the live API
    observed = client.label_object(crop, "red marker", Vec3(4.0, 1.0, 0.5))

    # Then the answer is a short label from the assistant text, not a reasoning dump
    assert observed.model_id == _MODEL_ID
    assert observed.label != ""
    assert "\n" not in observed.label
    assert len(observed.label) < 120
    assert observed.raw_text != ""
    assert "parked car" not in observed.label


def _jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()
