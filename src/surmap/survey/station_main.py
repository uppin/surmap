"""Station server process: `python -m surmap.survey.station_main`.

Mounts `StationSamService` plus health routes on a real socket. The
default detector is the in-memory one (no detections); with
`--detector sam3` the real SAM 3.1 adapter serves, running through
ONNX Runtime — CUDA provider on the station GPU, CPU elsewhere:

    python -m surmap.survey.station_main --detector sam3 \
        --sam3-model /models/sam3.1.onnx --sam3-device cuda

`--detector sam3-modal`, or `--detector sam3 --sam3-device modal`,
posts JPEG bytes and a text prompt to `MODAL_SAM_URL`. Deploy,
stop, and the checkpoint steps are in `docs/modal.md`.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.survey.modal_sam import ModalSamDetector, modal_sam_detector
from surmap.survey.sam import SamDetector
from surmap.survey.sam3 import Sam3Detector, Sam3Unavailable, sam3_detector
from surmap.survey.station_server import station_service_module

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8081


class StationConfigError(ValueError):
    """Raised when station CLI flags do not name a usable detector."""


def resolve_detector(
    *,
    detector: str,
    device: str,
    model: Path | None,
    label: str = "object",
) -> Sam3Detector | ModalSamDetector | None:
    """The detector for these flags, or ``None`` for the in-memory default.

    Modal does not read a local checkpoint. CPU and CUDA still require
    ``--sam3-model``.
    """
    if detector == "memory":
        if device == "modal":
            raise StationConfigError(
                "--sam3-device modal requires --detector sam3 or --detector sam3-modal"
            )
        return None
    if detector == "sam3-modal" or device == "modal":
        return modal_sam_detector(label=label)
    if model is None:
        raise StationConfigError("--detector sam3 requires --sam3-model")
    return sam3_detector(model, device=device, label=label)


def build_description(
    detector: SamDetector | None = None,
) -> ServerDescription[None]:
    """The station server's description: SAM service plus health routes."""
    return ServerDescription(
        services=(station_service_module(detector),),
        http_routes=health_routes(lambda: False),
    )


async def serve(host: str, port: int, description: ServerDescription[None] | None = None) -> None:
    """Serve the station description until cancelled; always stop the host."""
    server = HypercornHost(description or build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port`/`--detector` and serve until signalled."""
    parser = argparse.ArgumentParser(prog="surmap.survey.station_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--detector", choices=("memory", "sam3", "sam3-modal"), default="memory")
    parser.add_argument("--sam3-model", type=Path, default=None, help="SAM 3.1 ONNX export")
    parser.add_argument("--sam3-device", choices=("auto", "cpu", "cuda", "modal"), default="auto")
    parser.add_argument("--sam3-label", default="object")
    args = parser.parse_args(argv)
    try:
        detector = resolve_detector(
            detector=args.detector,
            device=args.sam3_device,
            model=args.sam3_model,
            label=args.sam3_label,
        )
    except (StationConfigError, Sam3Unavailable) as exc:
        parser.error(str(exc))
    description = None if detector is None else build_description(detector=detector)
    try:
        asyncio.run(serve(args.host, args.port, description))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
