"""Stage 3: area verdicts (design section 4 step 3).

TODO(n4): implemented by pr-4-moving-classification's Green row.
"""

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


class VerdictMachine:
    """Terminal, versioned verdict transitions per area track."""

    def __init__(self, config: MovingConfig) -> None:
        self._config = config

    def update(self, track_id: int, stats: AreaStats) -> VerdictUpdate:
        """Fold new statistics into the track's verdict."""
        raise NotImplementedError("TODO(n4): VerdictMachine.update")
