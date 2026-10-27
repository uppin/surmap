"""Stage 3: area verdicts (design section 4 step 3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from surmap.moving.config import MovingConfig


class Verdict(Enum):
    """Area-track verdict; RIGID_MOVER and OSCILLATING are terminal."""

    UNKNOWN = "unknown"
    RIGID_MOVER = "rigid_mover"
    OSCILLATING = "oscillating"


@dataclass(frozen=True)
class AreaStats:
    """Motion statistics accumulated per area track."""

    observation_count: int
    span_ns: int
    net_displacement_m: float
    path_length_m: float
    velocity_coherence: float
    area_variance: float


@dataclass(frozen=True)
class VerdictUpdate:
    """A verdict and its version (increments only on change)."""

    verdict: Verdict
    version: int


_TERMINAL = (Verdict.RIGID_MOVER, Verdict.OSCILLATING)
_MIN_OBSERVATIONS = 5
_MIN_SPAN_NS = 1_000_000_000


class VerdictMachine:
    """Terminal, versioned verdict transitions per area track."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config
        self._state: dict[int, VerdictUpdate] = {}

    def update(self, track_id: int, stats: AreaStats) -> VerdictUpdate:
        """Fold new statistics into the track's verdict."""
        current = self._state.get(track_id, VerdictUpdate(Verdict.UNKNOWN, 0))
        if current.verdict in _TERMINAL:
            return current
        candidate = self._classify(stats)
        if candidate is current.verdict:
            return current
        updated = VerdictUpdate(candidate, current.version + 1)
        self._state[track_id] = updated
        return updated

    @staticmethod
    def _classify(stats: AreaStats) -> Verdict:
        if stats.observation_count < _MIN_OBSERVATIONS or stats.span_ns < _MIN_SPAN_NS:
            return Verdict.UNKNOWN
        net_path = (
            stats.net_displacement_m / stats.path_length_m if stats.path_length_m > 0 else 0.0
        )
        if stats.net_displacement_m >= 0.5 and net_path >= 0.6 and stats.velocity_coherence >= 0.6:
            return Verdict.RIGID_MOVER
        if (net_path <= 0.25 and stats.path_length_m >= 0.5) or stats.velocity_coherence <= 0.35:
            return Verdict.OSCILLATING
        return Verdict.UNKNOWN
