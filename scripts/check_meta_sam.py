#!/usr/bin/env python3
"""Send one image to Meta SAM 3.1 and save the response JSON.

The request is sent only when both ``SURMAP_LIVE_META=1`` and
``MODEL_API_KEY`` are set. Detections are printed. The response body
is written to ``tmp/meta-sam-last-response.json`` (gitignored). The
API key is never printed, and it is replaced in that file if it
appears.

WSL, from the repository root:

    SURMAP_LIVE_META=1 MODEL_API_KEY='paste-key-here' uv run python scripts/check_meta_sam.py
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

from PIL import Image

from surmap.survey.meta_sam import DEFAULT_MODEL, MetaSamError, probe_sam
from surmap.survey.sam import RawFrame, SamDetection

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = REPO_ROOT / "scripts" / "fixtures" / "meta_sam_check.png"
DEFAULT_OUTPUT = REPO_ROOT / "tmp" / "meta-sam-last-response.json"


def frame_from_image(path: Path) -> RawFrame:
    """Load one image file as a jpeg frame the detector can post."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=90)
    return RawFrame(1, 0, 0, width, height, "mjpeg", buffer.getvalue())


def format_detection(detection: SamDetection) -> str:
    return (
        f"{detection.label} score={'none' if detection.score is None else detection.score} "
        f"box={detection.box_xyxy} "
        f"points={len(detection.mask_polygon)} track_id={detection.track_id}"
    )


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("SURMAP_LIVE_META") != "1" or not os.environ.get("MODEL_API_KEY"):
        print(
            "Refusing to call Meta. Set SURMAP_LIVE_META=1 and MODEL_API_KEY.",
            file=sys.stderr,
        )
        return 2
    parser = argparse.ArgumentParser(description="Send one image to Meta SAM 3.1")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--prompt", default="person")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    key = os.environ["MODEL_API_KEY"]
    try:
        detections = probe_sam(
            frame_from_image(args.image),
            prompt=args.prompt,
            output_path=args.output,
            api_key=key,
            model=args.model,
        )
    except MetaSamError as exc:
        message = str(exc).replace(key, "[redacted]")
        print(message, file=sys.stderr)
        return 1
    if not detections:
        print("no detections")
    for detection in detections:
        print(format_detection(detection))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
