"""One call to the deployed SAM 3.1 Modal endpoint.

Reads ``MODAL_SAM_URL``. Posts the bundled JPEG with the prompt
``person`` and prints detections plus GPU seconds. No token is read
from disk beyond what the environment already has.
"""

from __future__ import annotations

import sys
from pathlib import Path

from surmap.survey.modal_sam import CHECK_IMAGE, run_modal_sam_check
from surmap.survey.sam3 import Sam3Unavailable


def bundled_image() -> Path:
    """The JPEG committed next to the tests, resolved from the repo root."""
    return Path(__file__).resolve().parents[1] / CHECK_IMAGE


def main() -> int:
    """Post the bundled image. Exit 2 when the URL is unset."""
    try:
        image = bundled_image().read_bytes()
        run_modal_sam_check(image, prompt="person")
    except Sam3Unavailable as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
