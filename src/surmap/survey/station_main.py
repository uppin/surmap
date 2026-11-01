"""Station server process: `python -m surmap.survey.station_main`.

Mounts `StationSamService` plus health routes on a real socket. The
default detector is the in-memory one (no detections); with
`--detector sam3` the SAM 3.1 ONNX adapter serves (CUDA provider on
the station GPU), and with `--detector sam31-torch` Meta's SAM 3.1
PyTorch image model serves on the named GPU:

    python -m surmap.survey.station_main --detector sam31-torch \
        --sam31-model /models/facebook--sam3.1 --sam31-device cuda:0
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.routes import health_routes
from surmap.survey.sam import SamDetector
from surmap.survey.sam3 import sam3_detector
from surmap.survey.sam3_torch import DEFAULT_SAM31_MODEL, sam31_torch_detector
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


async def serve(host: str, port: int, description: ServerDescription[None] | None = None) -> None:
    """Serve the station description until cancelled; always stop the host."""
    server = HypercornHost(description or build_description(), None, host=host, port=port)
    await server.start()
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def build_parser() -> argparse.ArgumentParser:
    """The station process command line."""
    parser = argparse.ArgumentParser(prog="surmap.survey.station_main")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--detector", choices=("memory", "sam3", "sam31-torch"), default="memory")
    parser.add_argument("--sam3-model", type=Path, default=None, help="SAM 3.1 ONNX export")
    parser.add_argument("--sam3-device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--sam3-label", default="object")
    parser.add_argument(
        "--sam31-model",
        default=DEFAULT_SAM31_MODEL,
        help="SAM 3.1 checkpoint: HF id, local .pt, or local directory",
    )
    parser.add_argument("--sam31-device", default="cuda:0")
    parser.add_argument("--sam31-label", default="object", help="concept prompt per frame")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse `--host`/`--port`/`--detector` and serve until signalled."""
    parser = build_parser()
    args = parser.parse_args(argv)
    description = None
    if args.detector == "sam3":
        if args.sam3_model is None:
            parser.error("--detector sam3 requires --sam3-model")
        description = build_description(
            detector=sam3_detector(args.sam3_model, device=args.sam3_device, label=args.sam3_label)
        )
    elif args.detector == "sam31-torch":
        description = build_description(
            detector=sam31_torch_detector(
                args.sam31_model, device=args.sam31_device, prompt=args.sam31_label
            )
        )
    try:
        asyncio.run(serve(args.host, args.port, description))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
