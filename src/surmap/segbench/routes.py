"""Detector wrappers for the three SAM routes, plus a recorded replay.

A live route refuses to call out unless its `SURMAP_LIVE_*` flag is set,
and it checks the process budget before the request. Meta is only handed
`raw_rgb` (or an already-legal `mjpeg` that this wrapper converts to
`raw_rgb` for scoring). The station ONNX route is local and has no live flag.
Replay reads a detections JSONL and does not construct a detector.
"""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image

from surmap.survey.sam import RawFrame, SamDetection, SamDetector
from surmap.usage import UsageLedger, UsageRecord

Clock = Callable[[], float]

LIVE_FLAGS = {
    "meta": "SURMAP_LIVE_META",
    "modal": "SURMAP_LIVE_MODAL",
}


class LiveRouteRefused(RuntimeError):
    """A hosted route was asked to run without its live flag."""


@dataclass(frozen=True)
class RouteObservation:
    """One frame's detections plus the cost of producing them."""

    frame_id: int
    t_ns: int
    source: str
    model_id: str
    latency_s: float
    input_tokens: int
    output_tokens: int
    gpu_seconds: float
    detections: tuple[SamDetection, ...]
    mask_ids: tuple[str, ...]


class UsageCapture:
    """Counts tokens and, when a ledger is set, appends a usage line."""

    def __init__(self, ledger: UsageLedger | None = None) -> None:
        self.ledger = ledger
        self.input_tokens = 0
        self.output_tokens = 0

    def __call__(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.ledger is not None:
            self.ledger(
                UsageRecord(
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    time.time(),
                )
            )


class BenchRoute:
    """Times one `SamDetector` and records tokens, GPU seconds, and the flag."""

    def __init__(
        self,
        detector: SamDetector,
        *,
        source: str,
        model_id: str,
        live_flag: str | None = None,
        provider: str | None = None,
        ledger: UsageLedger | None = None,
        prepare: Callable[[RawFrame], RawFrame] | None = None,
        clock: Clock | None = None,
        usage: UsageCapture | None = None,
    ) -> None:
        self._detector = detector
        self.source = source
        self.model_id = model_id
        self._live_flag = live_flag
        self._provider = provider
        self._ledger = ledger
        self._prepare = prepare
        self._clock = time.perf_counter if clock is None else clock
        self.usage = usage if usage is not None else UsageCapture(ledger)

    async def observe(self, frame: RawFrame) -> RouteObservation:
        """Segment one frame. A missing live flag raises before any request."""
        require_live(self.source)
        if self._ledger is not None and self._provider is not None:
            self._ledger.check(self._provider)
        prepared = frame if self._prepare is None else self._prepare(frame)
        if self.source == "meta" and prepared.encoding not in ("mjpeg", "raw_rgb"):
            raise ValueError(
                f"Meta SAM was handed encoding {prepared.encoding}; "
                "only mjpeg and raw_rgb are legal"
            )
        tokens_in = self.usage.input_tokens
        tokens_out = self.usage.output_tokens
        started = self._clock()
        detections = await self._detector.detect(prepared)
        elapsed = self._clock() - started
        mask_ids = tuple(f"{frame.frame_id}-{index}" for index in range(len(detections)))
        return RouteObservation(
            frame_id=frame.frame_id,
            t_ns=frame.t_ns,
            source=self.source,
            model_id=self.model_id,
            latency_s=elapsed,
            input_tokens=self.usage.input_tokens - tokens_in,
            output_tokens=self.usage.output_tokens - tokens_out,
            gpu_seconds=_gpu_seconds(self._detector),
            detections=detections,
            mask_ids=mask_ids,
        )


def require_live(source: str) -> None:
    """Raise when a hosted route's `SURMAP_LIVE_*` flag is not `1`.

    `station-onnx` and `replay` are local and pass. No socket is opened here.
    """
    flag = LIVE_FLAGS.get(source)
    if flag is None:
        return
    if os.environ.get(flag) != "1":
        raise LiveRouteRefused(f"Refusing to call {source}. Set {flag}=1. No request was sent.")


def frame_for_meta(frame: RawFrame) -> RawFrame:
    """Encode a bench image as `raw_rgb`, the form Meta SAM scores from.

    `mjpeg` and `raw_rgb` are the only encodings the adapter accepts.
    `raw_rgb` keeps the pixels the 2D metrics use, so a PNG or JPEG bench
    image is decoded rather than forwarded as `png`.
    """
    if frame.encoding == "raw_rgb":
        expected = frame.width * frame.height * 3
        if len(frame.data) != expected:
            raise ValueError(f"raw_rgb frame has {len(frame.data)} bytes, expected {expected}")
        return frame
    try:
        with Image.open(io.BytesIO(frame.data)) as image:
            rgb = image.convert("RGB")
    except Exception as exc:
        raise ValueError(f"Meta SAM cannot read encoding {frame.encoding}") from exc
    if rgb.size != (frame.width, frame.height):
        raise ValueError(
            f"frame is {rgb.size[0]}x{rgb.size[1]}, expected {frame.width}x{frame.height}"
        )
    return RawFrame(
        frame.frame_id,
        frame.t_ns,
        frame.channel,
        frame.width,
        frame.height,
        "raw_rgb",
        rgb.tobytes(),
    )


def replay_route(path: Path, *, clock: Clock | None = None) -> BenchRoute:
    """A detector that returns the JSONL recorded for each `frame_id`."""
    by_frame = {item.frame_id: item for item in read_detections_jsonl(path)}

    class _Replay:
        async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
            found = by_frame.get(frame.frame_id)
            if found is None:
                return ()
            return found.detections

    return BenchRoute(_Replay(), source="replay", model_id="recorded", clock=clock)


def meta_route(
    detector: SamDetector,
    *,
    model_id: str = "sam-3.1",
    ledger: UsageLedger | None = None,
    clock: Clock | None = None,
    usage: UsageCapture | None = None,
) -> BenchRoute:
    """Meta route. `observe` converts the frame and checks `SURMAP_LIVE_META`."""
    return BenchRoute(
        detector,
        source="meta",
        model_id=model_id,
        live_flag=LIVE_FLAGS["meta"],
        provider="meta",
        ledger=ledger,
        prepare=frame_for_meta,
        clock=clock,
        usage=usage,
    )


def modal_route(
    detector: SamDetector,
    *,
    model_id: str = "surmap-sam",
    ledger: UsageLedger | None = None,
    clock: Clock | None = None,
    usage: UsageCapture | None = None,
) -> BenchRoute:
    """Modal route. `observe` checks `SURMAP_LIVE_MODAL` before the detector runs."""
    return BenchRoute(
        detector,
        source="modal",
        model_id=model_id,
        live_flag=LIVE_FLAGS["modal"],
        provider="modal",
        ledger=ledger,
        clock=clock,
        usage=usage,
    )


def station_route(
    detector: SamDetector,
    *,
    model_id: str,
    clock: Clock | None = None,
    usage: UsageCapture | None = None,
) -> BenchRoute:
    """Station ONNX route. It runs locally and does not consult a live flag."""
    return BenchRoute(
        detector,
        source="station-onnx",
        model_id=model_id,
        clock=clock,
        usage=usage,
    )


def write_detections_jsonl(
    path: Path, observations: tuple[RouteObservation, ...] | list[RouteObservation]
) -> None:
    """Write one JSON object per frame. Polygons use the protocol's `mask_polygon`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(_observation_json(item)) for item in observations]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def read_detections_jsonl(path: Path) -> tuple[RouteObservation, ...]:
    """Read the JSONL written by `write_detections_jsonl`."""
    observations: list[RouteObservation] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise ValueError(f"detections line {line_no} must be an object")
        observations.append(_observation(raw, line_no))
    return tuple(observations)


def _observation_json(item: RouteObservation) -> dict[str, object]:
    masks: list[dict[str, object]] = []
    for index, detection in enumerate(item.detections):
        mask_id = item.mask_ids[index] if index < len(item.mask_ids) else f"{item.frame_id}-{index}"
        masks.append(
            {
                "encoding": "polygon",
                "mask_id": mask_id,
                "mask_polygon": [[point[0], point[1]] for point in detection.mask_polygon],
                "label": detection.label,
                "score": detection.score,
                "box_xyxy": list(detection.box_xyxy),
                "source": item.source,
                "model_id": item.model_id,
                "track_id": detection.track_id,
            }
        )
    return {
        "frame_id": item.frame_id,
        "t_ns": item.t_ns,
        "source": item.source,
        "model_id": item.model_id,
        "latency_s": item.latency_s,
        "input_tokens": item.input_tokens,
        "output_tokens": item.output_tokens,
        "gpu_seconds": item.gpu_seconds,
        "masks": masks,
    }


def _observation(raw: dict[object, object], line_no: int) -> RouteObservation:
    body = {str(key): value for key, value in raw.items()}
    where = f"detections line {line_no}"
    masks_raw = body.get("masks", [])
    if not isinstance(masks_raw, list):
        raise ValueError(f"{where} masks must be a list")
    detections: list[SamDetection] = []
    mask_ids: list[str] = []
    for index, item in enumerate(masks_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{where} mask {index} must be an object")
        mask = {str(key): value for key, value in item.items()}
        polygon = _polygon(mask.get("mask_polygon"), f"{where} mask {index}")
        box = _box(mask.get("box_xyxy"), f"{where} mask {index}")
        label = mask.get("label")
        score = mask.get("score")
        if not isinstance(label, str):
            raise ValueError(f"{where} mask {index} label must be text")
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise ValueError(f"{where} mask {index} score must be a number")
        track = mask.get("track_id")
        track_id = track if isinstance(track, int) and not isinstance(track, bool) else None
        detections.append(SamDetection(label, float(score), box, polygon, track_id))
        mask_id = mask.get("mask_id")
        mask_ids.append(
            mask_id if isinstance(mask_id, str) and mask_id else f"{body.get('frame_id')}-{index}"
        )
    return RouteObservation(
        frame_id=_int(body.get("frame_id"), f"{where} frame_id"),
        t_ns=_int(body.get("t_ns"), f"{where} t_ns"),
        source=_text(body.get("source"), f"{where} source"),
        model_id=_text(body.get("model_id"), f"{where} model_id"),
        latency_s=_float(body.get("latency_s", 0.0), f"{where} latency_s"),
        input_tokens=_int(body.get("input_tokens", 0), f"{where} input_tokens"),
        output_tokens=_int(body.get("output_tokens", 0), f"{where} output_tokens"),
        gpu_seconds=_float(body.get("gpu_seconds", 0.0), f"{where} gpu_seconds"),
        detections=tuple(detections),
        mask_ids=tuple(mask_ids),
    )


def _polygon(raw: object, where: str) -> tuple[tuple[float, float], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{where} mask_polygon must be a list")
    points: list[tuple[float, float]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{where} polygon point {index} must be [x, y]")
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in item):
            raise ValueError(f"{where} polygon point {index} must be numbers")
        points.append((float(item[0]), float(item[1])))
    return tuple(points)


def _box(raw: object, where: str) -> tuple[float, float, float, float]:
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError(f"{where} box_xyxy must be [x0, y0, x1, y1]")
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in raw):
        raise ValueError(f"{where} box_xyxy must be numbers")
    return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))


def _text(raw: object, where: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{where} must be text")
    return raw


def _int(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{where} must be an integer")
    return raw


def _float(raw: object, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ValueError(f"{where} must be a number")
    return float(raw)


@runtime_checkable
class _GpuTimed(Protocol):
    last_inference_seconds: float


def _gpu_seconds(detector: object) -> float:
    if not isinstance(detector, _GpuTimed):
        return 0.0
    return float(detector.last_inference_seconds)
