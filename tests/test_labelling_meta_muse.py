"""Scene notes from hosted Muse Spark on the Meta Model API.

The fake transport pins the request the owner verified on 2026-10-28:
POST https://api.meta.ai/v1/responses, model muse-spark-1.3, and the
assistant note taken only from message output_text. A live call runs
only when SURMAP_LIVE_META=1.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest
from PIL import Image

from surmap.labelling.meta_muse import (
    MetaMuseSceneClient,
    MetaMuseSceneError,
    UrllibMetaMuseTransport,
)

_API_KEY = "scene-note-test-key"


@pytest.fixture(autouse=True)
def _clear_scene_note_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SURMAP_META_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("SURMAP_META_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("SURMAP_META_MODEL", raising=False)


def a_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def a_message(*texts: str) -> dict[str, object]:
    content: list[dict[str, object]] = [{"type": "output_text", "text": text} for text in texts]
    return {
        "output": [
            {
                "type": "reasoning",
                "content": [{"type": "output_text", "text": "reasoning the client must ignore"}],
            },
            {"type": "message", "role": "assistant", "content": content},
        ]
    }


class RecordingTransport:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, object]]] = []

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.calls.append((url, dict(headers), dict(body)))
        return self.response


class UnusedTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        raise AssertionError(f"transport should not be called for {url}")


class FailingTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        raise MetaMuseSceneError("Meta Model API returned HTTP 401")


def posted(transport: RecordingTransport) -> tuple[str, Mapping[str, str], Mapping[str, object]]:
    assert len(transport.calls) == 1
    return transport.calls[0]


def user_content(body: Mapping[str, object]) -> list[object]:
    raw_input = body["input"]
    assert isinstance(raw_input, list)
    message = raw_input[0]
    assert isinstance(message, dict)
    assert message["type"] == "message"
    assert message["role"] == "user"
    content = message["content"]
    assert isinstance(content, list)
    return list(content)


def prompt_text(body: Mapping[str, object]) -> str:
    part = user_content(body)[0]
    assert isinstance(part, dict)
    text = part["text"]
    assert isinstance(text, str)
    return text


def test_scene_note_posts_hosted_muse_spark_and_returns_the_message_text() -> None:
    # Given a mapped frame labelled debris and vehicle
    transport = RecordingTransport(a_message("Flooded street. Two vehicles."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the station asks for the scene note
    note = client.note(("debris", "vehicle"), a_jpeg())

    # Then the call hits the Meta Model API and the note is the assistant text
    url, headers, body = posted(transport)
    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.hostname == "api.meta.ai"
    assert parts.path == "/v1/responses"
    assert body["model"] == "muse-spark-1.3"
    assert body["stream"] is False
    assert headers["Authorization"] == f"Bearer {_API_KEY}"
    assert note == "Flooded street. Two vehicles."


def test_scene_note_ignores_reasoning_items_and_joins_message_output_text() -> None:
    # Given a response whose reasoning item also carries output_text
    transport = RecordingTransport(a_message("Flooded street. ", "Two vehicles."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is read
    note = client.note(("debris",), a_jpeg())

    # Then only the message parts are kept, in order
    assert note == "Flooded street. Two vehicles."
    assert "reasoning the client must ignore" not in note


def test_scene_note_sends_the_frame_as_an_input_image_data_url() -> None:
    # Given a JPEG of the mapped area
    jpeg = a_jpeg()
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), jpeg)

    # Then the Responses API image part is a plain data-URL string
    _url, _headers, body = posted(transport)
    content = user_content(body)
    image = content[1]
    assert isinstance(image, dict)
    assert image["type"] == "input_image"
    image_url = image["image_url"]
    assert isinstance(image_url, str)
    assert image_url == "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def test_scene_note_asks_for_a_rescue_description_and_no_flight_advice() -> None:
    # Given on-board labels for the frame
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris", "vehicle"), a_jpeg())

    # Then the prompt is a civilian rescue description and forbids flight advice
    text = prompt_text(posted(transport)[2])
    assert "search-and-rescue" in text
    assert "disaster-response" in text
    assert "debris" in text
    assert "vehicle" in text
    assert "Do not give flight advice" in text


def test_scene_note_still_describes_the_area_when_no_labels_were_recorded() -> None:
    # Given a frame with an empty label list
    transport = RecordingTransport(a_message("Open ground, no vehicles."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note((), a_jpeg())

    # Then the prompt says no labels were recorded and still forbids flight advice
    text = prompt_text(posted(transport)[2])
    assert "No on-board labels were recorded." in text
    assert "Do not give flight advice" in text


def test_a_single_string_is_not_treated_as_a_list_of_labels() -> None:
    # Given a client that must not post
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=UnusedTransport())

    # When one string is passed where a label sequence belongs
    with pytest.raises(MetaMuseSceneError, match="sequence of labels"):
        client.note("debris", a_jpeg())


def test_scene_note_defaults_reasoning_effort_to_high() -> None:
    # Given no effort override
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the body asks for high effort
    assert posted(transport)[2]["reasoning"] == {"effort": "high"}


def test_scene_note_reasoning_effort_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the env selects medium
    monkeypatch.setenv("SURMAP_META_REASONING_EFFORT", "medium")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then medium is what gets sent
    assert posted(transport)[2]["reasoning"] == {"effort": "medium"}


def test_constructor_reasoning_effort_overrides_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the env says low and the constructor says high
    monkeypatch.setenv("SURMAP_META_REASONING_EFFORT", "low")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, reasoning_effort="HIGH")

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the constructor value wins, normalized to the allowed spelling
    assert posted(transport)[2]["reasoning"] == {"effort": "high"}


def test_reasoning_effort_must_be_low_medium_or_high(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an effort outside the allowed set
    monkeypatch.setenv("SURMAP_META_REASONING_EFFORT", "minimal")

    # When the client is constructed from that env, or with a bad argument
    with pytest.raises(MetaMuseSceneError, match="low, medium, or high"):
        MetaMuseSceneClient(api_key=_API_KEY, transport=UnusedTransport())
    with pytest.raises(MetaMuseSceneError, match="low, medium, or high"):
        MetaMuseSceneClient(api_key=_API_KEY, transport=UnusedTransport(), reasoning_effort="max")


def test_scene_note_defaults_max_output_tokens_to_4096() -> None:
    # Given no output cap
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the body caps visible output and reasoning at 4096
    assert posted(transport)[2]["max_output_tokens"] == 4096


def test_max_output_tokens_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the env sets a smaller cap
    monkeypatch.setenv("SURMAP_META_MAX_OUTPUT_TOKENS", "128")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then that cap is what gets sent
    assert posted(transport)[2]["max_output_tokens"] == 128


def test_constructor_max_output_tokens_overrides_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the env says 128 and the constructor says 64
    monkeypatch.setenv("SURMAP_META_MAX_OUTPUT_TOKENS", "128")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, max_output_tokens=64)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the constructor cap wins
    assert posted(transport)[2]["max_output_tokens"] == 64


def test_an_unreadable_max_output_token_env_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an env value that is not an integer cap
    monkeypatch.setenv("SURMAP_META_MAX_OUTPUT_TOKENS", "plenty")

    # When the client is constructed
    with pytest.raises(MetaMuseSceneError, match="at least 16"):
        MetaMuseSceneClient(api_key=_API_KEY, transport=UnusedTransport())


def test_scene_note_sends_max_output_tokens_when_capped() -> None:
    # Given a cap of 64 tokens, counting visible output and reasoning
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, max_output_tokens=64)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the Responses body carries that cap
    assert posted(transport)[2]["max_output_tokens"] == 64


def test_max_output_tokens_below_16_is_refused() -> None:
    # Given a cap under the API minimum of 16
    # When the client is constructed
    with pytest.raises(MetaMuseSceneError, match="16"):
        MetaMuseSceneClient(api_key=_API_KEY, transport=UnusedTransport(), max_output_tokens=15)


def test_before_call_sees_meta_and_can_block_the_request() -> None:
    # Given a budget hook that refuses the provider
    transport = RecordingTransport(a_message("Debris across the road."))
    seen: list[str] = []

    def before_call(provider: str) -> None:
        seen.append(provider)
        raise MetaMuseSceneError("blocked")

    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, before_call=before_call)

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="blocked") as raised:
        client.note(("debris",), a_jpeg())

    # Then the hook saw "meta", the request was not sent, and the key stayed out
    assert seen == ["meta"]
    assert transport.calls == []
    assert _API_KEY not in str(raised.value)


def test_on_usage_receives_token_counts_from_the_response() -> None:
    # Given a response that reports input, output, and reasoning tokens
    payload = a_message("Debris across the road.")
    payload["usage"] = {
        "input_tokens": 120,
        "output_tokens": 40,
        "output_tokens_details": {"reasoning_tokens": 11},
    }
    transport = RecordingTransport(payload)
    seen: list[tuple[str, str, int, int, int | None]] = []

    def on_usage(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> None:
        seen.append((provider, model, input_tokens, output_tokens, reasoning_tokens))

    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, on_usage=on_usage)

    # When the note is requested
    note = client.note(("debris",), a_jpeg())

    # Then the ledger hook gets the Meta counts and the note is unchanged
    assert note == "Debris across the road."
    assert seen == [("meta", "muse-spark-1.3", 120, 40, 11)]


def test_on_usage_leaves_reasoning_tokens_empty_when_the_detail_is_absent() -> None:
    # Given usage without a reasoning breakdown
    payload = a_message("Debris across the road.")
    payload["usage"] = {"input_tokens": 10, "output_tokens": 4}
    transport = RecordingTransport(payload)
    seen: list[int | None] = []

    def on_usage(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> None:
        seen.append(reasoning_tokens)
        assert provider == "meta"
        assert model == "muse-spark-1.3"
        assert (input_tokens, output_tokens) == (10, 4)

    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport, on_usage=on_usage)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then reasoning tokens are absent rather than invented
    assert seen == [None]


def test_a_failed_request_does_not_report_usage() -> None:
    # Given a transport that fails after the gate has run
    events: list[str] = []

    def before_call(provider: str) -> None:
        events.append(provider)

    def on_usage(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> None:
        events.append(f"usage:{provider}:{model}:{input_tokens}:{output_tokens}:{reasoning_tokens}")

    client = MetaMuseSceneClient(
        api_key=_API_KEY,
        transport=FailingTransport(),
        before_call=before_call,
        on_usage=on_usage,
    )

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="HTTP 401"):
        client.note(("debris",), a_jpeg())

    # Then the gate ran and no usage was reported
    assert events == ["meta"]


def test_hooks_run_around_the_request_and_skip_usage_when_it_is_missing() -> None:
    # Given a response with no usage object
    transport = RecordingTransport(a_message("Debris across the road."))
    events: list[str] = []

    def before_call(provider: str) -> None:
        events.append(f"before:{provider}")

    def on_usage(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> None:
        events.append(f"usage:{provider}:{model}:{input_tokens}:{output_tokens}:{reasoning_tokens}")

    class OrderingTransport:
        def post_json(
            self,
            url: str,
            headers: Mapping[str, str],
            body: Mapping[str, object],
        ) -> Mapping[str, object]:
            events.append("post")
            return transport.post_json(url, headers, body)

    client = MetaMuseSceneClient(
        api_key=_API_KEY,
        transport=OrderingTransport(),
        before_call=before_call,
        on_usage=on_usage,
    )

    # When the note is requested
    note = client.note(("debris",), a_jpeg())

    # Then the gate runs before the post, and missing usage is not reported
    assert note == "Debris across the road."
    assert events == ["before:meta", "post"]


def test_muse_wonder_is_allowed_and_the_default_stays_muse_spark() -> None:
    # Given Muse Wonder, which the credits cover, and no model override
    wonder = RecordingTransport(a_message("Debris across the road."))
    default = RecordingTransport(a_message("Debris across the road."))
    wonder_client = MetaMuseSceneClient(model="muse-wonder-1.0", api_key=_API_KEY, transport=wonder)
    default_client = MetaMuseSceneClient(api_key=_API_KEY, transport=default)

    # When each note is requested
    wonder_client.note(("debris",), a_jpeg())
    default_client.note(("debris",), a_jpeg())

    # Then Wonder is sent as asked, and the default remains hosted Muse Spark
    assert posted(wonder)[2]["model"] == "muse-wonder-1.0"
    assert posted(default)[2]["model"] == "muse-spark-1.3"


def test_the_model_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the env selects Muse Wonder
    monkeypatch.setenv("SURMAP_META_MODEL", "muse-wonder-1.0")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then that id is what gets sent
    assert posted(transport)[2]["model"] == "muse-wonder-1.0"


def test_constructor_model_overrides_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the env says Wonder and the constructor says Muse Spark
    monkeypatch.setenv("SURMAP_META_MODEL", "muse-wonder-1.0")
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(model="muse-spark-1.3", api_key=_API_KEY, transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the constructor id wins
    assert posted(transport)[2]["model"] == "muse-spark-1.3"


@pytest.mark.parametrize("model_id", ["muse-wonder-full", "muse-wonder_full", "Muse-Wonder-Full"])
def test_muse_wonder_full_is_refused(model_id: str) -> None:
    # Given a Muse Wonder Full id, which the credits do not cover
    # When the client is constructed
    with pytest.raises(MetaMuseSceneError, match="Wonder Full"):
        MetaMuseSceneClient(model=model_id, api_key=_API_KEY, transport=UnusedTransport())


def test_the_baseten_open_model_id_is_refused_on_this_api() -> None:
    # Given the open-weight slug that belongs on Baseten
    # When the client is constructed
    with pytest.raises(MetaMuseSceneError, match="Baseten"):
        MetaMuseSceneClient(
            model="meta-models/muse-spark-open-1026",
            api_key=_API_KEY,
            transport=UnusedTransport(),
        )


def test_scene_note_requires_model_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no key in the environment and none on the client
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(transport=transport)

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="MODEL_API_KEY") as raised:
        client.note(("debris",), a_jpeg())

    # Then nothing was posted and the error does not invent a bearer token
    assert transport.calls == []
    assert "Bearer" not in str(raised.value)


def test_scene_note_reads_the_key_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given the key only in the environment
    monkeypatch.setenv("MODEL_API_KEY", _API_KEY)
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(transport=transport)

    # When the note is requested
    client.note(("debris",), a_jpeg())

    # Then the bearer header is that key and the body does not contain it
    _url, headers, body = posted(transport)
    assert headers["Authorization"] == f"Bearer {_API_KEY}"
    assert _API_KEY not in json.dumps(body)


def test_a_failed_call_does_not_report_the_api_key() -> None:
    # Given a transport that fails the HTTP call
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=FailingTransport())

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="HTTP 401") as raised:
        client.note(("debris",), a_jpeg())

    # Then the key is absent from the error and from the client's repr
    assert _API_KEY not in str(raised.value)
    assert _API_KEY not in repr(client)


def test_scene_note_refuses_a_frame_that_is_not_a_jpeg() -> None:
    # Given bytes that are not a JPEG
    transport = RecordingTransport(a_message("Debris across the road."))
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="JPEG"):
        client.note(("debris",), b"not-a-jpeg")

    # Then nothing was posted
    assert transport.calls == []


def test_a_response_with_only_reasoning_text_is_refused() -> None:
    # Given an output list that never produces a message
    transport = RecordingTransport(
        {
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "output_text", "text": "still reasoning"}],
                }
            ]
        }
    )
    client = MetaMuseSceneClient(api_key=_API_KEY, transport=transport)

    # When the note is requested
    with pytest.raises(MetaMuseSceneError, match="no scene-note text"):
        client.note(("debris",), a_jpeg())


def test_the_urllib_transport_posts_json_and_reads_the_object() -> None:
    # Given a loopback server that records one POST
    captured_body: list[bytes] = []
    captured_auth: list[str | None] = []
    server, thread = _serve(_recording_handler(captured_body, captured_auth, status=200))
    host, port = _address(server)
    try:
        # When the transport posts a JSON body
        result = UrllibMetaMuseTransport().post_json(
            f"http://{host}:{port}/v1/responses",
            {"Authorization": f"Bearer {_API_KEY}"},
            {"model": "muse-spark-1.3", "stream": False},
        )
    finally:
        _stop(server, thread)

    # Then the object comes back and the key stayed in the header
    assert result == {"ok": True}
    assert captured_auth == [f"Bearer {_API_KEY}"]
    assert json.loads(captured_body[0].decode("utf-8"))["model"] == "muse-spark-1.3"


def test_the_urllib_transport_does_not_follow_redirects_or_echo_the_body() -> None:
    # Given a server that redirects and would echo a leaked token on the next path
    captured_paths: list[str] = []
    server, thread = _serve(_redirect_handler(captured_paths))
    host, port = _address(server)
    try:
        # When the transport posts
        with pytest.raises(MetaMuseSceneError, match="HTTP 302") as raised:
            UrllibMetaMuseTransport().post_json(
                f"http://{host}:{port}/v1/responses",
                {"Authorization": f"Bearer {_API_KEY}"},
                {"model": "muse-spark-1.3"},
            )
    finally:
        _stop(server, thread)

    # Then the error is the redirect itself and the next path was never requested
    assert captured_paths == ["/v1/responses"]
    assert "leaked-token" not in str(raised.value)
    assert _API_KEY not in str(raised.value)


def test_the_urllib_transport_hides_an_error_body() -> None:
    # Given a server that returns 500 with a body containing the key
    captured_body: list[bytes] = []
    captured_auth: list[str | None] = []
    server, thread = _serve(_recording_handler(captured_body, captured_auth, status=500))
    host, port = _address(server)
    try:
        # When the transport posts
        with pytest.raises(MetaMuseSceneError, match="HTTP 500") as raised:
            UrllibMetaMuseTransport().post_json(
                f"http://{host}:{port}/v1/responses",
                {"Authorization": f"Bearer {_API_KEY}"},
                {"model": "muse-spark-1.3"},
            )
    finally:
        _stop(server, thread)

    # Then the status is reported and the response body is not
    assert "leaked-token" not in str(raised.value)
    assert _API_KEY not in str(raised.value)


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 to call the Meta Model API",
)
def test_live_scene_note_returns_text_for_a_mapped_frame() -> None:
    # Given a tiny JPEG and the key already in the environment
    client = MetaMuseSceneClient()

    # When a live scene note is requested
    note = client.note(("debris", "vehicle"), a_jpeg())

    # Then the API returned a non-empty note and the key is not in the repr
    assert note.strip()
    assert "MODEL_API_KEY" not in repr(client)
    env_key = os.environ.get("MODEL_API_KEY", "")
    assert not env_key or env_key not in repr(client)
    assert env_key not in note


def _recording_handler(
    captured_body: list[bytes],
    captured_auth: list[str | None],
    *,
    status: int,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            captured_body.append(self.rfile.read(length))
            captured_auth.append(self.headers.get("Authorization"))
            if status != 200:
                payload = b'{"error":"leaked-token","key":"scene-note-test-key"}'
            else:
                payload = b'{"ok":true}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def _redirect_handler(captured_paths: list[str]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            self.rfile.read(length)
            captured_paths.append(self.path)
            if self.path == "/stolen":
                payload = b'{"ok":true,"body":"leaked-token"}'
                self.send_response(200)
            else:
                payload = b"leaked-token"
                self.send_response(302)
                self.send_header("Location", "/stolen")
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def _serve(
    handler: type[BaseHTTPRequestHandler],
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _address(server: ThreadingHTTPServer) -> tuple[str, int]:
    host, port = server.server_address[:2]
    assert isinstance(host, str)
    assert isinstance(port, int)
    return host, port


def _stop(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
