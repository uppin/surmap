"""The console reruns a scene's cached recording by default; only Rebuild records a new one."""

import json
import urllib.request
from pathlib import Path

from surmap.demo.history import RunHistoryStore
from surmap.demo.server import make_demo_server
from tests.test_demo import _prepared_tiny
from tests.test_demo_replay import a_console, a_recorded_run, kinds
from tests.test_demo_sam_prompt import serving


def a_journalled_run(store: RunHistoryStore, dataset_id: str, status: str = "completed") -> str:
    run_id = store.create_run(dataset_id, "Scene")
    store.record_event(run_id, "frame", {"index": 0, "frame_id": 1})
    store.finish_run(run_id, status)
    return run_id


def test_a_scenes_cached_run_is_its_newest_complete_recording(tmp_path: Path) -> None:
    # Given a scene recorded twice, a broken-off recording, a replay, an
    # unjournalled legacy run, and another scene's recording
    store = RunHistoryStore(tmp_path / "history.db")
    a_journalled_run(store, "street")
    newest = a_journalled_run(store, "street")
    a_journalled_run(store, "street", status="interrupted")
    replay = a_journalled_run(store, "street")
    store.record_source(replay, newest)
    legacy = store.create_run("street", "Scene")
    store.finish_run(legacy)
    a_journalled_run(store, "room")

    # Then the scene's cached run is its newest complete, journalled recording
    assert store.latest_recording("street") == newest
    assert store.latest_recording("garden") is None


def test_the_scene_listing_names_each_scenes_cached_run(tmp_path: Path) -> None:
    # Given a console whose history holds a recording of its scene
    store = RunHistoryStore(tmp_path / "history.db")
    recorded = a_journalled_run(store, "tiny-test")
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        history_store=store,
    )

    # When the page asks which scenes there are
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/datasets", timeout=5) as response:
            listing = json.loads(response.read())

    # Then the scene names the run it would rerun, and an unrecorded one names none
    scenes = {scene["id"]: scene for scene in listing["datasets"]}
    assert scenes["tiny-test"]["cached_run"] == recorded
    assert scenes["kitti-2011-09-26-drive-0009"]["cached_run"] is None


def test_a_cached_rerun_is_not_persisted_as_another_run(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        # Given a recorded run
        run_id = a_recorded_run(console)
        runs_before = len(console.runs())

        # When it is rerun from its journal without recording
        events = console.stream(f"?replay={run_id}&speed=0&record=0")

        # Then it streams in full, under the recording's own run id, and adds no run
        assert len(kinds(events, "frame")) == 2 and len(kinds(events, "surface")) == 2
        assert kinds(events, "run")[0]["run_id"] == run_id
        assert len(console.runs()) == runs_before
        recorded = next(run for run in console.runs() if run["run_id"] == run_id)
        assert recorded["status"] == "completed"


def a_served_page(tmp_path: Path) -> str:
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False, sam_fake=True
    )
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            return response.read().decode()


def the_function(page: str, name: str) -> str:
    """The source of the page script's top-level function `name`."""
    start = page.index(f"function {name}(")
    return page[start : page.index("\n}\n", start)]


def test_the_console_opens_without_playing_and_rebuilds_only_on_request(
    tmp_path: Path,
) -> None:
    # When the console page is served
    page = a_served_page(tmp_path)

    # Then opening a scene starts no stream: it only offers the cached recording
    opening = the_function(page, "startDefault")
    assert "fillScenes().then(startDefault)" in page
    assert "playCached(" not in opening and "EventSource" not in opening
    assert "offerCached(scene.cached_run)" in opening
    # ... a Rebuild button replaces Restart
    assert 'id="rebuild"' in page and 'id="restart"' not in page
    # ... and applying a new SAM prompt is a rebuild: it needs fresh SAM results
    assert '<input type="hidden" name="rebuild" value="1">' in page


def test_replay_cached_run_plays_the_recording_without_persisting_it(tmp_path: Path) -> None:
    # When the console page is served
    page = a_served_page(tmp_path)

    # Then a Replay cached run button, disabled until a recording is offered,
    # reruns that recording unrecorded
    assert '<button id="replay-cached" disabled' in page
    offering = the_function(page, "offerCached")
    assert "replayCached.disabled = false" in offering
    assert "$('replay-cached').addEventListener('click', () => playCached(cachedRun))" in page
    assert "&record=0" in the_function(page, "playCached")


def test_a_run_cut_short_by_a_takeover_is_not_a_complete_recording(tmp_path: Path) -> None:
    import queue
    import threading

    from surmap.demo.datasets import ensure_dataset
    from tests.test_demo_controls import a_demo_server, a_local_scene, eventually, stream_kinds

    # Given a two-frame scene playing slowly (4 s) to a first viewer, so a
    # takeover lands mid-run even on a loaded machine
    catalog = [a_local_scene(tmp_path, "street")]
    ensure_dataset(catalog[0], tmp_path / "cache", log=lambda _: None)
    with a_demo_server(catalog, tmp_path / "cache", fps=0.5) as base:
        first: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", first), daemon=True).start()
        assert first.get(timeout=10) == "run"
        assert first.get(timeout=10) == "frame"

        # When a second viewer takes it over before it ends
        second: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", second), daemon=True).start()
        assert second.get(timeout=10) == "run"

        # Then the cut-short run is persisted as interrupted, never as a cached run
        def runs() -> list[dict[str, object]]:
            with urllib.request.urlopen(f"{base}/runs", timeout=5) as response:
                listed: list[dict[str, object]] = json.loads(response.read())["runs"]
            return listed

        eventually(lambda: any(run["status"] == "interrupted" for run in runs()))
        cut_short = next(run for run in runs() if run["status"] == "interrupted")
        assert int(str(cut_short["frame_count"])) < 2
