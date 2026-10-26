from types import ModuleType

import pytest

from surmap.slam import InMemorySlamBackend, RtabmapBackend, RtabmapUnavailable, SlamBackend
from surmap.types import StereoFramePair


def _frame(frame_id: int = 1) -> StereoFramePair:
    return StereoFramePair(frame_id, 1_000_000, "left.png", "right.png", "cal-1")


def test_fake_backend_satisfies_protocol_and_records_trajectory() -> None:
    backend = InMemorySlamBackend()
    assert isinstance(backend, SlamBackend)
    result = backend.process_frame(_frame())
    assert result.pose is not None
    assert result.static_points == ()
    assert backend.trajectory() == [result.pose]
    backend.close()
    assert backend.closed


def test_rtabmap_unavailable_without_binding() -> None:
    with pytest.raises(RtabmapUnavailable, match="not on PyPI"):
        RtabmapBackend(module_name="definitely_missing_rtabmap_binding_xyz")


def test_rtabmap_adapter_with_stub_binding() -> None:
    module = ModuleType("stub_rtabmap")

    class StubSession:
        def __init__(self, database_path: str) -> None:
            self.database_path = database_path
            self.closed = False

        def process(
            self, left_ref: str, right_ref: str, t_ns: int
        ) -> tuple[tuple[float, ...], list[tuple[float, float, float]]]:
            assert (left_ref, right_ref, t_ns) == ("left.png", "right.png", 1_000_000)
            return (1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0), [(4.0, 5.0, 6.0)]

        def close(self) -> None:
            self.closed = True

    module.RTABMap = StubSession  # type: ignore[attr-defined]
    backend = RtabmapBackend("test.db", module=module)
    result = backend.process_frame(_frame())
    assert result.pose is not None
    assert (result.pose.position.x, result.pose.position.y) == (1.0, 2.0)
    assert len(result.static_points) == 1
    assert backend.trajectory() == [result.pose]
    backend.close()


def test_rtabmap_binding_without_factory_is_rejected() -> None:
    with pytest.raises(RtabmapUnavailable, match="RTABMap"):
        RtabmapBackend(module=ModuleType("empty_binding"))
