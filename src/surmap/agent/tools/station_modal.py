"""`ModalStationControl`: the SAM station as the deployed `surmap-station` Modal app.

The station app (`surmap.survey.modal_station_app`) is deployed once and scales to zero. This
control reads it and drives it through the `modal` SDK's public `Function` API, behind the
`ModalFunction` protocol so nothing else here touches the SDK (it is an optional extra,
`uv sync --extra modal`, imported only by `modal_station_function`):

- the state comes from `get_current_stats()` (containers, queued requests, running inputs) and
  from what this control saw itself (a passed health check, a stop in flight). It never makes
  an HTTP call to the station: on Modal any request is an input, which would start a GPU or
  hold one up;
- `start()` is a health GET — the input that boots a container — repeated until it answers;
- `stop()` closes the agent's link, then lets idle containers go within 2 s
  (`autoscaler.update(min_containers=0, scaledown_window=2)`). A container serving another
  client's stream stays until that stream ends (`STOPPING`). `start()` puts the scaledown
  window back to the idle timeout.
"""

from __future__ import annotations

import importlib
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from surmap.agent.tools.station import (
    DEFAULT_IDLE_TIMEOUT_S,
    StationSamDetector,
    StationState,
    StationStatus,
    StationUnavailable,
)
from surmap.survey.sam import VideoSamDetector

HEALTH_PATH = "/health/is_alive"
STATION_FUNCTION = "serve"
# Modal's shortest scaledown window: an idle container leaves within it.
STOP_SCALEDOWN_S = 2

Probe = Callable[[str], int]
Connect = Callable[[str, "str | None", str], VideoSamDetector]


class LiveStats(Protocol):
    @property
    def backlog(self) -> int: ...
    @property
    def num_total_runners(self) -> int: ...
    @property
    def num_running_inputs(self) -> int: ...


class Autoscaler(Protocol):
    """`modal.Function.autoscaler`: overrides that last until the app is next deployed."""

    def update(
        self, *, min_containers: int | None = None, scaledown_window: int | None = None
    ) -> object: ...


class ModalFunction(Protocol):
    """The part of `modal.Function` the control uses."""

    @property
    def autoscaler(self) -> Autoscaler: ...
    def get_current_stats(self) -> LiveStats: ...
    def get_web_url(self) -> str | None: ...


class ModalStationControl:
    def __init__(
        self,
        function: ModalFunction,
        *,
        probe: Probe,
        connect: Connect,
        token: str | None,
        prompt: str,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        idle_timeout_s: int = DEFAULT_IDLE_TIMEOUT_S,
        start_timeout_s: int = 600,
        poll_s: float = 2.0,
        backend: str = "modal",
    ) -> None:
        self._function = function
        self._probe = probe
        self._connect = connect
        self._token = token
        self._prompt = prompt
        self._clock = clock
        self._sleep = sleep
        self._idle_timeout_s = idle_timeout_s
        self._start_timeout_s = start_timeout_s
        self._poll_s = poll_s
        self.backend = backend
        self._lock = threading.RLock()
        self._healthy = False
        self._stopping = False
        self._error: str | None = None
        self._last_used = 0.0
        self._live: VideoSamDetector | None = None

    def status(self) -> StationStatus:
        try:
            stats = self._function.get_current_stats()
        except Exception as exc:  # the SDK raises its own types; any failure reads as an error
            return self._status(StationState.ERROR, f"Modal cannot be reached: {exc}", 0)
        if self._error is not None:
            return self._status(StationState.ERROR, self._error, stats.num_total_runners)
        containers = stats.num_total_runners
        if containers == 0:
            self._healthy = False
            self._stopping = False
            if stats.backlog > 0:
                return self._status(StationState.QUEUED, "waiting for a GPU to be free", 0)
            return self._status(StationState.OFF, "", 0)
        if self._stopping:
            detail = (
                "a container still serves another client's stream"
                if stats.num_running_inputs > 0
                else "waiting for the idle container to leave"
            )
            return self._status(StationState.STOPPING, detail, containers)
        if self._healthy:
            return self._status(StationState.READY, "", containers)
        return self._status(StationState.STARTING, "waiting for its health check", containers)

    def start(self) -> StationStatus:
        with self._lock:
            if self.status().state == StationState.READY:
                return self.status()
            self._error = None
            self._stopping = False
            self._function.autoscaler.update(scaledown_window=self._idle_timeout_s)
            url = self._health_url()
            deadline = self._clock() + self._start_timeout_s
            while True:
                answer = self._probe(url)
                if answer == 200:
                    self._healthy = True
                    self._last_used = self._clock()
                    return self.status()
                if self._clock() >= deadline:
                    self._error = (
                        f"the station did not pass its health check in "
                        f"{self._start_timeout_s} s (last answer: {answer})"
                    )
                    raise StationUnavailable(self._error)
                self._sleep(self._poll_s)

    def stop(self) -> StationStatus:
        with self._lock:
            if self._live is not None:
                self._live.close()
                self._live = None
            if self.status().state == StationState.OFF:
                return self.status()
            self._healthy = False
            self._stopping = True
            self._function.autoscaler.update(min_containers=0, scaledown_window=STOP_SCALEDOWN_S)
            return self.status()

    def check_idle(self) -> StationStatus:
        with self._lock:
            idle_for = self._clock() - self._last_used
            if self._healthy and idle_for >= self._idle_timeout_s:
                return self.stop()
            return self.status()

    def detector(self) -> VideoSamDetector:
        return StationSamDetector(self._link, self._mark_used)

    def _link(self) -> VideoSamDetector:
        with self._lock:
            if self._live is not None and self._healthy:
                return self._live
            self.start()
            if self._live is None:
                self._live = self._connect(self._web_url(), self._token, self._prompt)
            return self._live

    def _mark_used(self) -> None:
        self._last_used = self._clock()

    def _web_url(self) -> str:
        url = self._function.get_web_url()
        if not url:
            raise StationUnavailable("the station app has no web URL: is it deployed?")
        return url.rstrip("/")

    def _health_url(self) -> str:
        return f"{self._web_url()}{HEALTH_PATH}"

    def _status(self, state: StationState, detail: str, containers: int) -> StationStatus:
        idle_for = int(self._clock() - self._last_used) if state == StationState.READY else 0
        return StationStatus(
            state=state,
            detail=detail,
            containers=containers,
            idle_timeout_s=self._idle_timeout_s,
            idle_for_s=idle_for,
            backend=self.backend,
        )


def http_health_probe(url: str, timeout_s: float = 30.0) -> int:
    """GET `url`; its status, or 0 when nothing answered in time (Modal redirects slow ones)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def modal_station_function(app: str, environment: str | None) -> ModalFunction:
    """The deployed station app's `serve` function — the one place the `modal` SDK is used."""
    try:
        modal = importlib.import_module("modal")
    except ImportError as exc:
        raise StationUnavailable(
            "the Modal station needs the modal SDK: uv sync --extra modal"
        ) from exc
    function: ModalFunction = modal.Function.from_name(
        app, STATION_FUNCTION, environment_name=environment
    )
    return function
