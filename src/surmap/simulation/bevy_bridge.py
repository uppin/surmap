"""The WebSocket bridge: Bevy wire messages in, RTAB-Map status out."""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Protocol

import websockets.asyncio.server
from PIL import Image

from surmap.simulation.bevy_wire import (
    BevyHello,
    BevyPair,
    BevyWireError,
    BridgeStatus,
    decode_bevy_message,
    encode_status,
)
from surmap.simulation.camera_profile import profile_sensor_yaml
from surmap.slam.stream_protocol import OdomUpdate
from surmap.types import StereoFramePair


class StreamingBackend(Protocol):
    @property
    def keyframe_count(self) -> int: ...

    @property
    def dropped_frames(self) -> int: ...

    def process_frame(self, frame: StereoFramePair) -> None: ...

    def poll_updates(self) -> list[OdomUpdate]: ...

    def close(self) -> None: ...


class PairRecorder(Protocol):
    def record_pair(self, pair: BevyPair) -> None: ...

    def finish(self) -> None: ...


BackendFactory = Callable[..., StreamingBackend]


def _png(gray: bytes, width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.frombytes("L", (width, height), gray).save(buffer, format="PNG")
    return buffer.getvalue()


class BevyStreamSession:
    def __init__(
        self,
        backend_factory: BackendFactory,
        recorder: PairRecorder | None = None,
    ) -> None:
        self._backend_factory = backend_factory
        self._recorder = recorder
        self._backend: StreamingBackend | None = None
        self._hello: BevyHello | None = None
        self._frames = 0
        self._posed = 0
        self._lost = False

    def handle(self, message: bytes) -> BridgeStatus:
        decoded = decode_bevy_message(message)
        if isinstance(decoded, BevyHello):
            self._hello = decoded
            camera = decoded.camera
            self._backend = self._backend_factory(
                cam0_yaml=profile_sensor_yaml(camera, 0),
                cam1_yaml=profile_sensor_yaml(camera, 1),
                width=camera.width,
                height=camera.height,
            )
            return BridgeStatus(frames=0, posed=0, lost=False, keyframes=0, dropped=0)
        if self._backend is None or self._hello is None:
            raise BevyWireError("pair received before any hello")
        pair = decoded
        if self._recorder is not None:
            self._recorder.record_pair(pair)
        self._backend.process_frame(
            StereoFramePair(
                frame_id=pair.frame_id,
                t_ns=pair.t_ns,
                left_ref="",
                right_ref="",
                calibration_id=self._hello.camera.id,
                left_data=_png(pair.left_data, pair.width, pair.height),
                right_data=_png(pair.right_data, pair.width, pair.height),
            )
        )
        self._frames += 1
        for update in self._backend.poll_updates():
            if update.pose is not None:
                self._posed += 1
            self._lost = update.lost
        return self._status()

    def _status(self) -> BridgeStatus:
        backend = self._backend
        return BridgeStatus(
            frames=self._frames,
            posed=self._posed,
            lost=self._lost,
            keyframes=backend.keyframe_count if backend is not None else 0,
            dropped=backend.dropped_frames if backend is not None else 0,
        )

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None
        if self._recorder is not None:
            self._recorder.finish()


async def serve_bevy_bridge(
    host: str,
    port: int,
    session_factory: Callable[[], BevyStreamSession],
) -> websockets.asyncio.server.Server:
    async def handler(socket: websockets.asyncio.server.ServerConnection) -> None:
        session = session_factory()
        try:
            async for message in socket:
                if isinstance(message, bytes):
                    await socket.send(encode_status(session.handle(message)))
        finally:
            session.close()

    return await websockets.asyncio.server.serve(handler, host, port)
