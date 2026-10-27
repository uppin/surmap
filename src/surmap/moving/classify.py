"""Stage 3: area verdicts (design section 4 step 3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from surmap.moving.config import MovingConfig
from surmap.types import Vec3


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


@dataclass
class _TrackAccum:
    first_t_ns: int
    last_t_ns: int
    first_centroid: Vec3
    last_centroid: Vec3
    count: int = 0
    path_m: float = 0.0
    velocity_sum: Vec3 = Vec3(0.0, 0.0, 0.0)
    speed_sum: float = 0.0
    area_mean: float = 0.0
    area_m2: float = 0.0


class TrackMotionStats:
    """Accumulates per-track motion statistics from area observations.

    This is what feeds `VerdictMachine`: net displacement vs path
    length (oscillation ratio), velocity coherence (mean velocity
    magnitude over mean speed), and area variance (Welford).
    """

    def __init__(self) -> None:
        self._tracks: dict[int, _TrackAccum] = {}

    def update(self, track_id: int, t_ns: int, centroid: Vec3, area: float) -> AreaStats:
        """Fold one observation in; returns the track's statistics."""
        accum = self._tracks.get(track_id)
        if accum is None:
            accum = _TrackAccum(t_ns, t_ns, centroid, centroid)
            self._tracks[track_id] = accum
        dt = (t_ns - accum.last_t_ns) / 1e9
        if accum.count > 0 and dt > 0:
            step = centroid - accum.last_centroid
            step_len = step.norm()
            accum.path_m += step_len
            velocity = Vec3(step.x / dt, step.y / dt, step.z / dt)
            accum.velocity_sum = Vec3(
                accum.velocity_sum.x + velocity.x,
                accum.velocity_sum.y + velocity.y,
                accum.velocity_sum.z + velocity.z,
            )
            accum.speed_sum += step_len / dt
        accum.count += 1
        accum.last_t_ns = t_ns
        accum.last_centroid = centroid
        delta = area - accum.area_mean
        accum.area_mean += delta / accum.count
        accum.area_m2 += delta * (area - accum.area_mean)
        net = (centroid - accum.first_centroid).norm()
        steps = max(accum.count - 1, 0)
        coherence = 0.0
        if steps > 0 and accum.speed_sum > 0:
            mean_velocity = Vec3(
                accum.velocity_sum.x / steps,
                accum.velocity_sum.y / steps,
                accum.velocity_sum.z / steps,
            )
            coherence = mean_velocity.norm() / (accum.speed_sum / steps)
        return AreaStats(
            observation_count=accum.count,
            span_ns=accum.last_t_ns - accum.first_t_ns,
            net_displacement_m=net,
            path_length_m=accum.path_m,
            velocity_coherence=min(1.0, coherence),
            area_variance=accum.area_m2 / accum.count if accum.count else 0.0,
        )


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
