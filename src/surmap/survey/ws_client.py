"""The survey client: one asyncio WebSocket to a CM5 or station server, every call over it.

Both survey servers serve Connect over one WebSocket at `/connect` (`surmap.rpc.socket_rpc`).
`SurveyConnection.open` dials it once, sending the bearer token on the upgrade; its calls are
multiplexed over that one socket, so a region query reaches the server holding the frames its
survey stream sent, and a stream can last a whole survey behind a proxy that caps HTTP requests.

    async with SurveyConnection.open("wss://<host>/connect", token=token) as connection:
        async for response in connection.stream_survey(requests):
            ...
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, TypeVar
from urllib.parse import urlsplit, urlunsplit

import websockets
from connectrpc.method import IdempotencyLevel, MethodInfo
from google.protobuf.message import Message

from surmap.rpc.socket_rpc import PeerRole, SocketRpcPeer, WebSocketFrames
from surmap.survey.endpoint import CONNECT_PATH
from surmap.survey.v1 import survey_pb2

__all__ = ["SurveyConnection", "SurveyService", "connect_url", "health_url"]

SurveyService = Literal["Cm5SurveyService", "StationSamService"]

REQ = TypeVar("REQ", bound=Message)
RES = TypeVar("RES", bound=Message)

# Larger than one socket-RPC chunk (256 KiB) with room to spare; under Modal's 2 MiB cap.
_MAX_MESSAGE_BYTES = 1024 * 1024


def connect_url(address: str) -> str:
    """The `ws(s)://…/connect` URL for `address`: `host:port`, an `http(s)://` or `ws(s)://` URL,
    with or without the path."""
    if "://" not in address:
        address = f"ws://{address}"
    parts = urlsplit(address)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    if scheme not in {"ws", "wss"}:
        raise ValueError(f"not a survey server address: {address!r}")
    path = parts.path.rstrip("/") or CONNECT_PATH
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def health_url(address: str) -> str:
    """The server's `GET /health/is_alive` URL, over HTTP(S) to the same host as `connect_url`."""
    parts = urlsplit(connect_url(address))
    scheme = "https" if parts.scheme == "wss" else "http"
    return urlunsplit((scheme, parts.netloc, "/health/is_alive", "", ""))


def _method(
    service: SurveyService, name: str, request: type[REQ], response: type[RES]
) -> MethodInfo[REQ, RES]:
    return MethodInfo(
        name=name,
        service_name=f"surmap.survey.v1.{service}",
        input=request,
        output=response,
        idempotency_level=IdempotencyLevel.UNKNOWN,
    )


_STREAM_SURVEY = _method(
    "Cm5SurveyService", "StreamSurvey", survey_pb2.Cm5Request, survey_pb2.Cm5Response
)
_STREAM_DETECTIONS = _method(
    "Cm5SurveyService", "StreamDetections", survey_pb2.Cm5Request, survey_pb2.DetectionResponse
)
_STREAM_REGION_POINTS = _method(
    "Cm5SurveyService", "StreamRegionPoints", survey_pb2.RegionQuery, survey_pb2.RegionPoints
)
_STREAM_ANALYSIS = _method(
    "StationSamService", "StreamAnalysis", survey_pb2.StationRequest, survey_pb2.StationResponse
)


class SurveyConnection:
    """Survey calls over one dialed socket; built by `open`."""

    def __init__(self, peer: SocketRpcPeer) -> None:
        self._peer = peer

    @classmethod
    @asynccontextmanager
    async def open(
        cls, address: str, *, token: str | None = None, open_timeout_s: float = 10.0
    ) -> AsyncIterator[SurveyConnection]:
        """Dial `address` (see `connect_url`); `PermissionError` when the server refuses the
        token, `OSError` when nothing answers."""
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            socket = await websockets.connect(
                connect_url(address),
                additional_headers=headers,
                open_timeout=open_timeout_s,
                max_size=_MAX_MESSAGE_BYTES,
            )
        except websockets.InvalidStatus as refused:
            status = refused.response.status_code
            if status in {401, 403}:
                raise PermissionError(
                    f"{address} refused the survey token (HTTP {status})"
                ) from None
            raise OSError(f"{address} answered HTTP {status}, not a WebSocket") from None
        except (TimeoutError, websockets.InvalidHandshake) as failed:
            raise OSError(f"{address} did not open a WebSocket: {failed}") from None
        peer = SocketRpcPeer(WebSocketFrames(socket), role=PeerRole.DIALER)
        serving = asyncio.create_task(peer.serve())
        try:
            yield cls(peer)
        finally:
            await peer.close()
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)

    async def capabilities(self, service: SurveyService) -> survey_pb2.Capabilities:
        """What the server's `service` was built with."""
        method = _method(
            service, "GetCapabilities", survey_pb2.CapabilitiesRequest, survey_pb2.Capabilities
        )
        return await self._peer.call_unary(method, survey_pb2.CapabilitiesRequest())

    def stream_survey(
        self, requests: AsyncIterable[survey_pb2.Cm5Request]
    ) -> AsyncIterator[survey_pb2.Cm5Response]:
        """`Cm5SurveyService.StreamSurvey`: config, then frames and GPS fixes."""
        return self._peer.call_bidi_stream(_STREAM_SURVEY, requests)

    def stream_detections(
        self, requests: AsyncIterable[survey_pb2.Cm5Request]
    ) -> AsyncIterator[survey_pb2.DetectionResponse]:
        """`Cm5SurveyService.StreamDetections`: config, then frames."""
        return self._peer.call_bidi_stream(_STREAM_DETECTIONS, requests)

    def stream_region_points(
        self, queries: AsyncIterable[survey_pb2.RegionQuery]
    ) -> AsyncIterator[survey_pb2.RegionPoints]:
        """`Cm5SurveyService.StreamRegionPoints`: polygons on frames this server holds."""
        return self._peer.call_bidi_stream(_STREAM_REGION_POINTS, queries)

    def stream_analysis(
        self, requests: AsyncIterable[survey_pb2.StationRequest]
    ) -> AsyncIterator[survey_pb2.StationResponse]:
        """`StationSamService.StreamAnalysis`: config, then frames."""
        return self._peer.call_bidi_stream(_STREAM_ANALYSIS, requests)
