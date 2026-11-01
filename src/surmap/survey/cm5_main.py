"""CM5 server process: `python -m surmap.survey.cm5_main`.

Mounts `Cm5SurveyService` (n4) plus health routes on a real socket.
By default scene points are the stereo reconstructor's, pose is the
in-memory adapter. With `--slam-backend sidecar`, pose and scene
points come from the real RTAB-Map Docker sidecar instead (no stereo
reconstruction: RTAB-Map's own cloud is the scene), calibrated by the
EuRoC `sensor.yaml` files under `--calibration-dir`:

    python -m surmap.survey.cm5_main --slam-backend sidecar \
        --calibration-dir tests/fixtures/euroc_v101_rtabmap

`--slam-backend streaming` runs the live RTAB-Map sidecar instead: poses
arrive while the stream runs (the batch sidecar only has them at the
end), and the same sidecar serves `StreamRegionPoints` — dense points
under a SAM polygon on a recent frame. Frames are resized to
`--frame-size` (default 376x240) for it.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path

from surmap.demo.datasets import scaled_sensor_yaml
from surmap.detection.detector import CoralDetector
from surmap.detection.profiles import DEFAULT_PROFILE, MODEL_PROFILES
from surmap.detection.source import CoralDetectionSource, CoralObjectPointSource, DetectionSource
from surmap.rpc.description import Closeable, ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.slam.base import SlamBackend
from surmap.slam.regions import RegionPointSource
from surmap.slam.sidecar import PINNED_RTABMAP_IMAGE, SidecarRtabmapBackend
from surmap.slam.stream_process import StreamProcess
from surmap.slam.streaming import StreamingRtabmapBackend
from surmap.survey.cm5_server import SlamFactory, cm5_service_module
from surmap.survey.object_points import ObjectPointSource
from surmap.survey.stereo import StereoReconstructor
from surmap.survey.v1 import survey_pb2

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


class _BackendCloseable:
    """Adapts a backend's sync `close()` to the host's async closeables.

    Registered whenever a backend is supplied, so stopping the server
    always tears the backend down — for the RTAB-Map sidecar that
    force-removes any live container and deletes its staging dir,
    even on a failed or interrupted stream.
    """

    def __init__(self, backend: SlamBackend) -> None:
        self._backend = backend

    async def close(self) -> None:
        self._backend.close()


def build_description(
    slam: SlamBackend | None = None,
    objects: ObjectPointSource | None = None,
    stereo: StereoReconstructor | None = None,
    *,
    use_stereo: bool = True,
    detections: DetectionSource | None = None,
    regions: RegionPointSource | None = None,
    moving_areas: bool = True,
    slam_factory: SlamFactory | None = None,
) -> ServerDescription[None]:
    """The CM5 server's description: survey service plus health routes."""
    if stereo is None and use_stereo:
        stereo = StereoReconstructor()
    slam_label = (
        "streaming"
        if isinstance(slam, StreamingRtabmapBackend)
        else "sidecar"
        if isinstance(slam, SidecarRtabmapBackend)
        else "inmemory"
    )
    closeables: tuple[Closeable, ...] = (_BackendCloseable(slam),) if slam is not None else ()
    return ServerDescription(
        services=(
            cm5_service_module(
                slam,
                objects,
                stereo,
                detections,
                regions,
                moving_areas=moving_areas,
                slam_label=slam_label,
                slam_factory=slam_factory,
            ),
        ),
        http_routes=health_routes(lambda: False),
        closeables=lambda _ctx: closeables,
    )


def coral_source(
    model_dir: Path, *, model: str = DEFAULT_PROFILE, use_edgetpu: bool = False
) -> CoralDetectionSource:
    """The Coral detector+tracker for the detections stream.

    `model_dir` is prepared by `scripts/fetch_coral_model.py`; `model`
    is a profile from `surmap.detection.MODEL_PROFILES`. The Edge TPU
    artifact needs the delegate library on a Coral board; everywhere
    else the CPU twin of the same network is used.
    """
    profile = MODEL_PROFILES[model]
    detector = CoralDetector(
        model_dir / profile.file_for(use_edgetpu=use_edgetpu),
        model_dir / "coco_labels.txt",
        edgetpu_delegate="libedgetpu.so.1" if use_edgetpu else None,
    )
    return CoralDetectionSource(detector)


