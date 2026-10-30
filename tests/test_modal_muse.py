"""Modal Muse Spark Open client. The HTTP transport is fake unless SURMAP_LIVE_MODAL=1."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Protocol, cast

import pytest

from surmap.labelling.modal_muse import (
    DEFAULT_MODEL,
    MIN_MAX_TOKENS,
    ModalMuseClient,
    ModalMuseConfigError,
    completions_url,
)

_JPEG = b"\xff\xd8\xff\xd9"


class _SavedUse(Protocol):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None


class _Transport:
    def __init__(self, bodies: list[dict[str, Any]]) -> None:
        self._bodies = list(bodies)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.payloads: list[dict[str, Any]] = []

    def post(self, url: str, headers: Mapping[str, str], body: bytes) -> bytes:
        self.urls.append(url)
        self.headers.append(dict(headers))
        payload = json.loads(body)
        assert isinstance(payload, dict)
        self.payloads.append(cast(dict[str, Any], payload))
        if not self._bodies:
            raise AssertionError("no scripted response left")
        return json.dumps(self._bodies.pop(0)).encode()


def _completion(
    text: str,
    *,
    finish: str = "stop",
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    reasoning_tokens: int | None = 3,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    return {
        "model": model,
        "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": text}}],
        "usage": usage,
    }


def test_a_missing_url_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no endpoint configuration
    monkeypatch.delenv("MODAL_MUSE_URL", raising=False)
    monkeypatch.delenv("MODAL_PROXY_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_PROXY_TOKEN_SECRET", raising=False)
    transport = _Transport([_completion("ready")])

    # When chat is attempted
    with pytest.raises(ModalMuseConfigError, match="MODAL_MUSE_URL"):
        ModalMuseClient(transport=transport).chat([{"role": "user", "content": "Hi"}])

    # Then the transport was not called
    assert transport.urls == []


def test_label_posts_the_image_the_model_and_the_proxy_token() -> None:
    # Given a configured client and a scripted reply
    transport = _Transport([_completion("a person standing")])
    client = ModalMuseClient(
        url="https://muse.modal.example",
        token_id="wk-id",
        token_secret="ws-secret",
        transport=transport,
    )

    # When a crop is labelled
    text = client.label(_JPEG, "person")

    # Then the shared-endpoint chat URL, bearer token, and image part are sent
    assert text == "a person standing"
    assert transport.urls == ["https://muse.modal.example/v1/chat/completions"]
    assert transport.headers[0]["Authorization"] == "Bearer wk-id.ws-secret"
    payload = transport.payloads[0]
    assert payload["model"] == DEFAULT_MODEL
    assert payload["max_tokens"] >= MIN_MAX_TOKENS
    content = payload["messages"][0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "person" in content[1]["text"]


def test_an_empty_reply_is_retried_once_with_a_larger_cap() -> None:
    # Given a first reply that is empty and a second that is not
    transport = _Transport([_completion("  "), _completion("debris")])
    seen: list[str] = []

    def before_call(provider: str) -> None:
        seen.append(provider)

    client = ModalMuseClient(
        url="https://muse.modal.example/v1",
        token_id="wk-id",
        token_secret="ws-secret",
        before_call=before_call,
        transport=transport,
    )

    # When chat runs
    text = client.chat([{"role": "user", "content": "Name the object."}])

    # Then the second call uses a larger cap and the hook ran twice
    assert text == "debris"
    assert transport.urls == ["https://muse.modal.example/v1/chat/completions"] * 2
    assert transport.payloads[0]["max_tokens"] == MIN_MAX_TOKENS
    assert transport.payloads[1]["max_tokens"] == MIN_MAX_TOKENS * 2
    assert seen == ["modal", "modal"]


def test_a_length_truncated_reply_is_retried_once() -> None:
    # Given a reply that hit the token cap
    transport = _Transport(
        [_completion("partial", finish="length"), _completion("a full sentence")]
    )
    client = ModalMuseClient(
        url="https://muse.modal.example",
        token_id="wk-id",
        token_secret="ws-secret",
        transport=transport,
    )

    # When chat runs
    text = client.chat([{"role": "user", "content": "Describe the scene."}])

    # Then the second completion is the one returned
    assert text == "a full sentence"
    assert len(transport.payloads) == 2


def test_usage_records_token_counts_from_the_response() -> None:
    # Given a completion with token counts
    transport = _Transport([_completion("ready", prompt_tokens=20, completion_tokens=4)])
    usage: list[tuple[str, str, int, int, int | None]] = []

    def on_usage(
        provider: str, model: str, input_tokens: int, output_tokens: int, reasoning: int | None
    ) -> None:
        usage.append((provider, model, input_tokens, output_tokens, reasoning))

    client = ModalMuseClient(
        url="https://muse.modal.example",
        token_id="wk-id",
        token_secret="ws-secret",
        model="meta-models/Muse-Spark-Open-816B-A42B",
        on_usage=on_usage,
        transport=transport,
    )

    # When chat runs
    client.chat([{"role": "user", "content": "Reply with the single word ready."}])

    # Then the hook sees modal, the model, and the response counts
    assert usage == [("modal", DEFAULT_MODEL, 20, 4, 3)]


def test_completions_url_does_not_double_the_suffix() -> None:
    # Given bases that already include part of the path
    # When the chat URL is built
    # Then the suffix is added once
    assert (
        completions_url("https://muse.modal.example")
        == "https://muse.modal.example/v1/chat/completions"
    )
    assert (
        completions_url("https://muse.modal.example/v1/")
        == "https://muse.modal.example/v1/chat/completions"
    )
    assert (
        completions_url("https://muse.modal.example/v1/chat/completions")
        == "https://muse.modal.example/v1/chat/completions"
    )


@pytest.mark.skipif(os.environ.get("SURMAP_LIVE_MODAL") != "1", reason="set SURMAP_LIVE_MODAL=1")
def test_live_modal_muse_prints_a_reply() -> None:
    # Given a real endpoint configured in the environment
    client = ModalMuseClient()

    # When one short completion is requested
    reply = client.chat([{"role": "user", "content": "Reply with the single word ready."}])

    # Then the text is printed for the operator and is not empty
    print(reply)
    assert reply.strip()
