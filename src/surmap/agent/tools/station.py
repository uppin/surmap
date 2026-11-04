"""The SAM station: the GPU the agent's SAM runs on, up on first use, down when idle.

`StationControl` is the one interface the station tools, the agent's SAM and the chat page's
indicator depend on. Two implementations satisfy it: `StubStationControl` here (in process,
deterministic, the fake SAM behind it) and `ModalStationControl`
(`surmap.agent.tools.station_modal`, the deployed `surmap-station` Modal app).

Both hand the workspace the same `StationSamDetector`: its first `track()` starts the station
and every frame restarts the idle timeout; `check_idle()` stops a station that has had no frame
for `idle_timeout_s`, and `IdleTicker` calls it in the agent process.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from surmap.survey.sam import CentredBoxVideoSamDetector, RawFrame, SamDetection, VideoSamDetector

DEFAULT_IDLE_TIMEOUT_S = 300

_log = logging.getLogger(__name__)


class StationState(enum.Enum):
    OFF = "off"
    QUEUED = "queued"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class StationStatus:
    state: StationState
    detail: str
    containers: int
    idle_timeout_s: int
    idle_for_s: int
    backend: str


class StationUnavailable(RuntimeError):
    """The station could not be started; the message says why."""


class StationControl(Protocol):
    """Read, start and stop the SAM station, and run SAM on it."""

    def status(self) -> StationStatus:
        """Its state now; reading it never starts the GPU or keeps it up."""
        ...

    def start(self) -> StationStatus:
        """Bring it up and return once it answers; a no-op when it is ready."""
        ...

    def stop(self) -> StationStatus:
        """Take it down now; a no-op when it is off."""
        ...

    def check_idle(self) -> StationStatus:
        """Stop it if it has had no SAM frame for its idle timeout."""
        ...

    def detector(self) -> VideoSamDetector:
        """The SAM the agent's workspace runs: it starts the station on its first frame."""
        ...


class StationSamDetector:
    """A `VideoSamDetector` whose frames go to the station, started on demand.

    `link()` brings the station up when needed and returns the detector it is reached with;
    a fresh link (after a stop) is reset to the current video's prompt. `used()` restarts the
    station's idle timeout after each frame.
    """

    def __init__(self, link: Callable[[], VideoSamDetector], used: Callable[[], None]) -> None:
        self._link = link
        self._used = used
        self._prompt: str | None = None
        self._current: VideoSamDetector | None = None

    def reset(self, prompt: str | None = None) -> None:
        if prompt is not None:
            self._prompt = prompt
        if self._current is not None:
            self._current.reset(prompt)

    def track(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        linked = self._link()
        if linked is not self._current:
            linked.reset(self._prompt)
            self._current = linked
        detections = linked.track(frame)
        self._used()
        return detections

    def close(self) -> None:
        """Nothing to release here: the station's control owns its link."""


class StubStationControl:
    """An in-process station: off until started or used, ready at once, the fake SAM on it."""

    backend = "stub"

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        idle_timeout_s: int = DEFAULT_IDLE_TIMEOUT_S,
        sam: Callable[[], VideoSamDetector] = CentredBoxVideoSamDetector,
    ) -> None:
        self._clock = clock
        self._idle_timeout_s = idle_timeout_s
        self._sam = sam
        self._lock = threading.RLock()
        self._ready = False
        self._last_used = 0.0
        self._live: VideoSamDetector | None = None

    def status(self) -> StationStatus:
        idle_for = int(self._clock() - self._last_used) if self._ready else 0
        return StationStatus(
            state=StationState.READY if self._ready else StationState.OFF,
            detail="",
            containers=1 if self._ready else 0,
            idle_timeout_s=self._idle_timeout_s,
            idle_for_s=idle_for,
            backend=self.backend,
        )

    def start(self) -> StationStatus:
        with self._lock:
            if not self._ready:
                self._ready = True
                self._last_used = self._clock()
            return self.status()

    def stop(self) -> StationStatus:
        with self._lock:
            if self._live is not None:
                self._live.close()
                self._live = None
            self._ready = False
            return self.status()

    def check_idle(self) -> StationStatus:
        with self._lock:
            if self._ready and self._clock() - self._last_used >= self._idle_timeout_s:
                return self.stop()
            return self.status()

    def detector(self) -> VideoSamDetector:
        return StationSamDetector(self._link, self._mark_used)

    def _link(self) -> VideoSamDetector:
        with self._lock:
            self.start()
            if self._live is None:
                self._live = self._sam()
            return self._live

    def _mark_used(self) -> None:
        self._last_used = self._clock()


class IdleTicker:
    """Calls `control.check_idle()` every `every_s` seconds on a daemon thread until stopped."""

    def __init__(self, control: StationControl, every_s: float = 15.0) -> None:
        self._control = control
        self._every_s = every_s
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="station-idle", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def tick(self) -> None:
        """One idle check; a failure (a Modal API blip) is logged, and the next tick retries."""
        try:
            self._control.check_idle()
        except Exception:
            _log.warning("station idle check failed; retrying next tick", exc_info=True)

    def _run(self) -> None:
        while not self._stopped.wait(self._every_s):
            self.tick()
