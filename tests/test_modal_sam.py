"""Modal GPU session for the SAM 3.1 ONNX contract.

The endpoint is fake. Nothing here imports the Modal SDK or needs a
token. `Sam3Detector` is the same post-processor as the local session.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import pytest
from numpy.typing import NDArray

from surmap.survey.modal_sam import (
    ModalSamSession,
    encode_request,
    response_body,
)
from surmap.survey.modal_sam_app import build_app, load_app, segment_payload
from surmap.survey.sam import RawFrame
from surmap.survey.sam3 import Sam3Detector, Sam3Unavailable
from surmap.survey.station_main import StationConfigError, resolve_detector


class _FixedSession:
    """A `Sam3Session` that returns one prepared mask."""

    def __init__(self, masks: NDArray[np.float32], scores: NDArray[np.float32]) -> None:
        self._masks = masks
        self._scores = scores

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def input_size(self) -> tuple[int, int]:
        return (int(self._masks.shape[3]), int(self._masks.shape[2]))

    def run(
        self, image_chw: NDArray[np.float32]
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        del image_chw
        return self._masks, self._scores


def _rectangle_outputs() -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    masks = np.zeros((1, 1, 32, 32), dtype=np.float32)
    masks[0, 0, 8:24, 4:20] = 1.0
    scores = np.array([[0.9]], dtype=np.float32)
    return masks, scores


def _frame() -> RawFrame:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (32, 32), (0, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return RawFrame(1, 100, 0, 32, 32, "mjpeg", buffer.getvalue())


def _clock(*ticks: float) -> Callable[[], float]:
    pending = iter(ticks)

    def read() -> float:
        return next(pending)

    return read


@contextmanager
def _json_endpoint(payload: bytes) -> Iterator[str]:
    """A local HTTP server that answers every POST with `payload`."""

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    try:
        yield f"http://{host}:{port}/segment"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_an_unset_url_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given no Modal URL, and a poster that would fail the test if called
    monkeypatch.delenv("MODAL_SAM_URL", raising=False)

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    # When the session is constructed
    # Then it refuses before the poster exists to be called
    with pytest.raises(Sam3Unavailable, match="MODAL_SAM_URL"):
        ModalSamSession(poster=poster)


def test_a_blank_url_fails_before_any_request() -> None:
    # Given a blank URL overriding the environment
    # When the session is constructed
    # Then it refuses
    with pytest.raises(Sam3Unavailable, match="MODAL_SAM_URL"):
        ModalSamSession(url="  ")


async def test_a_fake_endpoint_returning_masks_yields_a_polygon() -> None:
    # Given an endpoint that returns one rectangle mask and a score
    masks, scores = _rectangle_outputs()
    payload = json.dumps(response_body(masks, scores, 0.05)).encode()

    with _json_endpoint(payload) as url:
        session = ModalSamSession(url=url, input_size=(32, 32), model="surmap-sam/T4")
        detector = Sam3Detector(session, label="debris")

        # When the station detector segments a frame
        detections = await detector.detect(_frame())

    # Then the shared post-processor emits one detection with an outline
    assert len(detections) == 1
    assert detections[0].label == "debris"
    assert len(detections[0].mask_polygon) >= 4


def test_before_call_names_modal_and_can_block_the_request() -> None:
    # Given a hook that refuses the provider, and a poster that must not run
    seen: list[str] = []

    def before_call(provider: str) -> None:
        seen.append(provider)
        raise RuntimeError("blocked")

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    session = ModalSamSession(
        url="http://modal.test/sam",
        input_size=(32, 32),
        before_call=before_call,
        poster=poster,
    )
    image = np.zeros((1, 3, 32, 32), dtype=np.float32)

    # When inference is attempted
    with pytest.raises(RuntimeError, match="blocked"):
        session.run(image)

    # Then the hook saw the provider and the endpoint was not called
    assert seen == ["modal"]


class _SavedUse(Protocol):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None
    t_unix: float


class _Ledger:
    """Stand-in for ``surmap.usage.UsageLedger``: ``check`` plus one record call."""

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
    masks, scores = _rectangle_outputs()
    body = json.dumps(response_body(masks, scores, 1.25)).encode()
    ledger = _Ledger()

    def poster(url: str, body_bytes: bytes) -> bytes:
        del url, body_bytes
        ledger.order.append("post")
        return body

    session = ModalSamSession(
        url="http://modal.test/sam",
        input_size=(32, 32),
        model="surmap-sam/T4",
        before_call=ledger,
        on_usage=ledger,
        on_gpu_seconds=ledger,
        poster=poster,
    )

    # When one tensor is posted
    session.run(np.zeros((1, 3, 32, 32), dtype=np.float32))

    # Then the ledger is asked first, one zero-token call is stored, and GPU time
    # does not become a second ledger line
    assert ledger.order == ["check", "post", "usage"]
    assert ledger.checked == ["modal"]
    assert len(ledger.records) == 1
    recorded = ledger.records[0]
    assert recorded.provider == "modal"
    assert recorded.model == "surmap-sam/T4"
    assert recorded.input_tokens == 0
    assert recorded.output_tokens == 0
    assert recorded.reasoning_tokens is None
    assert isinstance(recorded.t_unix, float)


def test_a_usage_ledger_check_can_block_the_request() -> None:
    # Given a ledger that refuses the provider
    ledger = _Ledger(refuse=True)

    def poster(url: str, body: bytes) -> bytes:
        raise AssertionError(f"request was sent to {url} ({len(body)} bytes)")

    session = ModalSamSession(
        url="http://modal.test/sam",
        input_size=(32, 32),
        before_call=ledger,
        poster=poster,
    )

    # When inference is attempted
    with pytest.raises(RuntimeError, match="budget"):
        session.run(np.zeros((1, 3, 32, 32), dtype=np.float32))

    # Then nothing was posted and nothing was recorded
    assert ledger.records == []


def test_usage_hooks_record_one_modal_request_and_remote_gpu_seconds() -> None:
    # Given a fake endpoint that reports 1.25 seconds of inference
    masks, scores = _rectangle_outputs()
    body = json.dumps(response_body(masks, scores, 1.25)).encode()
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

    def poster(url: str, body_bytes: bytes) -> bytes:
        assert url == "http://modal.test/sam"
        sent = json.loads(body_bytes)
        assert sent["shape"] == [1, 3, 32, 32]
        order.append("post")
        return body

    session = ModalSamSession(
        url="http://modal.test/sam",
        input_size=(32, 32),
        model="surmap-sam/T4",
        before_call=before_call,
        on_usage=on_usage,
        on_gpu_seconds=on_gpu_seconds,
        poster=poster,
    )

    # When the session runs one tensor
    returned_masks, returned_scores = session.run(np.zeros((1, 3, 32, 32), dtype=np.float32))

    # Then token counts stay zero, GPU time is the remote figure, and the hook ran first
    assert returned_masks.shape == (1, 1, 32, 32)
    assert returned_scores.shape == (1, 1)
    assert usage == [("modal", "surmap-sam/T4", 0, 0, None)]
    assert gpu_seconds == [1.25]
    assert order == ["modal", "post", "usage", "gpu"]


def test_the_remote_function_returns_its_own_elapsed_inference_time() -> None:
    # Given a session and a clock that advances 1.5 seconds across the call
    masks, scores = _rectangle_outputs()
    image = np.zeros((1, 3, 8, 8), dtype=np.float32)
    payload = json.loads(encode_request(image))

    # When the remote function runs
    result = segment_payload(
        payload, session=_FixedSession(masks, scores), clock=_clock(10.0, 11.5)
    )

    # Then the response carries that elapsed time and the session's masks
    assert result["inference_seconds"] == 1.5
    assert result["masks_shape"] == [1, 1, 32, 32]
    assert result["scores_shape"] == [1, 1]


class _RecordingImage:
    packages: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def pip_install(self, *packages: str) -> _RecordingImage:
        self.packages = packages
        return self

    def add_local_python_source(self, *sources: str) -> _RecordingImage:
        self.sources = sources
        return self


class _RecordingVolume:
    def __init__(self, name: str, *, create_if_missing: bool) -> None:
        self.name = name
        self.create_if_missing = create_if_missing


class _RecordingApp:
    def __init__(self, name: str) -> None:
        self.name = name
        self.function_kwargs: dict[str, Any] | None = None

    def function(self, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        self.function_kwargs = kwargs

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorate


class _RecordingModal:
    endpoint_method: str | None = None
    built_app: _RecordingApp | None = None
    volume: _RecordingVolume | None = None
    image: _RecordingImage | None = None

    def App(self, name: str) -> _RecordingApp:
        self.built_app = _RecordingApp(name)
        return self.built_app

    def fastapi_endpoint(
        self, method: str = "GET"
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        self.endpoint_method = method

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorate

    class Image:
        @staticmethod
        def debian_slim(python_version: str = "3.11") -> _RecordingImage:
            del python_version
            return _RecordingImage()

    class Volume:
        @staticmethod
        def from_name(name: str, *, create_if_missing: bool = False) -> _RecordingVolume:
            return _RecordingVolume(name, create_if_missing=create_if_missing)


def test_the_published_function_caps_cost_and_mounts_the_checkpoint_volume() -> None:
    # Given a stand-in for the Modal SDK
    modal = _RecordingModal()

    # When the app is built with default settings
    app = build_app(modal)
    assert isinstance(app, _RecordingApp)
    kwargs = app.function_kwargs
    assert kwargs is not None

    # Then the GPU is small, idle time is short, and nothing is kept warm
    assert app.name == "surmap-sam"
    assert kwargs["gpu"] == "T4"
    assert kwargs["timeout"] == 300
    assert kwargs["scaledown_window"] == 60
    assert kwargs["max_containers"] == 1
    assert "min_containers" not in kwargs
    assert "keep_warm" not in kwargs
    assert modal.endpoint_method == "POST"
    volume = kwargs["volumes"]["/models"]
    assert isinstance(volume, _RecordingVolume)
    assert volume.name == "surmap-sam3"
    assert volume.create_if_missing is True
    image = kwargs["image"]
    assert isinstance(image, _RecordingImage)
    assert any("onnxruntime-gpu" in package for package in image.packages)
    assert "fastapi" in " ".join(image.packages)
    assert image.sources == ("surmap",)


def test_the_gpu_type_comes_from_the_environment() -> None:
    # Given a request for an L4 instead of the default T4
    modal = _RecordingModal()

    # When the app is built with that override
    app = build_app(modal, environ={"SURMAP_MODAL_GPU": "L4"})

    # Then the function asks Modal for an L4 and still does not keep a warm pool
    assert isinstance(app, _RecordingApp)
    assert app.function_kwargs is not None
    assert app.function_kwargs["gpu"] == "L4"
    assert "min_containers" not in app.function_kwargs


def test_loading_the_app_without_the_modal_package_returns_none() -> None:
    # Given an importer that cannot see Modal
    def missing(name: str) -> Any:
        raise ImportError(name)

    # When the deploy module asks for it
    # Then there is no app and no account is required
    assert load_app(missing) is None


def test_station_sam3_modal_uses_the_remote_session_without_a_local_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a URL and no checkpoint on disk
    monkeypatch.setenv("MODAL_SAM_URL", "http://modal.test/sam")

    # When the station entrypoint resolves --detector sam3-modal
    detector = resolve_detector(detector="sam3-modal", device="auto", model=None, label="debris")

    # Then the detector is the Modal session, not a local ONNX file
    assert detector is not None
    assert detector.provider == "modal"


def test_station_sam3_device_modal_uses_the_remote_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a URL
    monkeypatch.setenv("MODAL_SAM_URL", "http://modal.test/sam")

    # When the device flag selects Modal on the existing sam3 detector
    detector = resolve_detector(detector="sam3", device="modal", model=None, label="object")

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
