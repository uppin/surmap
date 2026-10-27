"""A small CPU multi-object tracker: detections in, track IDs out.

Tracking is not a neural model — on the CM5 it runs on CPU next to
the Edge TPU detector. This is a greedy IoU tracker: each frame's
detections are matched to live tracks by box overlap (best pair
first), unmatched detections start new tracks with monotonically
increasing IDs (never reused), and tracks unseen for more than
`max_missed` frames expire. Deliberately no motion model: the
contract is stable IDs for continuously visible objects, which is
what the survey stream's `100 + track_id` designations key on.
"""

from __future__ import annotations

from dataclasses import dataclass

from surmap.types import Detection


@dataclass(frozen=True)
class TrackedDetection:
    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    track_id: int
    frame_id: int


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x_min = max(a[0], b[0])
    y_min = max(a[1], b[1])
    x_max = min(a[2], b[2])
    y_max = min(a[3], b[3])
    intersection = max(0.0, x_max - x_min) * max(0.0, y_max - y_min)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    label: str
    box_xyxy: tuple[float, float, float, float]
    last_seen_frame: int


class IouTracker:
    """Greedy IoU association with persistent, never-reused track IDs."""

    def __init__(self, *, iou_threshold: float = 0.3, max_missed: int = 5) -> None:
        self._iou_threshold = iou_threshold
        self._max_missed = max_missed
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    @property
    def live_track_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._tracks))

    def update(
        self, frame_id: int, detections: tuple[Detection, ...]
    ) -> tuple[TrackedDetection, ...]:
        """Assign track IDs to `detections` seen at `frame_id`."""
        candidates = sorted(
            (
                (_iou(track.box_xyxy, detection.box_xyxy), track_id, index)
                for track_id, track in self._tracks.items()
                for index, detection in enumerate(detections)
                if detection.label == track.label
            ),
            reverse=True,
        )
        matched_tracks: set[int] = set()
        matched_detections: dict[int, int] = {}
        for iou, track_id, index in candidates:
            if iou < self._iou_threshold:
                break
            if track_id in matched_tracks or index in matched_detections:
                continue
            matched_tracks.add(track_id)
            matched_detections[index] = track_id

        tracked: list[TrackedDetection] = []
        for index, detection in enumerate(detections):
            matched_id = matched_detections.get(index)
            if matched_id is None:
                track_id = self._next_id
                self._next_id += 1
                self._tracks[track_id] = _Track(
                    track_id, detection.label, detection.box_xyxy, frame_id
                )
            else:
                track_id = matched_id
                track = self._tracks[track_id]
                track.box_xyxy = detection.box_xyxy
                track.last_seen_frame = frame_id
            tracked.append(
                TrackedDetection(
                    label=detection.label,
                    score=detection.score,
                    box_xyxy=detection.box_xyxy,
                    track_id=track_id,
                    frame_id=frame_id,
                )
            )
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if frame_id - track.last_seen_frame > self._max_missed
        ]
        for track_id in expired:
            del self._tracks[track_id]
        return tuple(tracked)
