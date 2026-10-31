"""Modal GPU SAM 3.1 client.

The endpoint is fake. Nothing here imports the Modal SDK. The deploy
file is checked with the AST so CI never imports ``modal``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import pytest

from surmap.survey.modal_sam import (
    CHECK_IMAGE,
    ModalSamDetector,
    encode_image_request,
    pack_detections,
    parse_detections,
)
from surmap.survey.sam3 import Sam3Unavailable
from surmap.survey.station_main import StationConfigError, resolve_detector

_APP_SOURCE = Path("src/surmap/survey/modal_sam_app.py")


def _person_response() -> bytes:
    return json.dumps(
        {
            "prompt": "person",
            "inference_seconds": 1.25,
            "detections": [
                {
                    "label": "person",
                    "score": 0.91,
                    "box_xyxy": [4.0, 8.0, 20.0, 24.0],
                    "mask_polygon": [[4.0, 8.0], [20.0, 8.0], [20.0, 24.0], [4.0, 24.0]],
                }
            ],
        }
    ).encode()


def test_an_unset_url_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no Modal URL, and a poster that would fail the test if called
    monkeypatch.delenv("MODAL_SAM_URL", raising=False)

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    # When the detector is constructed
    # Then it refuses before the poster exists to be called
    with pytest.raises(Sam3Unavailable, match="MODAL_SAM_URL"):
        ModalSamDetector(poster=poster)


def test_a_blank_url_fails_before_any_request() -> None:
    # Given a blank URL
    # When the detector is constructed
    # Then it refuses
    with pytest.raises(Sam3Unavailable, match="MODAL_SAM_URL"):
        ModalSamDetector(url="  ")


def test_a_fake_endpoint_returning_a_person_yields_a_polygon() -> None:
    # Given an endpoint that returns one person box and outline
    seen: list[dict[str, Any]] = []

    def poster(url: str, body: bytes) -> bytes:
        assert url == "http://modal.test/sam"
        payload = json.loads(body)
        seen.append(payload)
        return _person_response()

    detector = ModalSamDetector(url="http://modal.test/sam", prompt="person", poster=poster)

    # When the image is segmented
    detections = detector.segment(b"\xff\xd8\xff fake-jpeg", media_type="image/jpeg")

    # Then the prompt went out and the detection has a polygon and a box
    assert seen[0]["prompt"] == "person"
    assert seen[0]["media_type"] == "image/jpeg"
    assert detections[0].label == "person"
    assert detections[0].box_xyxy == (4.0, 8.0, 20.0, 24.0)
    assert len(detections[0].mask_polygon) == 4
    assert detector.last_inference_seconds == 1.25


def test_mask_outlines_keep_the_rectangle_and_the_gpu_seconds() -> None:
    # Given one rectangular mask, its box, and a measured GPU time
    masks = np.zeros((1, 32, 32), dtype=np.float32)
    masks[0, 8:24, 4:20] = 1.0
    boxes = np.array([[4.0, 8.0, 20.0, 24.0]], dtype=np.float32)
    scores = np.array([0.9], dtype=np.float32)

    # When the remote packs that output
    payload = pack_detections(
        "person",
        masks,
        boxes,
        scores,
        image_width=32,
        image_height=32,
        inference_seconds=0.4,
    )
    detections, elapsed = parse_detections(json.dumps(payload).encode())

    # Then the polygon is non-empty and the GPU time is the remote figure
    assert elapsed == 0.4
    assert detections[0].label == "person"
    assert len(detections[0].mask_polygon) >= 4


def test_before_call_names_modal_and_can_block_the_request() -> None:
    # Given a hook that refuses the provider
    seen: list[str] = []

    def before_call(provider: str) -> None:
        seen.append(provider)
        raise RuntimeError("blocked")

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    detector = ModalSamDetector(
        url="http://modal.test/sam",
        before_call=before_call,
        poster=poster,
    )

    # When inference is attempted
    with pytest.raises(RuntimeError, match="blocked"):
        detector.segment(b"\xff\xd8\xff")

    # Then the hook saw the provider and the endpoint was not called
    assert seen == ["modal"]


def test_usage_hooks_record_one_modal_request_and_remote_gpu_seconds() -> None:
    # Given a fake endpoint that reports 1.25 seconds of GPU time
    usage: list[tuple[str, str, int, int, int | None]] = []
    gpu_seconds: list[float] = []
    order: list[str] = []

    def before_call(provider: str) -> None:
        order.append(provider)

    def on_usage(
        provider: str, model: str, input_tokens: int, output_tokens: int, cached: int | None
    ) -> None:
        usage.append((provider, model, input_tokens, output_tokens, cached))
        order.append("usage")

    def on_gpu_seconds(seconds: float) -> None:
        gpu_seconds.append(seconds)
        order.append("gpu")

    def poster(url: str, body: bytes) -> bytes:
        del url, body
        order.append("post")
        return _person_response()

    detector = ModalSamDetector(
        url="http://modal.test/sam",
        model="surmap-sam/L4",
        before_call=before_call,
        on_usage=on_usage,
        on_gpu_seconds=on_gpu_seconds,
        poster=poster,
    )

    # When one image is posted
    detector.segment(b"\xff\xd8\xff")

    # Then token counts stay zero and GPU time is the remote figure
    assert usage == [("modal", "surmap-sam/L4", 0, 0, None)]
    assert gpu_seconds == [1.25]
    assert order == ["modal", "post", "usage", "gpu"]


class _SavedUse(Protocol):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float


class _Ledger:
    """Stand-in for ``surmap.usage.UsageLedger``."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.order: list[str] = []
        self.checked: list[str] = []
        self.records: list[_SavedUse] = []

    def check(self, provider: str) -> None:
        self.order.append("check")
        self.checked.append(provider)
        if self.refuse:
            raise RuntimeError("budget")

    def __call__(self, record: object) -> None:
        self.order.append("usage")
        self.records.append(cast(_SavedUse, record))


