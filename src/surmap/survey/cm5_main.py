"""CM5 server process: `python -m surmap.survey.cm5_main`.

Mounts `Cm5SurveyService` (n4) plus health routes on a real socket.
Until hardware adapters land, the served SLAM backend and object-point
source are the in-memory ones — this process proves the wire and the
deployment, not RTAB-Map or Coral output.
"""

from __future__ import annotations

from surmap.rpc.description import ServerDescription
from surmap.slam.base import SlamBackend
from surmap.survey.object_points import ObjectPointSource

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


def build_description(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
) -> ServerDescription[None]:
    """The CM5 server's description: survey service plus health routes."""
    raise NotImplementedError("TODO(pr-6): implement cm5_main.build_description")


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port` and serve until signalled."""
    raise NotImplementedError("TODO(pr-6): implement cm5_main.main")


if __name__ == "__main__":
    main()
