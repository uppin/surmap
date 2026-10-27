"""Station server process: `python -m surmap.survey.station_main`.

Mounts `StationSamService` (n5) plus health routes on a real socket.
Until a SAM 3.1 adapter lands behind the `SamDetector` port, the served
detector is the in-memory one (no detections) — this process proves the
wire and the deployment, not SAM output.
"""

from __future__ import annotations

import argparse
import asyncio

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.survey.sam import SamDetector
from surmap.survey.station_server import station_service_module

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8081


def build_description(
    detector: SamDetector | None = None,
) -> ServerDescription[None]:
    """The station server's description: SAM service plus health routes."""
    return ServerDescription(
        services=(station_service_module(detector),),
        http_routes=health_routes(lambda: False),
    )


async def serve(host: str, port: int) -> None:
    """Serve the station description until cancelled; always stop the host."""
    server = HypercornHost(build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port` and serve until signalled."""
    parser = argparse.ArgumentParser(prog="surmap.survey.station_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    try:
        asyncio.run(serve(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
