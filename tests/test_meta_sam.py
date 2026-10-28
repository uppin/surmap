"""Meta Model API SAM 3.1 adapter.

The detector is exercised through a fake Responses transport. Nothing
here downloads weights, starts another process, or calls api.meta.ai.
A live call exists only behind SURMAP_LIVE_META=1.
"""

from __future__ import annotations

import base64
import io
import os
import urllib.request
from collections.abc import Mapping

import pytest
from PIL import Image

from surmap.survey.meta_sam import (
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_CALLS_PER_SESSION,
    DEFAULT_MODEL,
    MetaSamCallLimit,
    MetaSamDetector,
    MetaSamError,
)
from surmap.survey.sam import RawFrame, SamDetection, SamDetector

FIXTURE_KEY = "fixture-key"
PUBLISHED_ONE_BIT_MASK = "!!!!!(QO(0lu8?"
ONE_OBJECT_LINE = (
    "<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80;c=0.75|>"
    f"<|mask;x=0;y=0;c=0.75;data=5,5,{PUBLISHED_ONE_BIT_MASK}|>"
)
TWO_OBJECT_LINE = (
    ONE_OBJECT_LINE + ",1<|box;x1=30;y1=40;x2=34;y2=44;w=100;h=80;c=0.4|>"
    f"<|mask;x=0;y=0;c=0.4;data=5,5,{PUBLISHED_ONE_BIT_MASK}|>"
)
UNSCORED_LINE = (
    "<0f>3<|box;x1=10;y1=20;x2=14;y2=24;w=100;h=80|>"
    f"<|mask;x=0;y=0;data=5,5,{PUBLISHED_ONE_BIT_MASK}|>"
)


def a_jpeg_frame() -> RawFrame:
    image = Image.new("RGB", (8, 8), (20, 40, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return RawFrame(7, 700, 0, 8, 8, "mjpeg", buffer.getvalue())


def a_raw_frame() -> RawFrame:
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255])
    return RawFrame(1, 1, 0, 2, 2, "raw_rgb", pixels)


def a_response(
    text: str,
    *,
    input_tokens: int = 11,
    output_tokens: int = 22,
    reasoning: int | None = None,
) -> dict[str, object]:
    usage: dict[str, object] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if reasoning is not None:
        usage["output_tokens_details"] = {"reasoning_tokens": reasoning}
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": usage,
    }


class RecordingTransport:
    """Stands in for HTTPS: records the call and returns one canned body."""

    def __init__(self, body: Mapping[str, object]) -> None:
        self.body = body
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.payloads: list[Mapping[str, object]] = []

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.urls.append(url)
        self.headers.append(dict(headers))
        self.payloads.append(payload)
        return self.body


