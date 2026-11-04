"""Builders, drivers and matchers for the SurMap tool tests.

`a_tool_rig` is a `DemoWorkspace` over a real, non-serving demo run host on a temp scene cache
and a temp history DB (never `~/.cache/surmap`): the tiny two-frame EuRoC fixture from
`tests/test_demo.py`, no RTAB-Map, and the fake centred-box SAM both in the host's runs and in
the workspace's own `detect`. Runs are recorded through the host itself, and objects are seeded
into the history as surfaces of known shape, so each tool test only exercises its own tool.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from surmap.agent.proto import survey_tools_pb2 as pb
from surmap.agent.tools.onboard import OnboardModels
from surmap.agent.tools.workspace import DemoWorkspace, GeometryStore
from surmap.demo.datasets import DISPLAY_HEIGHT, DISPLAY_WIDTH, PreparedDataset
from surmap.demo.history import RunHistoryStore
from surmap.demo.runs import DemoRunHost
from surmap.demo.server import make_demo_server
from surmap.survey.sam import CentredBoxVideoSamDetector
from tests.object_fakes import Vec3Tuple, a_box
from tests.test_demo import _prepared_tiny

T = TypeVar("T")

TINY_SCENE = "tiny-test"
"""The fixture scene: two 752 x 480 stereo pairs at t_ns 100 and 200, frame ids 1 and 2."""
TINY_FULL_SIZE = (752, 480)
TINY_DISPLAY_SIZE = (DISPLAY_WIDTH, DISPLAY_HEIGHT)
RETIRED_SCENE = "retired-scene"
"""A scene the history has runs of but the station no longer offers or caches."""

# The fake SAM outlines the middle 30 % of every frame.
_CENTRED_FRACTION = 0.3


@dataclass(frozen=True)
class ToolRig:
    """A workspace, the run host under it and the scene it plays."""

    workspace: DemoWorkspace
    host: DemoRunHost
    prepared: PreparedDataset

    @property
    def history(self) -> RunHistoryStore:
        return self.host.history_store

    def history_status(self, run_id: str) -> str:
        run = self.history.get_run(run_id)
        assert run is not None, f"the history has no run {run_id}"
        return str(run["status"])


@contextmanager
def a_tool_rig(tmp_path: Path, *, onboard: OnboardModels | None = None) -> Iterator[ToolRig]:
    """A `DemoWorkspace` over the tiny scene, built but not serving; closed on exit.

    `onboard` is the station's on-board detector catalogue; none, so no on-board model, when absent.
    """
    prepared = _prepared_tiny(tmp_path)
    server = make_demo_server(
        prepared,
        cache_dir=tmp_path / "cache",
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_fake=True,
        history_store=RunHistoryStore(tmp_path / "history.db"),
    )
    assert isinstance(server, DemoRunHost)
    workspace = DemoWorkspace(
        server,
        detector=CentredBoxVideoSamDetector(),
        geometry=GeometryStore(tmp_path / "geometry"),
        onboard=onboard,
    )
    try:
        yield ToolRig(workspace=workspace, host=server, prepared=prepared)
    finally:
        server.server_close()


def a_recorded_run(rig: ToolRig, prompt: str = "box") -> str:
    """The tiny scene played to its end through the host, with the fake SAM; its run id."""
    engine = rig.host.start_run(rig.prepared, rig.host.sam_prompt(TINY_SCENE, prompt))
    assert engine is not None, "the host refused to start a run"
    assert engine.done.wait(timeout=30), "the recorded run never ended"
    return engine.run_id


def a_display_jpeg(size: tuple[int, int] = TINY_DISPLAY_SIZE) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


def a_run_of_a_retired_scene(rig: ToolRig, frames: int = 20) -> str:
    """A finished run of a scene no longer cached: only its display JPEGs remain.

    Frame ids run 1..`frames`, timestamps 1000 ns apart.
    """
    run_id = rig.history.create_run(RETIRED_SCENE, "Retired scene")
    jpeg = a_display_jpeg()
    for index in range(frames):
        rig.history.record_frame(
            run_id,
            index=index,
            frame_id=index + 1,
            t_ns=(index + 1) * 1000,
            jpeg=jpeg,
            overlay=[],
            camera=None,
        )
    rig.history.finish_run(run_id)
    return run_id


def with_an_object(
    rig: ToolRig,
    run_id: str,
    surface_id: int,
    points: NDArray[np.float32],
    *,
    label: str = "box",
    track_id: int = 1,
    moving: bool = False,
    frame_id: int = 1,
) -> str:
    """Seed one surface of known shape into the run's history; its object id."""
    rig.history.record_surface(
        run_id,
        frame_id=frame_id,
        surface_id=surface_id,
        label=label,
        track_id=track_id,
        points=points.tolist(),
        moving=moving,
    )
    return f"obj_{surface_id}"


def a_cube(centre: Vec3Tuple, half: float) -> NDArray[np.float32]:
    """A solid 10 cm lattice cube of half-side `half` metres."""
    return a_box(centre=centre, half=(half, half, half))


def centred_box(size: tuple[int, int]) -> tuple[float, float, float, float]:
    """The box the fake SAM outlines on a `size` frame."""
    width, height = size
    half_w, half_h = width * _CENTRED_FRACTION / 2, height * _CENTRED_FRACTION / 2
    return (width / 2 - half_w, height / 2 - half_h, width / 2 + half_w, height / 2 + half_h)


def image_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def image_format(data: bytes) -> str | None:
    with Image.open(io.BytesIO(data)) as image:
        return image.format


async def eventually(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition never held")


async def the_run_started_by(rig: ToolRig, call: asyncio.Task[T]) -> str:
    """The run id of the host's current run once `call` has started one.

    Re-raises the call's own error when it ends before any run starts.
    """
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if call.done():
            call.result()
            raise AssertionError("the call ended without starting a run")
        engine = rig.host.run_engine
        if engine is not None and engine.run_id:
            return engine.run_id
        await asyncio.sleep(0.02)
    raise AssertionError("no run started")


async def settled(call: Awaitable[T]) -> None:
    """Wait for a cancelled call to finish unwinding."""
    with contextlib.suppress(asyncio.CancelledError):
        await call


def xyz(vector: pb.Vec3) -> tuple[float, float, float]:
    """A proto vector as an `(x, y, z)` tuple."""
    return (vector.x, vector.y, vector.z)


async def the_run_started_by_the_host(rig: ToolRig) -> str:
    """The run id of the host's most recent run, once it has one."""
    await eventually(lambda: rig.host.run_engine is not None and bool(rig.host.run_engine.run_id))
    engine = rig.host.run_engine
    assert engine is not None
    return engine.run_id
