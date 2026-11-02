"""A recorded run's SAM results, served again as a video SAM session.

Rebuilding a run's RTAB-Map part (`/stream?rebuild_rtabmap=<run_id>`)
plays the scene live through RTAB-Map again, so its map and dense buffer
come from the current sidecar, while SAM is not run: each frame is
answered with the masks the recording journalled for it, matched by
`t_ns`. A frame the recording has no SAM result for gets none.
"""

from __future__ import annotations

from surmap.demo.history import RunHistoryStore
from surmap.survey.sam import RawFrame, SamDetection


def _detection(raw: object) -> SamDetection:
    """One journalled SAM object (`surmap.demo.events.sam_event`) as a detection."""
    assert isinstance(raw, dict)
    box = raw["box"]
    polygon = raw.get("mask_polygon") or []
    score = raw.get("score")
    track_id = raw.get("track_id")
    assert isinstance(box, list) and len(box) == 4 and isinstance(polygon, list)
    x0, y0, x1, y1 = (float(value) for value in box)
    return SamDetection(
        str(raw["label"]),
        None if score is None else float(str(score)),
        (x0, y0, x1, y1),
        tuple((float(point[0]), float(point[1])) for point in polygon),
        None if track_id is None else int(str(track_id)),
    )


class JournalSamDetector:
    """`VideoSamDetector` over a recorded run's journalled `sam` events."""

    def __init__(self, store: RunHistoryStore, run_id: str) -> None:
        self._by_t_ns: dict[int, tuple[SamDetection, ...]] = {}
        for kind, data in store.journal_events(run_id):
            if kind == "sam":
                objects = data.get("objects") or []
                assert isinstance(objects, list)
                self._by_t_ns[int(str(data["t_ns"]))] = tuple(_detection(o) for o in objects)

    def reset(self, prompt: str | None = None) -> None:
        """A new video; the recording's masks answer whatever prompt it names."""

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        return self._by_t_ns.get(frame.t_ns, ())

    def close(self) -> None:
        """Nothing to release: the masks were read from the journal."""
