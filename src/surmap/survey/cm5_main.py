"""CM5 server process: `python -m surmap.survey.cm5_main`.

Mounts `Cm5SurveyService` (n4) plus health routes on a real socket.
By default scene points are the stereo reconstructor's, pose is the
in-memory adapter. With `--slam-backend sidecar`, pose and scene
points come from the real RTAB-Map Docker sidecar instead (no stereo
reconstruction: RTAB-Map's own cloud is the scene), calibrated by the
EuRoC `sensor.yaml` files under `--calibration-dir`:

    python -m surmap.survey.cm5_main --slam-backend sidecar \
        --calibration-dir tests/fixtures/euroc_v101_rtabmap
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.slam.base import SlamBackend
from surmap.slam.sidecar import PINNED_RTABMAP_IMAGE, SidecarRtabmapBackend
from surmap.survey.cm5_server import cm5_service_module
from surmap.survey.object_points import ObjectPointSource
from surmap.survey.stereo import StereoReconstructor

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


def build_description(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
    stereo: StereoReconstructor | None = None,
    *,
    use_stereo: bool = True,
) -> ServerDescription[None]:
    """The CM5 server's description: survey service plus health routes."""
    if stereo is None and use_stereo:
        stereo = StereoReconstructor()
    return ServerDescription(
        services=(cm5_service_module(slam, objects, stereo),),
        http_routes=health_routes(lambda: False),
    )


def sidecar_backend(
    calibration_dir: Path, image: str = PINNED_RTABMAP_IMAGE
) -> SidecarRtabmapBackend:
    """The RTAB-Map sidecar backend calibrated from a EuRoC dataset dir."""
    mav0 = calibration_dir / "mav0"

    def read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    return SidecarRtabmapBackend(
        cam0_yaml=read(mav0 / "cam0" / "sensor.yaml"),
        cam1_yaml=read(mav0 / "cam1" / "sensor.yaml"),
        imu_yaml=read(mav0 / "imu0" / "sensor.yaml"),
        imu_csv=read(mav0 / "imu0" / "data.csv"),
        image=image,
    )


async def serve(host: str, port: int, description: ServerDescription[None] | None = None) -> None:
    """Serve the CM5 description until cancelled; always stop the host."""
    server = HypercornHost(description or build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port`/`--slam-backend` and serve until signalled."""
    parser = argparse.ArgumentParser(prog="surmap.survey.cm5_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--slam-backend", choices=("inmemory", "sidecar"), default="inmemory")
    parser.add_argument(
        "--calibration-dir",
        type=Path,
        default=None,
        help="EuRoC dataset dir holding mav0/{cam0,cam1,imu0} for the sidecar backend",
    )
    parser.add_argument("--rtabmap-image", default=PINNED_RTABMAP_IMAGE)
    args = parser.parse_args(argv)
    description = None
    if args.slam_backend == "sidecar":
        if args.calibration_dir is None:
            parser.error("--slam-backend sidecar requires --calibration-dir")
        description = build_description(
            slam=sidecar_backend(args.calibration_dir, args.rtabmap_image),
            use_stereo=False,
        )
    try:
        asyncio.run(serve(args.host, args.port, description))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
