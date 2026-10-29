"""Place snapshot tracks on a replay clock.

When observation times overlap the replay, placement uses absolute
`t_ns`. Otherwise the replay progress scrubs each track along its own
observations, so a fixture recorded on another clock still moves.
"""

from __future__ import annotations

from surmap.types import Vec3
from surmap.viewer.model import PlacedTrack, SemanticMapSnapshot, Track


def clock_overlaps(snapshot: SemanticMapSnapshot, replay_start: int, replay_end: int) -> bool:
    for track in snapshot.tracks():
        for observation in track.observations:
            if replay_start <= observation.t_ns <= replay_end:
                return True
    return False


def placed_tracks(
    snapshot: SemanticMapSnapshot,
    t_ns: int,
    *,
    replay_start: int,
    replay_end: int,
) -> tuple[PlacedTrack, ...]:
    overlap = clock_overlaps(snapshot, replay_start, replay_end)
    placed = []
    for track in snapshot.tracks():
        sample_t = t_ns if overlap else _scrubbed_time(track, t_ns, replay_start, replay_end)
        xyz, trail, visible = _place(track, sample_t)
        placed.append(PlacedTrack(track, xyz, trail, visible))
    return tuple(placed)


def _scrubbed_time(track: Track, t_ns: int, replay_start: int, replay_end: int) -> int:
    ordered = sorted(track.observations, key=lambda item: item.t_ns)
    first = ordered[0].t_ns
    last = ordered[-1].t_ns
    if replay_end <= replay_start:
        return last
    progress = min(1.0, max(0.0, (t_ns - replay_start) / (replay_end - replay_start)))
    return int(round(first + progress * (last - first)))


def _place(track: Track, t_ns: int) -> tuple[Vec3, tuple[Vec3, ...], bool]:
    ordered = sorted(track.observations, key=lambda item: item.t_ns)
    if t_ns < ordered[0].t_ns:
        return ordered[0].xyz, (), False
    if t_ns >= ordered[-1].t_ns:
        trail = tuple(item.xyz for item in ordered)
        return ordered[-1].xyz, trail, True
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if later.t_ns < t_ns:
            continue
        span = later.t_ns - earlier.t_ns
        fraction = 0.0 if span == 0 else (t_ns - earlier.t_ns) / span
        xyz = _lerp(earlier.xyz, later.xyz, fraction)
        trail = tuple(item.xyz for item in ordered if item.t_ns <= earlier.t_ns)
        return xyz, trail + (xyz,), True
    return ordered[-1].xyz, tuple(item.xyz for item in ordered), True


def _lerp(start: Vec3, end: Vec3, fraction: float) -> Vec3:
    return Vec3(
        start.x + (end.x - start.x) * fraction,
        start.y + (end.y - start.y) * fraction,
        start.z + (end.z - start.z) * fraction,
    )
