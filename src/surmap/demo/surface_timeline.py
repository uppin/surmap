"""A journalled run's surfaces as the current surface logic makes them, frame by frame.

A run records the surfaces of the logic it ran with (`surface_points`).
Rewinding an old recording should not show that old logic's surfaces
while live runs and replays show today's, so a rewound moment of a
journalled run is recomputed: its journal is replayed once
(`JournalPlayer`, regions from the dense buffer, no RTAB-Map or SAM) and
every surface assignment is kept with its frame. `at(frame_id)` is then
every surface as assigned up to that frame, and which surface each SAM
track became on it, so the SAM view's cards link while rewinding.
A run without a journal has nothing to recompute from (`of` is None) and
keeps its recorded surfaces.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from surmap.demo.history import RunHistoryStore
from surmap.demo.replay import JournalPlayer

Assignment = dict[str, object]


@dataclass(frozen=True)
class SurfaceTimeline:
    """Every surface assignment of a replayed journal, in order, with its frame."""

    assignments: tuple[tuple[int, Assignment], ...]

    @staticmethod
    def of(store: RunHistoryStore, run_id: str) -> SurfaceTimeline | None:
        root = store.root_run(run_id)
        if store.rig(root) is None:
            return None
        assignments: list[tuple[int, Assignment]] = []
        for event in JournalPlayer(store, root).events():
            if event.kind != "surface":
                continue
            frame_id = int(str(event.data["frame_id"]))
            surfaces = event.data["surfaces"]
            assert isinstance(surfaces, list)
            assignments.extend((frame_id, surface) for surface in surfaces)
        return SurfaceTimeline(tuple(assignments))

    def at(self, frame_id: int) -> tuple[list[Assignment], list[dict[str, int]]]:
        """The surfaces up to `frame_id`, and each SAM track's surface on that frame."""
        surfaces: dict[int, Assignment] = {}
        tracks: list[dict[str, int]] = []
        for frame, assignment in self.assignments:
            if frame > frame_id:
                break
            surface_id = int(str(assignment["surface_id"]))
            points = assignment["points"]
            assert isinstance(points, list)
            surface = surfaces.setdefault(
                surface_id,
                {
                    "surface_id": surface_id,
                    "label": assignment["label"],
                    "moving": False,
                    "points": [],
                },
            )
            surface["moving"] = bool(assignment["moving"])
            held = surface["points"]
            assert isinstance(held, list)
            held.extend(points)
            if frame == frame_id:
                tracks.append(
                    {"track_id": int(str(assignment["track_id"])), "surface_id": surface_id}
                )
        return [surfaces[key] for key in sorted(surfaces)], tracks


class SurfaceTimelines:
    """The console's timelines, each computed once per run on first use."""

    def __init__(self, store: RunHistoryStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._timelines: dict[str, SurfaceTimeline | None] = {}
        self._computing: dict[str, threading.Lock] = {}

    def get(self, run_id: str) -> SurfaceTimeline | None:
        with self._lock:
            if run_id in self._timelines:
                return self._timelines[run_id]
            computing = self._computing.setdefault(run_id, threading.Lock())
        with computing:
            with self._lock:
                if run_id in self._timelines:
                    return self._timelines[run_id]
            timeline = SurfaceTimeline.of(self._store, run_id)
            with self._lock:
                self._timelines[run_id] = timeline
            return timeline