def test_a_usage_ledger_is_checked_then_records_one_zero_token_call() -> None:
    # Given a ledger with the same check/call shape as surmap.usage.UsageLedger
    ledger = _Ledger()

    def poster(url: str, body: bytes) -> bytes:
        del url, body
        ledger.order.append("post")
        return _person_response()

    detector = ModalSamDetector(
        url="http://modal.test/sam",
        model="surmap-sam/L4",
        before_call=ledger,
        on_usage=ledger,
        on_gpu_seconds=ledger,
        poster=poster,
    )

    # When one image is posted
    detector.segment(b"\xff\xd8\xff")

    # Then the ledger is asked first and GPU time does not become a second line
    assert ledger.order == ["check", "post", "usage"]
    assert ledger.checked == ["modal"]
    recorded = ledger.records[0]
    assert recorded.provider == "modal"
    assert recorded.model == "surmap-sam/L4"
    assert recorded.input_tokens == 0
    assert recorded.output_tokens == 0
    assert recorded.reasoning_tokens is None
    assert isinstance(recorded.t_unix, float)


def test_a_usage_ledger_check_can_block_the_request() -> None:
    # Given a ledger that refuses the provider
    ledger = _Ledger(refuse=True)

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    detector = ModalSamDetector(url="http://modal.test/sam", before_call=ledger, poster=poster)

    # When inference is attempted
    with pytest.raises(RuntimeError, match="budget"):
        detector.segment(b"\xff\xd8\xff")

    # Then nothing was posted
    assert ledger.records == []


def _module_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_APP_SOURCE.read_text(encoding="utf-8"))
    found = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(found) == 1
    nested = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert nested == found
    return found[0]


def _keyword(call: ast.Call, name: str) -> ast.keyword | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword
    return None


