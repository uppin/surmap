"""Demo: a rewound moment shows its surfaces as the current surface logic makes them.

A run records the surfaces of the logic it ran with. Rewinding an old
recording must not show that old logic's smears and one-point "surfaces"
while live runs and replays show the current logic's: a journalled run's
moment is recomputed from its journal, like a replay up to that frame.
"""

import json
import urllib.request
from pathlib import Path

import pytest

from surmap.demo.history import RunHistoryStore
from surmap.demo.surface_timeline import SurfaceTimeline
from tests.test_demo_replay import MASK_PIXELS, Console, a_console, a_recorded_run
from tests.test_demo_replay_sam import JPEG


def snapshot(console: Console, run_id: str, seq: int) -> dict[str, object]:
    with urllib.request.urlopen(
        f"{console.base}/runs/{run_id}/snapshot?seq={seq}", timeout=20
    ) as r:
        loaded: dict[str, object] = json.loads(r.read())
    return loaded


def surface_count(moment: dict[str, object]) -> int:
    surfaces = moment["surfaces"]
    assert isinstance(surfaces, list)
    return len(surfaces)


def test_a_rewound_moment_shows_the_current_logics_surfaces_not_the_recorded_ones(
    tmp_path: Path,
) -> None:
    # Given a recorded run: its live regions were two points each (no surface then),
    # while its journalled dense buffer holds the car as a wall 2 m away
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
        assert console.store.surfaces_at(run_id, 99) == []

        # When its first moment is rewound to
        moment = snapshot(console, run_id, 0)

    # Then the moment shows the surface today's logic makes of the journal
    surfaces = moment["surfaces"]
    assert isinstance(surfaces, list) and len(surfaces) == 1
    surface = surfaces[0]
    assert (surface["surface_id"], surface["label"], surface["moving"]) == (1, "car", False)
    assert 0 < len(surface["points"]) <= MASK_PIXELS


def test_a_rewound_moment_says_which_surface_each_sam_track_became(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
        moment = snapshot(console, run_id, 0)
    # SAM's track 1 (the car) became surface 1 on that frame, so its card links
    assert moment["surface_tracks"] == [{"track_id": 1, "surface_id": 1}]


def test_a_later_moment_holds_everything_assigned_up_to_it(tmp_path: Path) -> None:
    # Given a recorded run's first two moments
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
        first, second = snapshot(console, run_id, 0), snapshot(console, run_id, 1)

    # Then every point the car's surface had on the first is still on it on the second
    one, two = first["surfaces"], second["surfaces"]
    assert isinstance(one, list) and isinstance(two, list)
    held_then = {tuple(point) for point in one[0]["points"]}
    held_later = {tuple(point) for point in two[0]["points"]}
    assert held_then and held_then <= held_later


def test_a_run_without_a_journal_keeps_its_recorded_surfaces(tmp_path: Path) -> None:
    # Given a run recorded before journals existed, with one surface row
    store = RunHistoryStore(tmp_path / "history.db")
    run_id = store.create_run("tiny-test", "Tiny")
    store.record_frame(run_id, index=0, frame_id=1, t_ns=1, jpeg=JPEG, overlay=[], camera=None)
    store.record_surface(
        run_id,
        frame_id=1,
        surface_id=4,
        label="car",
        track_id=2,
        points=[[1.0, 2.0, 3.0]],
        moving=False,
    )

    # Then there is nothing to recompute it from, and its moment shows what was recorded
    assert SurfaceTimeline.of(store, run_id) is None
    moment = store.snapshot_at(run_id, 0)
    assert moment is not None
    assert moment["surfaces"] == [
        {"surface_id": 4, "label": "car", "moving": False, "points": [[1.0, 2.0, 3.0]]}
    ]


def test_the_timeline_is_computed_once_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a recorded run, and a count of timeline computations
    computed: list[str] = []
    compute = SurfaceTimeline.of

    def counting(store: RunHistoryStore, run_id: str) -> SurfaceTimeline | None:
        computed.append(run_id)
        return compute(store, run_id)

    monkeypatch.setattr(SurfaceTimeline, "of", staticmethod(counting))
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)

        # When four moments of it are rewound to
        moments = [snapshot(console, run_id, seq) for seq in (0, 1, 0, 1)]

    # Then its timeline was computed once and served all four
    assert computed == [run_id]
    assert [surface_count(moment) for moment in moments] == [1, 1, 1, 1]


def test_rewinding_never_runs_sam(tmp_path: Path) -> None:
    # Given a recorded run
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
        tracked = console.sam.tracked

        # When its moments are rewound to
        snapshot(console, run_id, 0)
        snapshot(console, run_id, 1)

        # Then SAM tracked nothing more: the journal holds its masks
        assert console.sam.tracked == tracked


def test_a_timeline_gives_each_moments_surfaces_and_sam_links(tmp_path: Path) -> None:
    # Given a recorded run's timeline
    with a_console(tmp_path) as console:
        run_id = a_recorded_run(console)
    timeline = SurfaceTimeline.of(console.store, run_id)
    assert timeline is not None

    # When its first frame is read
    surfaces, tracks = timeline.at(1)

    # Then it holds the car's surface, and SAM's track 1 became it
    assert [surface["surface_id"] for surface in surfaces] == [1]
    assert tracks == [{"track_id": 1, "surface_id": 1}]


def test_the_page_links_a_rewound_moments_sam_cards(tmp_path: Path) -> None:
    with a_console(tmp_path) as console:
        with urllib.request.urlopen(f"{console.base}/", timeout=5) as response:
            page = response.read().decode()
    show = page.split("async function showSnapshot(", 1)[1].split("\n}", 1)[0]
    assert "noteSurfaces({frame_id: snap.frame_id, surfaces: snap.surface_tracks" in show
    assert show.index("noteSurfaces(") < show.index("drawSamPane(")