def sidecar_backend(
    calibration_dir: Path,
    image: str = PINNED_RTABMAP_IMAGE,
    shared_container: str | None = None,
) -> SidecarRtabmapBackend:
    """The RTAB-Map sidecar backend calibrated from a EuRoC dataset dir.

    `shared_container` (or the `SURMAP_RTABMAP_SHARED_CONTAINER`
    environment variable when it is `None`) borrows a reusable
    already-running container instead of starting owned ones; a
    shared container is never stopped or removed by the backend.
    """
    mav0 = calibration_dir / "mav0"

    def read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    return SidecarRtabmapBackend(
        cam0_yaml=read(mav0 / "cam0" / "sensor.yaml"),
        cam1_yaml=read(mav0 / "cam1" / "sensor.yaml"),
        imu_yaml=read(mav0 / "imu0" / "sensor.yaml"),
        imu_csv=read(mav0 / "imu0" / "data.csv"),
        image=image,
        shared_container=shared_container,
    )


def streaming_backend(
    calibration_dir: Path,
    frame_size: tuple[int, int] = (376, 240),
    *,
    region_buffer_s: float = 10.0,
    process_factory: Callable[[list[str]], StreamProcess] | None = None,
    native_binary: Path | None = None,
) -> StreamingRtabmapBackend:
    """The live RTAB-Map sidecar calibrated from a EuRoC dataset dir.

    It is both the CM5's `SlamBackend` (poses while streaming) and its
    `RegionPointSource`; frames stay queryable for `region_buffer_s`.
    """
    mav0 = calibration_dir / "mav0"
    width, height = frame_size

    def camera(name: str) -> str:
        return scaled_sensor_yaml(
            (mav0 / name / "sensor.yaml").read_text(encoding="utf-8"), width, height
        )

    return StreamingRtabmapBackend(
        cam0_yaml=camera("cam0"),
        cam1_yaml=camera("cam1"),
        width=width,
        height=height,
        region_buffer_s=region_buffer_s,
        process_factory=process_factory,
        native_binary=native_binary,
    )


def _frame_size(text: str) -> tuple[int, int]:
    width, _, height = text.partition("x")
    try:
        return int(width), int(height)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {text!r}") from exc


