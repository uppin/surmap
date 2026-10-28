"""Baseten Muse Spark Open labels one JPEG crop. The transport is fake."""

from __future__ import annotations

import base64
import io
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest
from PIL import Image

from surmap.labelling import (
    BasetenApiKeyMissing,
    BasetenMuseLabelClient,
    LabelClient,
    ObjectLabel,
)
from surmap.types import Vec3
from surmap.usage import BudgetExceeded, UsageLedger, UsageRecord

_MODEL = "meta-models/muse-spark-open-1026"
_LIVE = os.environ.get("SURMAP_LIVE_BASETEN") == "1" and bool(os.environ.get("BASETEN_API_KEY"))


@dataclass(frozen=True)
class RecordedPost:
    url: str
    headers: dict[str, str]
    body: bytes


class RecordingTransport:
    """Adapter-seam fake: records the POST and returns one canned completion."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = json.dumps(response).encode("utf-8")
        self.posts: list[RecordedPost] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        self.posts.append(RecordedPost(url, dict(headers), body))
        return self._response


def a_jpeg_crop() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (180, 40, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def a_completion(
    content: str | None,
    *,
    reasoning: str | None = "Looking at the crop.",
    prompt_tokens: int = 120,
    completion_tokens: int = 40,
    reasoning_tokens: int | None = 30,
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    usage: dict[str, object] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return {
        "object": "chat.completion",
        "model": _MODEL,
        "choices": [{"message": message}],
        "usage": usage,
    }


def a_client(
    transport: RecordingTransport,
    *,
    ledger: UsageLedger | None = None,
    max_tokens: int = 1024,
    reasoning_effort: str = "low",
    clock: Callable[[], float] | None = None,
    api_key: str | None = "test-key",
) -> BasetenMuseLabelClient:
    return BasetenMuseLabelClient(
        api_key=api_key,
        transport=transport,
        ledger=ledger,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        clock=clock,
    )


def a_map_point() -> Vec3:
    return Vec3(12.0, 4.0, 1.5)


def payload(body: bytes) -> dict[str, object]:
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return {str(key): value for key, value in parsed.items()}


def user_parts(body: bytes) -> list[dict[str, object]]:
    messages = payload(body)["messages"]
    assert isinstance(messages, list)
    user = messages[-1]
    assert isinstance(user, dict)
    content = user["content"]
    assert isinstance(content, list)
    parts: list[dict[str, object]] = []
    for part in content:
        assert isinstance(part, dict)
        parts.append({str(key): value for key, value in part.items()})
    return parts


def image_bytes(body: bytes) -> bytes:
    for part in user_parts(body):
        if part.get("type") != "image_url":
            continue
        image = part["image_url"]
        assert isinstance(image, dict)
        url = image["url"]
        assert isinstance(url, str)
        prefix = "data:image/jpeg;base64,"
        assert url.startswith(prefix)
        return base64.b64decode(url.removeprefix(prefix))
    raise AssertionError("request has no image part")


def text_part(body: bytes) -> str:
    for part in user_parts(body):
        if part.get("type") == "text":
            text = part["text"]
            assert isinstance(text, str)
            return text
    raise AssertionError("request has no text part")


def the_only_post(transport: RecordingTransport) -> RecordedPost:
    assert transport.posts == [transport.posts[0]]
    return transport.posts[0]


def test_label_request_posts_the_crop_to_baseten_and_parses_the_label() -> None:
    # Given a JPEG crop and a completion that names the object
    crop = a_jpeg_crop()
    reply = "label: pickup truck\ndescription: A white pickup beside the debris."
    transport = RecordingTransport(a_completion(reply, reasoning_tokens=None, reasoning=None))
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(crop, "car", a_map_point())

    # Then the POST is the Baseten chat completion and the label is the reply's
    post = the_only_post(transport)
    target = urlparse(post.url)
    body = payload(post.body)
    assert isinstance(client, LabelClient)
    assert target.scheme == "https"
    assert target.hostname == "inference.baseten.co"
    assert target.path == "/v1/chat/completions"
    assert body["model"] == _MODEL
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 1024
    assert "response_format" not in body
    assert "enable_thinking" not in post.body.decode("utf-8")
    assert image_bytes(post.body) == crop
    assert "car" in text_part(post.body)
    assert "12.00" in text_part(post.body)
    assert labelled == ObjectLabel(
        label="pickup truck",
        description="A white pickup beside the debris.",
        confidence=None,
        model_id=_MODEL,
        raw_text=reply,
        reasoning_text=None,
    )


def test_missing_api_key_raises_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no key in the environment and none passed to the client
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    transport = RecordingTransport(a_completion("label: car"))
    client = a_client(transport, api_key=None)

    # When the crop is labelled
    with pytest.raises(BasetenApiKeyMissing):
        client.label(a_jpeg_crop(), "car", a_map_point())

    # Then nothing is posted
    assert transport.posts == []


def test_blank_api_key_raises_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a blank key, even when the environment holds one
    monkeypatch.setenv("BASETEN_API_KEY", "should-not-be-read")
    transport = RecordingTransport(a_completion("label: car"))
    client = a_client(transport, api_key="  ")

    # When the crop is labelled
    with pytest.raises(BasetenApiKeyMissing):
        client.label(a_jpeg_crop(), "car", a_map_point())

    # Then nothing is posted
    assert transport.posts == []


def test_reply_without_a_label_prefix_uses_the_first_line() -> None:
    # Given a reply that is plain lines, not a label: field
    transport = RecordingTransport(
        a_completion("pickup truck\nParked on the shoulder.", reasoning=None, reasoning_tokens=None)
    )
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "vehicle", a_map_point())

    # Then the first line is the label and the next line is the description
    assert labelled.label == "pickup truck"
    assert labelled.description == "Parked on the shoulder."
    assert labelled.confidence is None


def test_confidence_is_absent_when_the_reply_has_no_number() -> None:
    # Given a reply with no digits
    transport = RecordingTransport(
        a_completion(
            "label: roof\nA flat roof on the clinic.", reasoning=None, reasoning_tokens=None
        )
    )
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "roof", a_map_point())

    # Then confidence stays unset
    assert labelled.label == "roof"
    assert labelled.description == "A flat roof on the clinic."
    assert labelled.confidence is None


def test_confidence_line_wins_over_a_number_in_the_label() -> None:
    # Given a label that itself contains digits and an explicit confidence
    reply = "label: 4x4 truck\nconfidence: 0.82\ndescription: A dark 4x4 by the clinic."
    transport = RecordingTransport(a_completion(reply, reasoning=None, reasoning_tokens=None))
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "truck", a_map_point())

    # Then confidence is the confidence line, not the 4 in 4x4
    assert labelled.label == "4x4 truck"
    assert labelled.confidence == 0.82
    assert labelled.description == "A dark 4x4 by the clinic."


def test_reasoning_text_is_kept_out_of_the_label() -> None:
    # Given a short answer and a long reasoning trace that names a different object
    content = "label: car"
    reasoning = "label: boat\nThe crop might be a boat. " + ("thinking " * 40)
    transport = RecordingTransport(
        a_completion(content, reasoning=reasoning, reasoning_tokens=2200)
    )
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "vehicle", a_map_point())

    # Then the label comes from content and reasoning is stored beside it
    assert labelled.label == "car"
    assert labelled.raw_text == content
    assert labelled.reasoning_text == reasoning
    assert "boat" not in labelled.raw_text
    assert labelled.reasoning_text not in labelled.raw_text


def test_empty_content_does_not_take_the_label_from_reasoning() -> None:
    # Given a completion whose answer is null and whose reasoning names an object
    transport = RecordingTransport(
        a_completion(None, reasoning="label: generator", reasoning_tokens=100)
    )
    client = a_client(transport)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "vehicle", a_map_point())

    # Then the label is empty and the reasoning is not copied into raw text
    assert labelled.label == ""
    assert labelled.raw_text == ""
    assert labelled.reasoning_text == "label: generator"


def test_configured_max_tokens_is_the_cap_that_is_sent() -> None:
    # Given a client capped at 256 completion tokens
    transport = RecordingTransport(
        a_completion("label: car", reasoning=None, reasoning_tokens=None)
    )
    client = a_client(transport, max_tokens=256)

    # When the crop is labelled
    client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the body carries that cap and still asks for low reasoning
    assert payload(the_only_post(transport).body)["max_tokens"] == 256
    assert payload(the_only_post(transport).body)["reasoning_effort"] == "low"


def _clear_baseten_tuning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SURMAP_BASETEN_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("SURMAP_BASETEN_MAX_TOKENS", raising=False)


def test_unset_env_sends_low_effort_and_a_1024_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no tuning env and a client that omits both settings
    _clear_baseten_tuning(monkeypatch)
    transport = RecordingTransport(
        a_completion("label: car", reasoning=None, reasoning_tokens=None)
    )
    client = BasetenMuseLabelClient(api_key="test-key", transport=transport)

    # When the crop is labelled
    client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the request uses the per-object defaults
    body = payload(the_only_post(transport).body)
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 1024


def test_env_overrides_reasoning_effort_and_the_token_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given env tuning and a client that omits both settings
    _clear_baseten_tuning(monkeypatch)
    monkeypatch.setenv("SURMAP_BASETEN_REASONING_EFFORT", "medium")
    monkeypatch.setenv("SURMAP_BASETEN_MAX_TOKENS", "512")
    transport = RecordingTransport(
        a_completion("label: car", reasoning=None, reasoning_tokens=None)
    )
    client = BasetenMuseLabelClient(api_key="test-key", transport=transport)

    # When the crop is labelled
    client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the request uses the env values
    body = payload(the_only_post(transport).body)
    assert body["reasoning_effort"] == "medium"
    assert body["max_tokens"] == 512


def test_explicit_effort_and_cap_win_over_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given env tuning and a client that sets both arguments
    monkeypatch.setenv("SURMAP_BASETEN_REASONING_EFFORT", "high")
    monkeypatch.setenv("SURMAP_BASETEN_MAX_TOKENS", "2048")
    transport = RecordingTransport(
        a_completion("label: car", reasoning=None, reasoning_tokens=None)
    )
    client = BasetenMuseLabelClient(
        api_key="test-key",
        transport=transport,
        reasoning_effort="low",
        max_tokens=256,
    )

    # When the crop is labelled
    client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the constructor arguments are what is sent
    body = payload(the_only_post(transport).body)
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 256


def test_invalid_reasoning_effort_env_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given an effort env that is not low, medium, or high
    monkeypatch.setenv("SURMAP_BASETEN_REASONING_EFFORT", "xhigh")
    transport = RecordingTransport(a_completion("label: car"))

    # When the client is built without an explicit effort
    with pytest.raises(ValueError, match="reasoning_effort"):
        BasetenMuseLabelClient(api_key="test-key", transport=transport)

    # Then nothing is posted
    assert transport.posts == []


def test_invalid_max_tokens_env_is_rejected_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a token-cap env that is not a positive integer
    _clear_baseten_tuning(monkeypatch)
    monkeypatch.setenv("SURMAP_BASETEN_MAX_TOKENS", "many")
    transport = RecordingTransport(a_completion("label: car"))

    # When the client is built without an explicit cap
    with pytest.raises(ValueError, match="SURMAP_BASETEN_MAX_TOKENS"):
        BasetenMuseLabelClient(api_key="test-key", transport=transport)

    # Then nothing is posted
    assert transport.posts == []


def test_reasoning_effort_cannot_claim_reasoning_is_off() -> None:
    # Given a transport that would fail the test if it were called
    transport = RecordingTransport(a_completion("label: car"))

    # When the client is built with an effort that claims reasoning is off
    with pytest.raises(ValueError, match="reasoning"):
        a_client(transport, reasoning_effort="none")

    # Then nothing is posted
    assert transport.posts == []


def test_api_key_is_sent_only_in_the_authorization_header() -> None:
    # Given a client that holds a test key
    transport = RecordingTransport(
        a_completion("label: car", reasoning=None, reasoning_tokens=None)
    )
    client = a_client(transport, api_key="test-key")

    # When the crop is labelled
    client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the key is the bearer token and is absent from the body
    post = the_only_post(transport)
    assert post.headers["Authorization"] == "Bearer test-key"
    assert post.headers["Content-Type"] == "application/json"
    assert b"test-key" not in post.body


def test_label_records_usage_on_the_ledger(tmp_path: Path) -> None:
    # Given a ledger and a completion that reports token counts
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    transport = RecordingTransport(
        a_completion("label: car", prompt_tokens=120, completion_tokens=40, reasoning_tokens=30)
    )
    client = a_client(transport, ledger=ledger, clock=lambda: 1_761_609_600.5)

    # When the crop is labelled
    labelled = client.label(a_jpeg_crop(), "car", a_map_point())

    # Then one JSON line records Baseten usage and the process total includes it
    assert labelled.model_id == _MODEL
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == [
        json.dumps(
            {
                "provider": "baseten",
                "model": _MODEL,
                "input_tokens": 120,
                "output_tokens": 40,
                "reasoning_tokens": 30,
                "t_unix": 1_761_609_600.5,
            },
            separators=(",", ":"),
        )
    ]
    assert ledger.calls("baseten") == 1
    assert ledger.total_tokens("baseten") == 160


def test_spent_call_budget_raises_before_the_transport_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a ledger that has already recorded the one allowed Baseten call
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    ledger(UsageRecord("baseten", _MODEL, 10, 5, 4, 100.0))
    monkeypatch.setenv("SURMAP_BUDGET_BASETEN_CALLS", "1")
    transport = RecordingTransport(a_completion("label: car"))
    client = a_client(transport, ledger=ledger)

    # When another crop is labelled
    with pytest.raises(BudgetExceeded) as caught:
        client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the transport is not called
    assert transport.posts == []
    assert caught.value.provider == "baseten"
    assert caught.value.kind == "calls"


def test_spent_token_budget_raises_before_the_transport_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a ledger already over the Baseten token budget
    log = tmp_path / "usage.jsonl"
    ledger = UsageLedger(log)
    ledger(UsageRecord("baseten", _MODEL, 80, 30, 20, 100.0))
    monkeypatch.setenv("SURMAP_BUDGET_BASETEN_TOKENS", "100")
    transport = RecordingTransport(a_completion("label: car"))
    client = a_client(transport, ledger=ledger)

    # When another crop is labelled
    with pytest.raises(BudgetExceeded) as caught:
        client.label(a_jpeg_crop(), "car", a_map_point())

    # Then the transport is not called
    assert transport.posts == []
    assert caught.value.kind == "tokens"


@pytest.mark.skipif(
    not _LIVE,
    reason="set SURMAP_LIVE_BASETEN=1 and BASETEN_API_KEY to call Baseten",
)
def test_live_baseten_labels_a_crop() -> None:
    # Given a real key and an explicit opt-in
    client = BasetenMuseLabelClient(max_tokens=256)

    # When one tiny crop is labelled
    labelled = client.label(a_jpeg_crop(), "vehicle", a_map_point())

    # Then the answer is a label from the hackathon model, not an empty body
    assert labelled.model_id == _MODEL
    assert labelled.label != ""
    assert labelled.raw_text != ""
