"""Stream designations for surmap.survey.v1 outputs.

Every output on a survey stream carries an int32 designation:
RTAB-Map scene points are always 1, an echoed video frame takes its
channel's designation (2 or 3), and a tracked object's points take
``100 + track_id`` so objects are grouped per object.
"""

from __future__ import annotations

RTABMAP_DESIGNATION = 1
OBJECT_DESIGNATION_BASE = 100


def video_designation(channel: int) -> int:
    """The designation of the echoed video frame for `channel` (0 or 1)."""
    raise NotImplementedError("TODO(pr-1): implement video_designation")


def object_designation(track_id: int) -> int:
    """The designation of the points belonging to tracked object `track_id`."""
    raise NotImplementedError("TODO(pr-1): implement object_designation")
