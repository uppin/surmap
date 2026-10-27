"""CM5 server process: `python -m surmap.survey.cm5_main`.

Mounts `Cm5SurveyService` (n4) plus health routes on a real socket.
Scene points are real: the stereo reconstructor turns the streamed
pairs into points. Pose and object points still come from the
in-memory adapters until RTAB-Map and the Coral tracker land behind
their ports.
"""

from __future__ import annotations

import argparse
import asyncio

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.slam.base import SlamBackend
from surmap.survey.cm5_server import cm5_service_module
from surmap.survey.object_points import ObjectPointSource
from surmap.survey.stereo import StereoReconstructor

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


def build_description(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
    stereo: StereoReconstructor | None = None,
) -> ServerDescription[None]:
    """The CM5 server's description: survey service plus health routes."""
    return ServerDescription(
        services=(
            cm5_service_module(
                slam, objects, stereo if stereo is not None else StereoReconstructor()
            ),
        ),
        http_routes=health_routes(lambda: False),
    )


async def serve(host: str, port: int) -> None:
    """Serve the CM5 description until cancelled; always stop the host."""
    server = HypercornHost(build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port` and serve until signalled."""
    parser = argparse.ArgumentParser(prog="surmap.survey.cm5_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    try:
        asyncio.run(serve(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
