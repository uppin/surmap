"""Replaying cached runs: the SAM overlay is shown, and long journals stream promptly."""

import urllib.request
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from surmap.demo.history import RunHistoryStore
from surmap.demo.replay import Bounds, CloudRenderer, JournalPlayer
from surmap.demo.server import make_demo_server
from surmap.demo.surface_render import SurfaceLayer
from tests.test_demo import _prepared_tiny
from tests.test_demo_sam_prompt import serving

JPEG = b"\xff\xd8frame\xff\xd9"
A_CAR = {"label": "car", "score": 0.9, "track_id": 1, "box": [1, 1, 9, 9], "mask_polygon": []}
A_TRUCK = {**A_CAR, "label": "truck", "track_id": 2}


class CountingStore(RunHistoryStore):
    """Counts how much of the journal a replay has read so far."""

    read = 0

    def journal_events(self, run_id: str) -> Iterator[tuple[str, dict[str, object]]]:
        for entry in super().journal_events(run_id):
            self.read += 1
            yield entry


def a_long_run(store: RunHistoryStore, frames: int = 40) -> str:
    run_id = store.create_run("tiny-test", "Tiny")
    for index in range(frames):
        frame_id = index + 1
        store.record_frame(
            run_id,
            index=index,
            frame_id=frame_id,
            t_ns=frame_id,
            jpeg=JPEG,
            overlay=[],
            camera=None,
        )
        store.record_event(run_id, "frame", {"index": index, "frame_id": frame_id})
        store.record_event(
            run_id,
            "map",
            {"frame_id": frame_id, "points": [[0.0, 0.0, 1.0]], "point_colors": [[9, 9, 9]]},
        )
    store.record_event(run_id, "final", {"points": [[0.0, 0.0, 1.0]], "point_colors": [[9, 9, 9]]})
    return run_id


def a_render() -> tuple[list[int], CloudRenderer]:
    calls: list[int] = []

    def render(
        points: NDArray[np.float32],
        colors: NDArray[np.uint8],
        bounds: Bounds,
        layer: SurfaceLayer,
    ) -> str:
        calls.append(len(points))
        return "png"

    return calls, render


def test_a_replay_streams_its_first_frame_before_reading_the_whole_journal(
    tmp_path: Path,
) -> None:
    # Given a long recorded run
    store = CountingStore(tmp_path / "history.db")
    run_id = a_long_run(store)

    # When its replay yields its first frame
    events = JournalPlayer(store, run_id).events()
    first_frame = next(event for event in events if event.kind == "frame")

    # Then only the journal's head was read for it
    assert first_frame.data["frame_id"] == 1
    assert 1 <= store.read <= 2


def test_a_replay_draws_the_map_at_the_live_cadence_not_per_journalled_update(
    tmp_path: Path,
) -> None:
    # Given a run journalled with one map update per frame (a slow recording)
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = a_long_run(store)
    renders, render = a_render()

    # When it replays faster than the map's 0.33 s cadence (the clock stands still)
    player = JournalPlayer(store, run_id, render_cloud=render, clock=lambda: 0.0)
    kinds = [event.kind for event in player.events()]

    # Then the first map and the newest one before the end are drawn, not all 40
    assert kinds.count("frame") == 40
    assert kinds.count("map") == 2
    assert kinds[-1] == "final"
    assert len(renders) == 3


def test_a_console_without_sam_can_still_show_a_replays_sam_masks(tmp_path: Path) -> None:
    # Given a console started without SAM
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )

    # When its page is loaded
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

    # Then a hidden SAM view is there for replayed masks, with nothing to prompt
    assert '<div class="sam-pane" id="sam-pane" hidden>' in page
    assert 'id="sam-view"' in page
    assert 'id="sam-prompt"' not in page
    assert "samPane.hidden = false" in page


def test_a_history_moment_carries_the_sam_masks_seen_by_then(tmp_path: Path) -> None:
    # Given a run where SAM saw a car on frame 1 and a truck on frame 2
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = store.create_run("tiny-test", "Tiny")
    for index in range(3):
        store.record_frame(
            run_id,
            index=index,
            frame_id=index + 1,
            t_ns=index + 1,
            jpeg=JPEG,
            overlay=[],
            camera=None,
        )
    store.record_event(run_id, "sam", {"frame_id": 1, "t_ns": 1, "objects": [A_CAR]})
    store.record_event(run_id, "sam", {"frame_id": 2, "t_ns": 2, "objects": [A_TRUCK]})

    # When the run is rewound to frames 1 and 3
    first = store.snapshot_at(run_id, 0)
    third = store.snapshot_at(run_id, 2)

    # Then each moment carries the newest SAM result by then, with its image
    assert first is not None and third is not None
    sam_first, sam_third = first["sam"], third["sam"]
    assert isinstance(sam_first, dict) and isinstance(sam_third, dict)
    assert sam_first["objects"] == [A_CAR]
    assert sam_third["frame_id"] == 2 and sam_third["objects"] == [A_TRUCK]
    assert sam_third["image_b64"]


def test_scrubbing_draws_the_snapshots_sam_masks(tmp_path: Path) -> None:
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

    assert "if (snap.sam) drawSamPane(snap.sam)" in page


def test_a_stream_played_to_its_end_says_so_last(tmp_path: Path) -> None:
    # Given a console playing a two-frame scene
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )

    # When a viewer plays it to the end
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/stream", timeout=10) as response:
            body = response.read().decode()

    # Then the last event tells the page the run is over, so it does not reconnect
    assert body.rstrip().splitlines()[-2:] == [
        "event: ended",
        'data: {"reason": "finished"}',
    ]


def test_a_viewer_whose_run_is_taken_over_is_told_so(tmp_path: Path) -> None:
    import queue
    import threading

    from surmap.demo.datasets import ensure_dataset
    from tests.test_demo_controls import a_demo_server, a_local_scene, stream_kinds

    # Given a slow scene playing to a first viewer
    catalog = [a_local_scene(tmp_path, "street")]
    ensure_dataset(catalog[0], tmp_path / "cache", log=lambda _: None)
    with a_demo_server(catalog, tmp_path / "cache", fps=2.0) as base:
        first: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", first), daemon=True).start()
        assert first.get(timeout=10) == "run"

        # When a second viewer takes the run over
        second: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_kinds, args=(f"{base}/stream", second), daemon=True).start()
        assert second.get(timeout=10) == "run"

        # Then the first viewer's stream ends by saying so, before it closes
        kinds: list[str] = []
        while (kind := first.get(timeout=10)) != "end":
            kinds.append(kind)
        assert kinds[-1] == "ended"


def test_the_page_stops_streaming_once_its_run_has_ended(tmp_path: Path) -> None:
    server = make_demo_server(
        _prepared_tiny(tmp_path), host="127.0.0.1", port=0, with_rtabmap=False
    )
    with serving(server) as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            page = response.read().decode()

    assert "source.addEventListener('ended'" in page
