#!/usr/bin/env python3
"""Fetch and prepare the Coral object-detection model artifacts.

No Coral runtime or compiler is installed on the host: this script
downloads the two pinned EfficientDet-Lite0 INT8 artifacts (the
Edge-TPU-compiled one for CM5 hardware, the CPU twin for CI/local
proof — see docs/coral-edge-tpu-model-spike.md for why the detector
is Coral-native rather than a Meta model) plus the COCO labels, and
verifies each by size + SHA-256.

Prepared output lands in `tests/fixtures/coral_model/` (git-ignored):

    uv run python scripts/fetch_coral_model.py
    SURMAP_REQUIRE_CORAL_E2E=1 uv run pytest tests/test_survey_cm5_coral_e2e.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "coral_model"
BASE_URL = "https://raw.githubusercontent.com/google-coral/test_data/master"

# (filename, size, sha256) — pinned; the hash, not the host, is trusted.
# Covers every profile in surmap.detection.profiles.MODEL_PROFILES.
ARTIFACTS = (
    (
        "efficientdet_lite0_320_ptq_edgetpu.tflite",
        5_958_680,
        "4b17288c7988973274c63e10c914748363e7795ba715c6d8d7db1a2b909744a5",
    ),
    (
        "efficientdet_lite0_320_ptq.tflite",
        4_561_184,
        "33a3b622c7cac0762f96089353cd61495f3e993968d133af7871bfc2d5396704",
    ),
    (
        "ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite",
        6_911_677,
        "b94e2d58222c32f31062c7604e10488e2aba9259ab77462039476a3ba4597fef",
    ),
    (
        "ssd_mobilenet_v2_coco_quant_postprocess.tflite",
        6_220_797,
        "42fb3d70ffb7bb37dd518f730f7be784b831c2078f30c497d0019cc2e987fa26",
    ),
    (
        "ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite",
        5_395_936,
        "b69e508ef2a670e06b80bd3e5559a827d5cd8d557c95d5e332cbf1d31d434a2e",
    ),
    (
        "ssdlite_mobiledet_coco_qat_postprocess.tflite",
        4_330_856,
        "32c486140391eb4dc43fca7113ad392be632dc5366687f2731f73d740678693f",
    ),
    ("coco_labels.txt", 661, "dc183f003fc753c4c43fae6fdf7f387559449573f13fa32e517fb7453fd380f1"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    files = []
    for name, size, sha256 in ARTIFACTS:
        target = output / name
        if not (target.is_file() and target.stat().st_size == size and _sha256(target) == sha256):
            print(f"downloading {name} ({size / 1e6:.2f} MB)")
            with urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=120) as response:
                target.write_bytes(response.read())
        if target.stat().st_size != size or _sha256(target) != sha256:
            raise ValueError(f"{name} failed size/SHA-256 verification; refusing to use it")
        files.append({"file": name, "size_bytes": size, "sha256": sha256})
    manifest = {
        "model": "EfficientDet-Lite0 INT8 (COCO), Coral test_data artifacts",
        "spike": "docs/coral-edge-tpu-model-spike.md",
        "input": "320x320 uint8 RGB",
        "files": files,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Coral detection model prepared under {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    prepare(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
