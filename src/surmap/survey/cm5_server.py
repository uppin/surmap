"""CM5 ConnectRPC server: `Cm5SurveyService.StreamSurvey` (BIDI).

Frames and calibration in; incremental designated points and requested
video channels out. Points are streamed as they are spawned through the
`IncrementalPointEmitter` (n2) — a point still at a sent position is
never resent. RTAB-Map output is registration data only, never a control
signal (docs/architecture.md section 1).
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from surmap.rpc.description import ServiceModule
from surmap.slam.base import SlamBackend
from surmap.survey.object_points import ObjectPointSource
from surmap.survey.points import IncrementalPointEmitter
from surmap.survey.v1 import survey_pb2


async def stream_survey(
    requests: AsyncIterable[survey_pb2.Cm5Request],
    slam: SlamBackend,
    objects: ObjectPointSource,
    emitter: IncrementalPointEmitter | None = None,
) -> AsyncIterator[survey_pb2.Cm5Response]:
    """Serve one CM5 survey stream: config first, then per-channel frames."""
    raise NotImplementedError("TODO(pr-4): implement stream_survey")
    yield survey_pb2.Cm5Response()  # unreachable; keeps the generator shape typed


def cm5_service_module() -> ServiceModule[Any]:
    """The `surmap.rpc` service module mounting `Cm5SurveyService`."""
    raise NotImplementedError("TODO(pr-4): implement cm5_service_module")