class FailingTransport:
    """A transport whose request fails after the detector has decided to send."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        self.calls += 1
        raise MetaSamError(self.message)


def _content(payload: Mapping[str, object]) -> list[object]:
    messages = payload["input"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    return content


def _image_url(payload: Mapping[str, object]) -> str:
    for part in _content(payload):
        if isinstance(part, dict) and part.get("type") == "input_image":
            url = part["image_url"]
            assert isinstance(url, str)
            return url
    raise AssertionError("request has no input_image")


def _prompt_text(payload: Mapping[str, object]) -> str:
    for part in _content(payload):
        if isinstance(part, dict) and part.get("type") == "input_text":
            text = part["text"]
            assert isinstance(text, str)
            return text
    raise AssertionError("request has no input_text")


def is_one_roof_detection(detection: SamDetection) -> bool:
    x_min, y_min, x_max, y_max = detection.box_xyxy
    polygon_on_box = all(
        x_min <= x <= x_max and y_min <= y <= y_max for x, y in detection.mask_polygon
    )
    return (
        detection.label == "roof"
        and detection.score == 0.75
        and detection.box_xyxy == (10.0, 20.0, 15.0, 25.0)
        and detection.track_id == 0
        and len(detection.mask_polygon) >= 4
        and polygon_on_box
    )


def is_sam_image_request(
    transport: RecordingTransport, frame: RawFrame, *, model: str, prompt: str
) -> bool:
    payload = transport.payloads[0]
    messages = payload["input"]
    assert isinstance(messages, list)
    message = messages[0]
    assert isinstance(message, dict)
    url = _image_url(payload)
    encoded = url.removeprefix("data:image/jpeg;base64,")
    jpeg = base64.b64decode(encoded)
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    return (
        transport.urls == [DEFAULT_ENDPOINT]
        and transport.headers[0]["Authorization"] == f"Bearer {FIXTURE_KEY}"
        and payload["model"] == model
        and payload["stream"] is False
        and message["type"] == "message"
        and message["role"] == "user"
        and _prompt_text(payload) == prompt
        and url.startswith("data:image/jpeg;base64,")
        and jpeg == frame.data
        and metadata["include_confidence"] == "true"
        and metadata["mask_encoding"] == "one_bit"
    )


async def test_a_box_and_mask_become_one_detection_with_a_polygon() -> None:
    # Given a Responses body with one box and the published 5×5 one_bit mask
    transport = RecordingTransport(a_response(ONE_OBJECT_LINE))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, prompt="roof", transport=transport)

    # When the detector segments one frame
    detections = await detector.detect(a_jpeg_frame())

    # Then that match is one SamDetection whose polygon follows the mask
    assert isinstance(detector, SamDetector)
    (detection,) = detections
    assert is_one_roof_detection(detection)


async def test_two_wire_records_become_two_detections() -> None:
    # Given a frame line with object 0 and object 1
    transport = RecordingTransport(a_response(TWO_OBJECT_LINE))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, prompt="roof", transport=transport)

    # When the frame is segmented
    detections = await detector.detect(a_jpeg_frame())

    # Then both objects come back, under the ids the wire used
    assert [item.track_id for item in detections] == [0, 1]
    assert [item.score for item in detections] == [0.75, 0.4]


async def test_a_record_without_confidence_scores_one() -> None:
    # Given a box and mask that omit the c field
    transport = RecordingTransport(a_response(UNSCORED_LINE))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, prompt="roof", transport=transport)

    # When the frame is segmented
    (detection,) = await detector.detect(a_jpeg_frame())

    # Then the detection is kept and its score is 1
    assert detection.score == 1.0
    assert detection.track_id == 3
    assert len(detection.mask_polygon) >= 4


async def test_a_low_score_is_dropped() -> None:
    # Given a match whose confidence is 0.4 and a threshold of 0.5
    transport = RecordingTransport(a_response(TWO_OBJECT_LINE))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        prompt="roof",
        transport=transport,
        score_threshold=0.5,
    )

    # When the frame is segmented
    detections = await detector.detect(a_jpeg_frame())

    # Then only the 0.75 match remains
    assert [item.score for item in detections] == [0.75]


async def test_an_empty_output_text_is_no_detections() -> None:
    # Given a completed response whose output text is empty
    seen: list[tuple[str, str, int, int, int | None]] = []
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        transport=transport,
        on_usage=lambda provider, model, incoming, outgoing, reasoning: seen.append(
            (provider, model, incoming, outgoing, reasoning)
        ),
    )

    # When the frame is segmented
    detections = await detector.detect(a_jpeg_frame())

    # Then nothing matched, and the token usage was still reported
    assert detections == ()
    assert seen == [("meta", DEFAULT_MODEL, 11, 22, None)]


async def test_usage_reports_reasoning_tokens_when_the_body_has_them() -> None:
    # Given a usage object that includes reasoning tokens
    seen: list[tuple[str, str, int, int, int | None]] = []
    transport = RecordingTransport(a_response(ONE_OBJECT_LINE, reasoning=0))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        model="sam-3.1",
        transport=transport,
        on_usage=lambda provider, model, incoming, outgoing, reasoning: seen.append(
            (provider, model, incoming, outgoing, reasoning)
        ),
    )

    # When the frame is segmented
    await detector.detect(a_jpeg_frame())

    # Then the hook receives provider, model, and the three counts
    assert seen == [("meta", "sam-3.1", 11, 22, 0)]


async def test_the_detector_posts_the_documented_sam_request() -> None:
    # Given a jpeg frame and the default model id
    frame = a_jpeg_frame()
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, prompt="roof", transport=transport)

    # When the frame is segmented
    await detector.detect(frame)

    # Then the body is one non-streaming sam-3.1 image request
    assert is_sam_image_request(transport, frame, model=DEFAULT_MODEL, prompt="roof")


async def test_a_configured_model_id_is_what_gets_posted_and_reported() -> None:
    # Given a detector pointed at a non-default model id
    seen: list[str] = []
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        model="sam-3.1-preview",
        transport=transport,
        on_usage=lambda _provider, model, _incoming, _outgoing, _reasoning: seen.append(model),
    )

    # When the frame is segmented
    await detector.detect(a_jpeg_frame())

    # Then both the request and the usage hook use that id
    assert transport.payloads[0]["model"] == "sam-3.1-preview"
    assert seen == ["sam-3.1-preview"]


async def test_a_raw_rgb_frame_is_sent_as_a_png_data_url() -> None:
    # Given a raw RGB frame
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=transport)

    # When the frame is segmented
    await detector.detect(a_raw_frame())

    # Then the image part is a PNG data URL of those pixels
    encoded = _image_url(transport.payloads[0]).removeprefix("data:image/png;base64,")
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        assert image.size == (2, 2)
        assert image.convert("RGB").getpixel((0, 0)) == (255, 0, 0)


async def test_before_call_can_block_the_request() -> None:
    # Given a hook that refuses the provider
    transport = RecordingTransport(a_response(ONE_OBJECT_LINE))

    def block(provider: str) -> None:
        raise RuntimeError(f"blocked {provider}")

    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=transport, before_call=block)

    # When a frame is segmented
    with pytest.raises(RuntimeError, match="blocked meta"):
        await detector.detect(a_jpeg_frame())

    # Then no request was sent and the session budget was not spent
    assert transport.urls == []
    assert detector.calls_made == 0


async def test_a_session_stops_at_its_call_limit() -> None:
    # Given a detector allowed two Meta calls
    providers: list[str] = []
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        transport=transport,
        max_calls_per_session=2,
        before_call=providers.append,
    )

    # When two frames are segmented and a third is requested
    await detector.detect(a_jpeg_frame())
    await detector.detect(a_jpeg_frame())
    with pytest.raises(MetaSamCallLimit, match="2"):
        await detector.detect(a_jpeg_frame())

    # Then Meta was asked twice and the third frame never left the process
    assert providers == ["meta", "meta"]
    assert transport.urls == [DEFAULT_ENDPOINT, DEFAULT_ENDPOINT]
    assert detector.calls_made == 2


def test_the_default_session_cap_is_two_hundred() -> None:
    # Given a detector constructed without a call cap
    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=RecordingTransport(a_response("")))

    # Then the cap is the demo-replay default
    assert detector.max_calls_per_session == DEFAULT_MAX_CALLS_PER_SESSION
    assert DEFAULT_MAX_CALLS_PER_SESSION == 200


def test_a_model_id_containing_wonder_is_rejected() -> None:
    # Given a model id that names a model this project does not use
    # When a detector is constructed with it
    with pytest.raises(ValueError, match="wonder"):
        MetaSamDetector(api_key=FIXTURE_KEY, model="muse-wonder-1")


async def test_a_missing_key_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no API key in the constructor or the environment
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(transport=transport)

    # When a frame is segmented
    with pytest.raises(MetaSamError, match="MODEL_API_KEY"):
        await detector.detect(a_jpeg_frame())

    # Then nothing was posted
    assert transport.urls == []
    assert detector.calls_made == 0


async def test_a_transport_failure_still_counts_and_hides_the_key() -> None:
    # Given a transport that fails and echoes the bearer token
    transport = FailingTransport(f"rejected {FIXTURE_KEY}")
    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=transport)

    # When a frame is segmented
    with pytest.raises(MetaSamError, match="redacted") as raised:
        await detector.detect(a_jpeg_frame())

    # Then the call was spent and the error text does not carry the key
    assert FIXTURE_KEY not in str(raised.value)
    assert transport.calls == 1
    assert detector.calls_made == 1


async def test_prose_output_reports_usage_then_fails() -> None:
    # Given output text that is not the segmentation grammar
    seen: list[tuple[int, int]] = []
    transport = RecordingTransport(a_response("the model wrote prose"))
    detector = MetaSamDetector(
        api_key=FIXTURE_KEY,
        transport=transport,
        on_usage=lambda _provider, _model, incoming, outgoing, _reasoning: seen.append(
            (incoming, outgoing)
        ),
    )

    # When the frame is segmented
    with pytest.raises(MetaSamError, match="not segmentation"):
        await detector.detect(a_jpeg_frame())

    # Then usage was reported before the failure
    assert seen == [(11, 22)]


async def test_a_fake_transport_does_not_open_a_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given urlopen is wired to fail if anything touches the network
    def explode(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    transport = RecordingTransport(a_response(ONE_OBJECT_LINE))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, prompt="roof", transport=transport)

    # When the frame is segmented through the fake transport
    detections = await detector.detect(a_jpeg_frame())

    # Then the detection still comes back from the canned body
    assert len(detections) == 1
    assert is_one_roof_detection(detections[0])


@pytest.mark.skipif(
    os.environ.get("SURMAP_LIVE_META") != "1",
    reason="set SURMAP_LIVE_META=1 to call the Meta Model API",
)
async def test_a_live_meta_call_returns_sam_detections() -> None:
    # Given a one-call detector using MODEL_API_KEY from the environment
    detector = MetaSamDetector(prompt="object", max_calls_per_session=1)

    # When one tiny frame is segmented against the live API
    detections = await detector.detect(a_jpeg_frame())

    # Then the call returns a detection tuple
    assert isinstance(detections, tuple)
    assert detections == () or isinstance(detections[0], SamDetection)


async def test_an_unsupported_encoding_is_rejected_before_a_request() -> None:
    # Given a frame encoding the API adapter does not send
    transport = RecordingTransport(a_response(""))
    detector = MetaSamDetector(api_key=FIXTURE_KEY, transport=transport)
    frame = RawFrame(1, 1, 0, 1, 1, "yuv", b"\x00")

    # When the frame is segmented
    with pytest.raises(MetaSamError, match="unsupported frame encoding"):
        await detector.detect(frame)

    # Then the budget and the transport were not touched
    assert transport.urls == []
    assert detector.calls_made == 0