def test_the_deploy_function_is_defined_at_module_scope() -> None:
    # Given the Modal app source, which CI does not import
    segment = _module_function("segment")
    decorators = [node for node in segment.decorator_list if isinstance(node, ast.Call)]

    # When the decorators are read
    function_call = next(
        call
        for call in decorators
        if isinstance(call.func, ast.Attribute) and call.func.attr == "function"
    )
    endpoint_call = next(
        call
        for call in decorators
        if isinstance(call.func, ast.Attribute) and call.func.attr == "fastapi_endpoint"
    )

    # Then the web function is global, capped, and not kept warm
    assert isinstance(function_call.func, ast.Attribute)
    assert isinstance(function_call.func.value, ast.Name)
    assert function_call.func.value.id == "app"
    assert _keyword(function_call, "min_containers") is None
    assert _keyword(function_call, "keep_warm") is None
    assert _keyword(function_call, "serialized") is None
    max_containers = _keyword(function_call, "max_containers")
    assert max_containers is not None
    assert isinstance(max_containers.value, ast.Constant)
    assert max_containers.value.value == 1
    assert _keyword(function_call, "timeout") is not None
    assert _keyword(function_call, "scaledown_window") is not None
    assert _keyword(function_call, "gpu") is not None
    assert _keyword(function_call, "secrets") is not None
    assert _keyword(function_call, "volumes") is not None
    method = _keyword(endpoint_call, "method")
    assert method is not None
    assert isinstance(method.value, ast.Constant)
    assert method.value.value == "POST"
    source = _APP_SOURCE.read_text(encoding="utf-8")
    assert 'DEFAULT_GPU = "L4"' in source
    assert '"900"' in source
    assert '"60"' in source
    assert 'Secret.from_name("huggingface")' in source or "HF_SECRET" in source
    assert "surmap-sam3" in source
    assert "facebook/sam3.1" in source or 'version="sam3.1"' in source
    assert "import modal\n" in source


def test_importing_the_client_does_not_import_modal() -> None:
    # Given a fresh look at the client module
    import sys

    import surmap.survey.modal_sam as client

    # When it has been imported
    # Then the Modal SDK was not loaded
    assert client.ModalSamDetector is not None
    assert "modal" not in sys.modules


def test_the_check_image_is_a_jpeg() -> None:
    # Given the bundled person image
    image = Path(CHECK_IMAGE)

    # When it is read
    data = image.read_bytes()

    # Then it is a small JPEG the check script can post
    assert data.startswith(b"\xff\xd8")
    assert len(data) < 50_000


def test_encode_image_request_carries_the_prompt() -> None:
    # Given a JPEG and a prompt
    body = encode_image_request(b"\xff\xd8\xff", prompt="person", media_type="image/jpeg")

    # When the body is parsed
    payload = json.loads(body)

    # Then the prompt and the image are both present
    assert payload["prompt"] == "person"
    assert payload["media_type"] == "image/jpeg"
    assert isinstance(payload["image_b64"], str)


def test_station_sam3_modal_uses_the_remote_detector_without_a_local_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a URL and no checkpoint on disk
    monkeypatch.setenv("MODAL_SAM_URL", "http://modal.test/sam")

    # When the station entrypoint resolves --detector sam3-modal
    detector = resolve_detector(detector="sam3-modal", device="auto", model=None, label="person")

    # Then the detector is the Modal session and the prompt is the label
    assert detector is not None
    assert detector.provider == "modal"
    assert isinstance(detector, ModalSamDetector)
    assert detector.prompt == "person"


def test_station_sam3_device_modal_uses_the_remote_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a URL
    monkeypatch.setenv("MODAL_SAM_URL", "http://modal.test/sam")

    # When the device flag selects Modal
    detector = resolve_detector(detector="sam3", device="modal", model=None, label="person")

    # Then no local model path is required
    assert detector is not None
    assert detector.provider == "modal"


def test_station_sam3_on_cpu_still_requires_a_local_model() -> None:
    # Given the local ONNX detector and no model path
    # When the station resolves it
    # Then the configuration error names the missing file
    with pytest.raises(StationConfigError, match="sam3-model"):
        resolve_detector(detector="sam3", device="cpu", model=None, label="object")


def test_a_local_cpu_model_still_resolves() -> None:
    # Given the fake checkpoint the CPU path already runs
    model = Path(__file__).parent / "fixtures" / "sam3_fake" / "fake_sam3.onnx"

    # When the station resolves a CPU detector
    detector = resolve_detector(detector="sam3", device="cpu", model=model, label="object")

    # Then the provider is ONNX Runtime's CPU execution provider
    assert detector is not None
    assert detector.provider == "CPUExecutionProvider"
