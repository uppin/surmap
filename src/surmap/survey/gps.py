"""GPS fixes on the CM5 survey stream, anchored to the posed frame nearest in time."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from surmap.survey.v1 import survey_pb2
from surmap.types import Vec3

# A fix further than this from every posed frame is not anchored.
MAX_ANCHOR_GAP_NS = 500_000_000


@dataclass
class PoseTimeline:
    """Map positions of one stream's posed frames, ordered by time."""

    _times: list[int] = field(default_factory=list)
    _frames: list[tuple[int, Vec3]] = field(default_factory=list)

    def add(self, frame_id: int, t_ns: int, position: Vec3) -> None:
        index = bisect.bisect_left(self._times, t_ns)
        if index < len(self._times) and self._times[index] == t_ns:
            # The same frame posed again (odometry after the pair result): keep the latest.
            self._frames[index] = (frame_id, position)
            return
        self._times.insert(index, t_ns)
        self._frames.insert(index, (frame_id, position))

    def nearest(self, t_ns: int, max_gap_ns: int = MAX_ANCHOR_GAP_NS) -> tuple[int, Vec3] | None:
        """The posed frame nearest to `t_ns` within `max_gap_ns`; ties go to the earlier frame."""
        index = bisect.bisect_left(self._times, t_ns)
        candidates = [i for i in (index - 1, index) if 0 <= i < len(self._times)]
        if not candidates:
            return None
        best = min(candidates, key=lambda i: abs(self._times[i] - t_ns))
        if abs(self._times[best] - t_ns) > max_gap_ns:
            return None
        return self._frames[best]


def gps_anchor(fix: survey_pb2.GpsFix, timeline: PoseTimeline) -> survey_pb2.Cm5Response:
    """The response to one fix: the fix, plus the nearest posed frame when there is one."""
    anchor = survey_pb2.GpsAnchorOut(fix=fix)
    nearest = timeline.nearest(fix.t_ns)
    if nearest is not None:
        frame_id, position = nearest
        anchor.frame_id = frame_id
        anchor.map_position.CopyFrom(survey_pb2.Point3(x=position.x, y=position.y, z=position.z))
    return survey_pb2.Cm5Response(gps_anchor=anchor)
