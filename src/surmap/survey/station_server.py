"""Station ConnectRPC server: `StationSamService.StreamAnalysis` (BIDI).

The same raw-frame input as the CM5, SAM detections out — each response
repeats the `frame_id` the requester assigned, so dropped frames (the
requester's `BEST_EFFORT_DROP` choice, enforced by the n3 gate) are
reconcilable by their absence. The station issues no commands to the
drone (docs/architecture.md section 2.2).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from surmap.rpc.compose import Brick
from surmap.rpc.description import ServiceModule
from surmap.survey.sam import (
    AnalysisGate,
    AnalysisMode,
    InMemorySamDetector,
    RawFrame,
    SamDetection,
    SamDetector,
)
from surmap.survey.v1 import survey_pb2


def _map_mode(mode: int) -> AnalysisMode:
    if mode == survey_pb2.ANALYSIS_MODE_BEST_EFFORT_DROP:
        return AnalysisMode.BEST_EFFORT_DROP
    # ANALYSIS_MODE_EVERY_FRAME and ANALYSIS_MODE_UNSPECIFIED both mean
    # every frame: UNSPECIFIED is treated as EVERY_FRAME.
    return AnalysisMode.EVERY_FRAME


def _encoding_name(encoding: int) -> str:
    if encoding == survey_pb2.FRAME_ENCODING_MJPEG:
        return "mjpeg"
    if encoding == survey_pb2.FRAME_ENCODING_RAW_RGB:
        return "raw_rgb"
    return "unspecified"


def _to_raw_frame(frame: survey_pb2.RawVideoFrame) -> RawFrame:
    return RawFrame(
        frame_id=frame.frame_id,
        t_ns=frame.t_ns,
        channel=frame.channel,
        width=frame.width,
        height=frame.height,
        encoding=_encoding_name(frame.encoding),
        data=frame.data,
    )


def _to_proto_detection(detection: SamDetection) -> survey_pb2.SamDetection:
    x_min, y_min, x_max, y_max = detection.box_xyxy
    proto = survey_pb2.SamDetection(
        label=detection.label,
        score=detection.score,
        box=survey_pb2.Box(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max),
        mask_polygon=[survey_pb2.Point2(x=x, y=y) for x, y in detection.mask_polygon],
    )
    if detection.track_id is not None:
        proto.track_id = detection.track_id
    return proto


def _execution(detector: SamDetector) -> tuple[str, str]:
    """The (provider, device) a detector reports for its execution.

    Real adapters name their provider (`CUDAExecutionProvider`,
    `SAM 3.1 (PyTorch)`) and device (`cuda:<index>` / `cpu`); a
    detector that says neither is named by type and counted as CPU.
    """
    provider = str(getattr(detector, "provider", "") or type(detector).__name__)
    device = str(getattr(detector, "device", "") or "cpu")
    return provider, device


async def _analyze(
    frame: survey_pb2.RawVideoFrame,
    gate: AnalysisGate,
    detector: SamDetector,
) -> survey_pb2.StationResponse | None:
    async with gate.slot() as admitted:
        if not admitted:
            return None
        detections = await detector.detect(_to_raw_frame(frame))
        provider, device = _execution(detector)
        return survey_pb2.StationResponse(
            detections=survey_pb2.SamFrameDetections(
                frame_id=frame.frame_id,
                detections=[_to_proto_detection(d) for d in detections],
                provider=provider,
                device=device,
            )
        )


async def stream_analysis(
    requests: AsyncIterable[survey_pb2.StationRequest],
    detector: SamDetector,
) -> AsyncIterator[survey_pb2.StationResponse]:
    """Serve one station analysis stream: config first, then frames."""
    gate: AnalysisGate | None = None
    tasks: list[asyncio.Task[survey_pb2.StationResponse | None]] = []
    async for request in requests:
        if gate is None:
            if request.WhichOneof("kind") != "config":
                raise ValueError("first request must be config")
            gate = AnalysisGate(_map_mode(request.config.analysis_mode))
            # The stream's concept leads: a detector that can be
            # re-prompted (SAM 3.1) is reset to it, so the page's
            # prompt — not the server's build-time default — is what
            # gets segmented for.
            prompts = request.config.concept_prompts
            set_prompt = getattr(detector, "set_prompt", None)
            if prompts and callable(set_prompt):
                set_prompt(prompts[0])
            continue
        if request.WhichOneof("kind") != "frame":
            continue
        tasks.append(asyncio.ensure_future(_analyze(request.frame, gate, detector)))
    if gate is None:
        raise ValueError("first request must be config")
    for task in tasks:
        response = await task
        if response is not None:
            yield response


def station_service_module(
    detector: SamDetector | None = None,
) -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `StationSamService`."""
    default_detector: SamDetector = detector if detector is not None else InMemorySamDetector()

    async def handler(
        requests: AsyncIterable[survey_pb2.StationRequest], _ctx: Any
    ) -> AsyncIterator[survey_pb2.StationResponse]:
        async for response in stream_analysis(requests, default_detector):
            yield response

    async def capabilities_handler(
        _request: survey_pb2.CapabilitiesRequest, _ctx: Any
    ) -> survey_pb2.Capabilities:
        provider, device = _execution(default_detector)
        return survey_pb2.Capabilities(
            service="station",
            sam_analysis=not isinstance(default_detector, InMemorySamDetector),
            provider=provider,
            device=device,
        )

    return ServiceModule(
        descriptor=survey_pb2.DESCRIPTOR.services_by_name["StationSamService"],
        bricks=lambda ctx: (
            Brick(methods={"GetCapabilities": capabilities_handler, "StreamAnalysis": handler}),
        ),
    )
