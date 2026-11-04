"""The WebSocket bridge session: wire messages in, RTAB-Map status out."""

import asyncio
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import websockets
from PIL import Image

from surmap.simulation.bevy_bridge import BevyStreamSession, serve_bevy_bridge
from surmap.simulation.bevy_wire import (
    BevyHello,
    BevyPair,
    BevyWireError,
    BridgeStatus,
    decode_bevy_message,
)
from surmap.simulation.camera_profile import profile_sensor_yaml
from surmap.slam.stream_protocol import OdomUpdate, Rectification
from surmap.slam.streaming import MapCloud
from surmap.types import Pose, StereoFramePair, Vec3

GOLDENS = Path(__file__).parent / "fixtures" / "bevy_sim_wire"
HELLO = (GOLDENS / "hello.bin").read_bytes()
PAIR = (GOLDENS / "pair.bin").read_bytes()


class FakeBackend:
    """The streaming backend seam: records frames, replays scripted odometry, maps nothing."""

    def __init__(self) -> None:
        self.frames: list[StereoFramePair] = []
        self.updates: list[OdomUpdate] = []
        self.keyframe_count = 3
        self.dropped_frames = 1
        self.rectification: Rectification | None = None
        self.closed = False

    def process_frame(self, frame: StereoFramePair) -> None:
        self.frames.append(frame)

    def poll_updates(self) -> list[OdomUpdate]:
        updates, self.updates = self.updates, []
        return updates

    def map_cloud(self) -> MapCloud:
        return MapCloud(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8))

    def close(self) -> None:
        self.closed = True


class FakeRecorder:
    """The capture recorder seam: records pairs until it is finished."""

    def __init__(self) -> None:
        self.pairs: list[BevyPair] = []
        self.finished = False

    def record_pair(self, pair: BevyPair) -> None:
        self.pairs.append(pair)

    def finish(self) -> None:
        self.finished = True


class FakeFactory:
    """A backend factory that remembers the calibration it was built with."""

    def __init__(self, backend: FakeBackend) -> None:
        self.backend = backend
        self.cam0_yaml = ""
        self.cam1_yaml = ""
        self.width = 0
        self.height = 0

    def __call__(self, *, cam0_yaml: str, cam1_yaml: str, width: int, height: int) -> FakeBackend:
        self.cam0_yaml, self.cam1_yaml = cam0_yaml, cam1_yaml
        self.width, self.height = width, height
        return self.backend


def a_session() -> tuple[BevyStreamSession, FakeFactory, FakeBackend, FakeRecorder]:
    backend = FakeBackend()
    factory = FakeFactory(backend)
    recorder = FakeRecorder()
    return BevyStreamSession(factory, recorder=recorder), factory, backend, recorder


def test_the_hello_builds_the_backend_from_the_hello_calibration() -> None:
    # Given a bridge session that has seen no message yet
    session, factory, _, _ = a_session()

    # When the browser's hello arrives
    status = session.handle(HELLO)

    # Then the backend is built from both rendered sensor yamls at full size
    assert factory.width == 640
    assert factory.height == 480
    assert "intrinsics: [381.36, 381.36, 320.0, 240.0]" in factory.cam0_yaml
    assert factory.cam0_yaml != factory.cam1_yaml
    assert status == BridgeStatus(frames=0, posed=0, lost=False, keyframes=0, dropped=0)


def test_the_hello_sensor_yamls_come_from_its_camera_profile() -> None:
    # Given a bridge session and the camera profile the hello golden carries
    session, factory, _, _ = a_session()
    session.handle(HELLO)

    # When the yamls the factory received are compared with the renderer
    hello = decode_bevy_message(HELLO)
    assert isinstance(hello, BevyHello)

    # Then cam0 and cam1 are exactly the rendered EuRoC yamls
    assert factory.cam0_yaml == profile_sensor_yaml(hello.camera, 0)
    assert factory.cam1_yaml == profile_sensor_yaml(hello.camera, 1)


def test_a_pair_before_any_hello_is_refused() -> None:
    # Given a bridge session that has seen no hello
    session, _, _, _ = a_session()

    # When a pair arrives first, Then the wire error is raised
    with pytest.raises(BevyWireError):
        session.handle(PAIR)


def test_a_pair_becomes_a_stereo_frame_with_png_payloads() -> None:
    # Given a session opened by the hello
    session, _, backend, recorder = a_session()
    session.handle(HELLO)

    # When the pair golden arrives
    session.handle(PAIR)

    # Then one stereo frame reaches the backend and the recorder, as 4x2 PNGs
    assert len(backend.frames) == 1
    frame = backend.frames[0]
    assert (frame.frame_id, frame.t_ns) == (7, 700_000_000)
    assert frame.calibration_id == "elp-stereo-pinhole-v1"
    with Image.open(io.BytesIO(frame.left_data)) as left_image:
        assert left_image.size == (4, 2)
        assert list(left_image.getdata()) == list(range(8))
    with Image.open(io.BytesIO(frame.right_data)) as right_image:
        assert right_image.size == (4, 2)
    assert len(recorder.pairs) == 1


def test_the_status_counts_frames_posed_keyframes_and_dropped() -> None:
    # Given a session whose backend tracked the pair and holds keyframes
    session, _, backend, _ = a_session()
    session.handle(HELLO)
    backend.updates = [
        OdomUpdate(
            frame_id=7,
            t_ns=700_000_000,
            pose=Pose(Vec3(1.0, 3.0, 2.0), (0.0, 0.0, 0.0, 1.0)),
            lost=False,
            ms=1.0,
        )
    ]

    # When the pair arrives
    status = session.handle(PAIR)

    # Then the status counts the frame, its pose, the keyframes and the drops
    assert status == BridgeStatus(frames=1, posed=1, lost=False, keyframes=3, dropped=1)


def test_closing_the_session_closes_the_backend_and_finishes_the_recorder() -> None:
    # Given a session that streamed one pair
    session, _, backend, recorder = a_session()
    session.handle(HELLO)
    session.handle(PAIR)

    # When the session is closed
    session.close()

    # Then the backend is closed and the recording is finished
    assert backend.closed
    assert recorder.finished


async def exchange_over_loopback() -> dict[str, object]:
    """Send hello and pair to a real bridge server; return the pair's status."""
    backend = FakeBackend()
    factory = FakeFactory(backend)
    session_factory: Callable[[], BevyStreamSession] = lambda: BevyStreamSession(factory)  # noqa: E731
    server = await serve_bevy_bridge("127.0.0.1", 0, session_factory)
    bound_socket = next(iter(server.sockets or ()))
    port = int(cast("tuple[str, int]", bound_socket.getsockname())[1])
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as socket:
            await socket.send(HELLO)
            await socket.recv()
            await socket.send(PAIR)
            reply = await socket.recv()
    finally:
        server.close()
        await server.wait_closed()
    decoded: dict[str, object] = json.loads(reply)
    return decoded


def test_a_real_websocket_client_gets_a_status_for_its_pair() -> None:
    # Given a bridge served on an ephemeral port with the fake backend behind it
    # When a real client sends the hello and the pair goldens
    status = asyncio.run(exchange_over_loopback())

    # Then the reply is the status text for one streamed frame
    assert status == {
        "type": "status",
        "frames": 1,
        "posed": 0,
        "lost": False,
        "keyframes": 3,
        "dropped": 1,
    }
