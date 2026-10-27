"""Station ConnectRPC server: `StationSamService.StreamAnalysis` (BIDI).

The same raw-frame input as the CM5, SAM detections out — each response
repeats the `frame_id` the requester assigned, so dropped frames (the
requester's `BEST_EFFORT_DROP` choice, enforced by the n3 gate) are
reconcilable by their absence. The station issues no commands to the
drone (docs/architecture.md section 2.2).
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from surmap.rpc.description import ServiceModule
from surmap.survey.sam import SamDetector
from surmap.survey.v1 import survey_pb2


async def stream_analysis(
    requests: AsyncIterable[survey_pb2.StationRequest],
    detector: SamDetector,
) -> AsyncIterator[survey_pb2.StationResponse]:
    """Serve one station analysis stream: config first, then frames."""
    raise NotImplementedError("TODO(pr-5): implement stream_analysis")
    yield survey_pb2.StationResponse()  # unreachable; keeps the generator shape typed


def station_service_module() -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `StationSamService`."""
    raise NotImplementedError("TODO(pr-5): implement station_service_module")
