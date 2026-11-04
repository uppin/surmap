"""Fakes behind the station tests: a manual clock, a Modal function, a health probe, a link.

`FakeModalFunction` stands in for `modal.Function` behind `ModalFunction`: it reports the
container and queue counts a test sets, and records every autoscaler update. `FakeProbe`
answers health checks from a script, and a 200 boots a container on the fake function, as a
GET does on Modal. `RecordingLinks` hands out the detector a started station is reached with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from surmap.survey.sam import CentredBoxVideoSamDetector, RawFrame, SamDetection

STATION_URL = "https://ginas-bb--surmap-station-serve.us-east.modal.run"


@dataclass
class FakeClock:
    """Monotonic seconds that move only when a test (or a fake sleep) moves them."""

    now: float = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


@dataclass(frozen=True)
class FakeStats:
    backlog: int
    num_total_runners: int
    num_running_inputs: int


@dataclass
class FakeModalFunction:
    containers: int = 0
    queued: int = 0
    running_inputs: int = 0
    unreachable: str | None = None
    autoscaler_updates: list[dict[str, int]] = field(default_factory=list)
    url: str = STATION_URL

    def get_current_stats(self) -> FakeStats:
        if self.unreachable is not None:
            raise ConnectionError(self.unreachable)
        return FakeStats(self.queued, self.containers, self.running_inputs)

    def update_autoscaler(
        self, *, min_containers: int | None = None, scaledown_window: int | None = None
    ) -> None:
        update = {"min_containers": min_containers, "scaledown_window": scaledown_window}
        self.autoscaler_updates.append({k: v for k, v in update.items() if v is not None})
        # Idle containers leave within the window; one serving an input stays until it ends.
        if min_containers == 0 and scaledown_window == 2 and self.running_inputs == 0:
            self.containers = 0

    def get_web_url(self) -> str:
        return self.url


@dataclass
class FakeProbe:
    """Health answers in order (the last repeats); a 200 means a container is up."""

    function: FakeModalFunction
    answers: list[int] = field(default_factory=lambda: [200])
    calls: list[str] = field(default_factory=list)

    def __call__(self, url: str) -> int:
        self.calls.append(url)
        answer = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if answer == 200:
            self.function.containers = max(self.function.containers, 1)
        return answer


class RecordingDetector(CentredBoxVideoSamDetector):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingLinks:
    """Connects to a started station: one detector per link, recording what it was given."""

    opened: list[tuple[str, str | None, str]] = field(default_factory=list)
    detectors: list[RecordingDetector] = field(default_factory=list)

    def __call__(self, url: str, token: str | None, prompt: str) -> RecordingDetector:
        self.opened.append((url, token, prompt))
        self.detectors.append(RecordingDetector())
        return self.detectors[-1]


def a_frame(frame_id: int = 1) -> RawFrame:
    return RawFrame(frame_id, frame_id * 1_000_000, 0, 376, 240, "jpeg", b"\xff\xd8")


def labels(detections: tuple[SamDetection, ...]) -> list[str]:
    return [detection.label for detection in detections]
