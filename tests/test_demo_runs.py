"""The demo's run host: takeover, a run's end, and scene preparation, with no viewer attached.

Characterisation tests (V1) for the run lifecycle paths the rest of the demo suite does not
reach, recorded before `_RunEngine` and the run host move into `surmap.demo.runs`.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from surmap.demo.datasets import DatasetSpec, PreparedDataset
from surmap.demo.history import RunHistoryStore
from surmap.demo.server import (
    TAKEOVER_TIMEOUT_S,
    DemoEvent,
    PlaybackControls,
    _DemoHttpServer,
    _RunEngine,
    make_demo_server,
)
from tests.test_demo import _prepared_tiny
from tests.test_demo_controls import a_local_scene, eventually


@contextmanager
def a_run_host(
    tmp_path: Path,
    prepared: PreparedDataset | None = None,
    *,
    catalog: list[DatasetSpec] | None = None,
    fetch: Callable[[str, Path], None] | None = None,
) -> Iterator[_DemoHttpServer]:
    """The demo's run host, built but not serving: runs start on it directly."""
    server = make_demo_server(
        prepared,
        catalog=catalog,
        cache_dir=tmp_path / "cache",
        fetch=fetch,
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        history_store=RunHistoryStore(tmp_path / "history.db"),
    )
    assert isinstance(server, _DemoHttpServer)
    try:
        yield server
    finally:
        server.server_close()


def nothing_to_play(controls: PlaybackControls) -> Iterator[DemoEvent]:
    return iter(())


def a_playback_that_breaks(controls: PlaybackControls) -> Iterator[DemoEvent]:
    yield DemoEvent("status", {"text": "connecting to the CM5"})
    raise RuntimeError("CM5 link lost")


def an_unreachable_mirror(url: str, target: Path) -> None:
    raise OSError("mirror unreachable")


def scene_listed(host: _DemoHttpServer, scene_id: str) -> dict[str, object]:
    scenes = host.scene_listing()["datasets"]
    assert isinstance(scenes, list)
    found: dict[str, object] = next(scene for scene in scenes if scene["id"] == scene_id)
    return found


class AStuckRun(_RunEngine):
    """A run engine that never stops when a takeover waits for it."""

    waited_s: float | None = None

    def join(self, timeout: float) -> bool:
        self.waited_s = timeout
        return False


class ARunOverAtOnce(_RunEngine):
    """A run engine whose playback ends before the takeover can register it."""

    def start(self) -> None:
        self.done.set()


def test_a_new_run_is_refused_while_the_current_run_will_not_stop(tmp_path: Path) -> None:
    # Given a host whose current run does not stop when taken over
    prepared = _prepared_tiny(tmp_path)
    with a_run_host(tmp_path, prepared) as host:
        stuck = AStuckRun(host, "tiny-test", "Tiny", nothing_to_play)
        host.run_engine = stuck

        # When a new run is started on it
        started = host.start_run(prepared, None)

        # Then none starts: the stuck run stays current, after the takeover timeout
        assert started is None
        assert host.run_engine is stuck
        assert stuck.waited_s == TAKEOVER_TIMEOUT_S


def test_a_run_over_before_it_is_registered_leaves_nothing_playing(tmp_path: Path) -> None:
    # Given a host with nothing playing
    with a_run_host(tmp_path, _prepared_tiny(tmp_path)) as host:
        # When it takes over with a run that is over as soon as it starts
        engine = host._take_over(lambda: ARunOverAtOnce(host, "tiny-test", "Tiny", nothing_to_play))

        # Then that run is handed back, but neither it nor its controls stay current
        assert isinstance(engine, ARunOverAtOnce)
        assert host.run_engine is None and host.current is None


def test_a_run_whose_playback_breaks_is_persisted_as_interrupted(tmp_path: Path) -> None:
    # Given a recorded run whose playback fails after its first event
    with a_run_host(tmp_path, _prepared_tiny(tmp_path)) as host:
        engine = _RunEngine(host, "tiny-test", "Tiny", a_playback_that_breaks)

        # When it plays to the failure
        engine.start()
        assert engine.done.wait(timeout=10)

        # Then its history says it was interrupted, not completed
        run = host.history_store.get_run(engine.run_id)
        assert run is not None and run["status"] == "interrupted"


def test_a_scene_whose_download_fails_is_listed_as_failed_with_the_reason(
    tmp_path: Path,
) -> None:
    # Given a host offering one scene whose mirror is unreachable
    catalog = [a_local_scene(tmp_path, "street")]
    with a_run_host(tmp_path, catalog=catalog, fetch=an_unreachable_mirror) as host:
        # When the scene is prepared
        host.prepare("street")

        # Then the listing reports it failed, saying why
        eventually(lambda: scene_listed(host, "street")["state"] == "error")
        assert scene_listed(host, "street")["error"] == "mirror unreachable"
