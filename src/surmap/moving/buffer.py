"""Stage 5: per-track observation buffer (design section 4 step 5)."""

from __future__ import annotations

from dataclasses import dataclass

from surmap.types import Vec3


@dataclass(frozen=True)
class Observation:
    """One buffered observation of a graduated area track."""

    t_ns: int
    keypoints: tuple[Vec3, ...]
    centroid: Vec3
    velocity: Vec3
    vo_translation: Vec3  # VO increment since the previous observation


class ObservationBuffer:
    """Ring of observations per track, window- and cap-bounded."""

    def __init__(self, window_ns: int = 3_000_000_000, max_per_track: int = 64) -> None:
        self._window_ns = window_ns
        self._max_per_track = max_per_track
        self._tracks: dict[int, list[Observation]] = {}

    def add(self, track_id: int, observation: Observation) -> None:
        """Buffer one observation, evicting out-of-window ones."""
        entries = self._tracks.setdefault(track_id, [])
        entries.append(observation)
        cutoff = observation.t_ns - self._window_ns
        entries[:] = [entry for entry in entries if entry.t_ns >= cutoff]
        if len(entries) > self._max_per_track:
            del entries[: len(entries) - self._max_per_track]

    def observations(self, track_id: int) -> tuple[Observation, ...]:
        """Buffered observations for a track, oldest first."""
        return tuple(self._tracks.get(track_id, ()))
