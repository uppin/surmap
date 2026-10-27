"""Station server process: `python -m surmap.survey.station_main`.

Mounts `StationSamService` (n5) plus health routes on a real socket.
Until a SAM 3.1 adapter lands behind the `SamDetector` port, the served
detector is the in-memory one (no detections) — this process proves the
wire and the deployment, not SAM output.
"""

from __future__ import annotations

from surmap.rpc.description import ServerDescription
from surmap.survey.sam import SamDetector

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8081


def build_description(
    detector: SamDetector | None = None,
) -> ServerDescription[None]:
    """The station server's description: SAM service plus health routes."""
    raise NotImplementedError("TODO(pr-6): implement station_main.build_description")


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port` and serve until signalled."""
    raise NotImplementedError("TODO(pr-6): implement station_main.main")


if __name__ == "__main__":
    main()
