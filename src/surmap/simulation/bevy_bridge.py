"""The WebSocket bridge: Bevy wire messages in, RTAB-Map status out."""

from __future__ import annotations

import asyncio
import io
import threading
from collections import deque
from collections.abc import AsyncIterable, Awaitable, Callable
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
    is_pair_message,
)
from surmap.simulation.camera_profile import profile_sensor_yaml
from surmap.slam.stream_protocol import OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud
from surmap.types import StereoFramePair


class StreamingBackend(Protocol):
    @property
    def keyframe_count(self) -> int: ...

    @property
    def dropped_frames(self) -> int: ...

    @property
    def rectification(self) -> Rectification | None: ...

    def process_frame(self, frame: StereoFramePair) -> None: ...

    def poll_updates(self) -> list[OdomUpdate]: ...

    def map_cloud(self) -> MapCloud: ...

    def close(self) -> None: ...


class PairRecorder(Protocol):
    def record_pair(self, pair: BevyPair) -> None: ...

    def finish(self) -> None: ...


BackendFactory = Callable[..., StreamingBackend]


class BridgeSession(Protocol):
    """One page connection's state: a wire message in, its status reply out; closed when the
    page disconnects. `BevyStreamSession` (one drone) and
    `surmap.simulation.fleet.perception.FleetPerception` (one map per drone) are both one."""

    def handle(self, message: bytes) -> BridgeStatus: ...

    def close(self) -> None: ...


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
    session_factory: Callable[[], BridgeSession],
) -> websockets.asyncio.server.Server:
    """Serves the stereo bridge on `host:port`: one session per connection, each binary
    message answered with that session's status text, the session closed with the socket.

    A session's work (a map starting, PNG encodes, thread joins, `docker rm`) blocks, so it runs
    on a worker thread and the event loop, shared with the agent's own server, keeps serving.
    A connection's messages are still handled one at a time and in order, though a pair
    superseded while the session works is skipped (`serve_connection`), and `close` waits for
    a `handle` a cancelled handler left running."""

    async def handler(socket: websockets.asyncio.server.ServerConnection) -> None:
        session = session_factory()
        one_at_a_time = threading.Lock()

        def handle(message: bytes) -> BridgeStatus:
            with one_at_a_time:
                return session.handle(message)

        def close() -> None:
            with one_at_a_time:
                session.close()

        try:
            await serve_connection(socket, socket.send, handle)
        finally:
            await asyncio.to_thread(close)

    return await websockets.asyncio.server.serve(handler, host, port)


class BridgeMailbox:
    """A connection's messages on their way from its reader to its worker: every hello in
    arrival order, and of the pairs only the newest — a pair still waiting when a newer one
    arrives is skipped, so a slow session always goes on with the latest frame."""

    def __init__(self) -> None:
        self._waiting: deque[tuple[bool, bytes]] = deque()
        self._arrived = asyncio.Event()
        self._closed = False
        self.superseded = 0
        """Pairs skipped because a newer one arrived before the worker took them."""

    def put(self, message: bytes) -> None:
        pair = is_pair_message(message)
        if pair:
            older = next((entry for entry in self._waiting if entry[0]), None)
            if older is not None:
                self._waiting.remove(older)
                self.superseded += 1
        self._waiting.append((pair, message))
        self._arrived.set()

    def close(self) -> None:
        """No more messages; what is waiting is still taken."""
        self._closed = True
        self._arrived.set()

    async def take(self) -> bytes | None:
        """The next message, once one is waiting; `None` once closed and drained."""
        while not self._waiting:
            if self._closed:
                return None
            self._arrived.clear()
            await self._arrived.wait()
        return self._waiting.popleft()[1]


async def serve_connection(
    messages: AsyncIterable[str | bytes],
    send: Callable[[str], Awaitable[None]],
    handle: Callable[[bytes], BridgeStatus],
) -> None:
    """One connection: each binary message `handle`d on a worker thread, its status `send`.

    The reader never waits on `handle`: it keeps reading into a `BridgeMailbox`, so the page's
    socket never backs up behind a slow session and the session works on the newest pair. The
    connection ends once the reader has ended and what was waiting is handled; a `handle` that
    fails ends it at once."""
    mailbox = BridgeMailbox()

    async def read() -> None:
        try:
            async for message in messages:
                if isinstance(message, bytes):
                    mailbox.put(message)
        finally:
            mailbox.close()

    reader = asyncio.create_task(read())
    try:
        while (message := await mailbox.take()) is not None:
            status = await asyncio.to_thread(handle, message)
            await send(encode_status(status))
        await reader
    finally:
        reader.cancel()