async def serve(host: str, port: int, description: ServerDescription[None] | None = None) -> None:
    """Serve the CM5 description until cancelled; always stop the host."""
    server = HypercornHost(description or build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def build_parser() -> argparse.ArgumentParser:
    """The CM5 process command line.

    Only the SLAM backend and the Coral detector are core: every
    other computation (object tracking, moving areas, region points)
    is off unless its flag enables it.
    """
    parser = argparse.ArgumentParser(prog="surmap.survey.cm5_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--slam-backend", choices=("inmemory", "sidecar", "streaming"), default="inmemory"
    )
    parser.add_argument(
        "--calibration-dir",
        type=Path,
        default=None,
        help="EuRoC dataset dir holding mav0/{cam0,cam1,imu0} for the sidecar backend",
    )
    parser.add_argument("--rtabmap-image", default=PINNED_RTABMAP_IMAGE)
    parser.add_argument(
        "--frame-size",
        type=_frame_size,
        default=(376, 240),
        help="WIDTHxHEIGHT the streaming sidecar works at (default 376x240)",
    )
    parser.add_argument(
        "--region-buffer-s",
        type=float,
        default=10.0,
        help="how long frames stay queryable for StreamRegionPoints (streaming backend)",
    )
    parser.add_argument(
        "--rtabmap-shared-container",
        default=None,
        help="borrow this reusable RTAB-Map container instead of starting owned ones "
        "(default: $SURMAP_RTABMAP_SHARED_CONTAINER; never stopped or removed)",
    )
    parser.add_argument(
        "--rtabmap-native",
        type=Path,
        default=None,
        help="run this natively built surmap-rtabmap-stream binary directly "
        "(system RTAB-Map, no Docker; build: scripts/build_rtabmap_native.sh)",
    )
    parser.add_argument("--detector", choices=("none", "coral"), default="none")
    parser.add_argument(
        "--coral-model",
        choices=sorted(MODEL_PROFILES),
        default=DEFAULT_PROFILE,
        help="detector model profile (see surmap.detection.MODEL_PROFILES)",
    )
    parser.add_argument(
        "--coral-model-dir",
        type=Path,
        default=None,
        help="model dir prepared by scripts/fetch_coral_model.py",
    )
    parser.add_argument(
        "--coral-edgetpu",
        action="store_true",
        help="use the Edge-TPU artifact + delegate (needs a Coral board)",
    )
    parser.add_argument(
        "--object-tracking",
        action="store_true",
        help="enable object tracking: lift Coral-tracked objects' stereo "
        "points into the survey object layer (default: off)",
    )
    parser.add_argument(
        "--moving-areas",
        action="store_true",
        help="enable the StreamMovingAreas computation (default: off)",
    )
    parser.add_argument(
        "--region-points",
        action="store_true",
        help="enable the StreamRegionPoints dense-stereo computation (default: off)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port`/`--slam-backend` and serve until signalled."""
    parser = build_parser()
    args = parser.parse_args(argv)
    detections: DetectionSource | None = None
    objects: ObjectPointSource | None = None
    if args.detector == "coral":
        if args.coral_model_dir is None:
            parser.error("--detector coral requires --coral-model-dir")
        detections = coral_source(
            args.coral_model_dir, model=args.coral_model, use_edgetpu=args.coral_edgetpu
        )
        if args.object_tracking:
            # The same detector+tracker lifts object points on
            # StreamSurvey; its rig arrives with each stream's config.
            objects = CoralObjectPointSource(detections, StereoReconstructor())
    description = None
    if args.slam_backend == "sidecar":
        if args.calibration_dir is None:
            parser.error("--slam-backend sidecar requires --calibration-dir")
        description = build_description(
            slam=sidecar_backend(
                args.calibration_dir, args.rtabmap_image, args.rtabmap_shared_container
            ),
            objects=objects,
            use_stereo=False,
            detections=detections,
            moving_areas=args.moving_areas,
        )
    elif args.slam_backend == "streaming":
        if args.calibration_dir is None:
            parser.error("--slam-backend streaming requires --calibration-dir")
        live = streaming_backend(
            args.calibration_dir,
            args.frame_size,
            region_buffer_s=args.region_buffer_s,
            native_binary=args.rtabmap_native,
        )

        def stream_slam_factory(
            config: survey_pb2.Cm5StreamConfig,
        ) -> StreamingRtabmapBackend | None:
            # A stream that brings its own camera definitions (e.g.
            # the demo playing another dataset) gets a backend
            # calibrated for it, closed with the stream; a stream
            # without them runs on the configured backend above.
            if not (config.cam0_yaml and config.cam1_yaml):
                return None
            calibration = config.calibration
            return StreamingRtabmapBackend(
                cam0_yaml=config.cam0_yaml,
                cam1_yaml=config.cam1_yaml,
                width=calibration.width or args.frame_size[0],
                height=calibration.height or args.frame_size[1],
                max_depth_m=config.max_depth_m or 6.0,
                region_buffer_s=args.region_buffer_s,
                native_binary=args.rtabmap_native,
            )

        description = build_description(
            slam=live,
            objects=objects,
            use_stereo=False,
            detections=detections,
            regions=live if args.region_points else None,
            moving_areas=args.moving_areas,
            slam_factory=stream_slam_factory,
        )
    elif detections is not None:
        description = build_description(
            objects=objects, detections=detections, moving_areas=args.moving_areas
        )
    if description is None and not args.moving_areas:
        description = build_description(moving_areas=False)
    try:
        asyncio.run(serve(args.host, args.port, description))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
