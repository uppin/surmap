"""RTAB-Map backend adapter.

RTAB-Map has no official package on PyPI: its Python access comes from
a system build of RTAB-Map (or the ROS 2 ``rtabmap`` packages), which
provides an importable binding module. This adapter therefore loads
that module lazily and fails with install guidance when it is absent,
instead of adding a fictitious pip dependency.

Expected binding surface (the subset SurMap needs): the binding module
exposes ``RTABMap(database_path)`` with
``process(left_ref, right_ref, t_ns) -> (pose, points)`` where ``pose``
is ``(x, y, z, qx, qy, qz, qw)`` or ``None`` and ``points`` is an
iterable of ``(x, y, z)`` map-frame static-scene points, plus ``close()``.
A module with a different surface is adapted at this boundary, not
throughout the codebase.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import Protocol, cast

from surmap.slam.base import FrameResult
from surmap.types import Pose, StereoFramePair, Vec3

PoseTuple = tuple[float, float, float, float, float, float, float]
PointTuple = tuple[float, float, float]


class NativeRtabmapSession(Protocol):
    """The subset of a native RTAB-Map binding session SurMap uses."""

    def process(
        self, left_ref: str, right_ref: str, t_ns: int
    ) -> tuple[PoseTuple | None, Iterable[PointTuple]]: ...

    def close(self) -> None: ...


DEFAULT_BINDING_MODULE = "pyrtabmap"

_INSTALL_HINT = (
    "RTAB-Map Python bindings are not importable. RTAB-Map is not on "
    "PyPI: install a system build of RTAB-Map with its Python bindings "
    "(or the ROS 2 rtabmap packages) so the binding module is on "
    "PYTHONPATH, or pass a compatible module to RtabmapBackend."
)


class RtabmapUnavailable(RuntimeError):
    """Raised when no usable RTAB-Map binding module can be loaded."""


def _load_binding(module: ModuleType | None, module_name: str) -> ModuleType:
    if module is not None:
        return module
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise RtabmapUnavailable(f"{_INSTALL_HINT} (tried {module_name!r})") from exc


class RtabmapBackend:
    """SlamBackend backed by a native RTAB-Map binding module."""

    def __init__(
        self,
        database_path: str = "",
        *,
        module: ModuleType | None = None,
        module_name: str = DEFAULT_BINDING_MODULE,
    ) -> None:
        binding = _load_binding(module, module_name)
        factory = getattr(binding, "RTABMap", None)
        if not callable(factory):
            raise RtabmapUnavailable(
                f"RTAB-Map binding module {binding.__name__!r} does not "
                "expose a callable RTABMap; cannot adapt it."
            )
        create = cast(Callable[[str], NativeRtabmapSession], factory)
        self._session: NativeRtabmapSession = create(database_path)
        self._trajectory: list[Pose] = []

    def process_frame(self, frame: StereoFramePair) -> FrameResult:
        pose_raw, points_raw = self._session.process(frame.left_ref, frame.right_ref, frame.t_ns)
        pose = None
        if pose_raw is not None:
            x, y, z, qx, qy, qz, qw = pose_raw
            pose = Pose(Vec3(x, y, z), (qx, qy, qz, qw))
            self._trajectory.append(pose)
        points = tuple(Vec3(px, py, pz) for px, py, pz in points_raw)
        return FrameResult(frame.frame_id, frame.t_ns, pose, points)

    def trajectory(self) -> list[Pose]:
        return list(self._trajectory)

    def close(self) -> None:
        self._session.close()
