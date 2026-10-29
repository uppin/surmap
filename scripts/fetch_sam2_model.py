#!/usr/bin/env python3
"""Fetch SAM 2.1 and export it to the two-graph ONNX contract.

SAM 2.1 hiera-small (`facebook/sam2.1-hiera-small`, Apache-2.0, not
gated) stands in for SAM 3 until the gated SAM 3 checkpoints are
granted. This script downloads the pinned revision, exports the image
encoder and the box-prompted mask decoder to ONNX (the contract in
`surmap.survey.sam2`), checks the ONNX outputs against PyTorch, and
writes a `manifest.json`. Output lands outside the repo:

    uv run --no-project --with torch --with torchvision --with transformers \\
        --with onnx --with onnxscript --with onnxruntime --with pillow \\
        python scripts/fetch_sam2_model.py

Default output: `$SURMAP_SAM2_MODEL_DIR`, else
`~/.cache/surmap/sam2/sam2.1-hiera-small`. The export dependencies
are tooling-only (passed with `--with`), never project dependencies;
the demo then needs only `onnxruntime`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = "facebook/sam2.1-hiera-small"
REVISION = "ee5bba1d82bb8749febdf90f45e84b687142ba03"
DEFAULT_OUTPUT = Path(
    os.environ.get("SURMAP_SAM2_MODEL_DIR", "")
    or Path.home() / ".cache" / "surmap" / "sam2" / "sam2.1-hiera-small"
)
INPUT_SIZE = 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def export(output: Path) -> None:
    import numpy as np
    import onnxruntime as ort
    import torch
    from transformers import Sam2Model, Sam2Processor

    output.mkdir(parents=True, exist_ok=True)
    print(f"loading {REPO}@{REVISION[:12]}")
    model = Sam2Model.from_pretrained(REPO, revision=REVISION).eval()
    processor: Any = Sam2Processor.from_pretrained(REPO, revision=REVISION).image_processor

    class Encoder(torch.nn.Module):
        def __init__(self, sam: Any) -> None:
            super().__init__()
            self.sam = sam

        def forward(self, pixel_values: Any) -> tuple[Any, ...]:
            return tuple(self.sam.get_image_embeddings(pixel_values))

    class Decoder(torch.nn.Module):
        def __init__(self, sam: Any) -> None:
            super().__init__()
            self.sam = sam

        def forward(self, emb0: Any, emb1: Any, emb2: Any, boxes: Any) -> tuple[Any, Any]:
            result = self.sam(
                image_embeddings=[emb0, emb1, emb2], input_boxes=boxes, multimask_output=False
            )
            return result.pred_masks, result.iou_scores

    generator = torch.Generator().manual_seed(0)
    pixel_values = torch.rand((1, 3, INPUT_SIZE, INPUT_SIZE), generator=generator)
    boxes = torch.tensor([[[100.0, 200.0, 800.0, 900.0]]])
    with torch.no_grad():
        embeddings = Encoder(model)(pixel_values)
        torch_masks, _scores = Decoder(model)(*embeddings, boxes)
        print("exporting encoder")
        torch.onnx.export(
            Encoder(model),
            (pixel_values,),
            output / "sam2_encoder.onnx",
            input_names=["pixel_values"],
            output_names=["emb0", "emb1", "emb2"],
            opset_version=17,
            dynamo=False,
        )
        print("exporting decoder")
        torch.onnx.export(
            Decoder(model),
            (*embeddings, boxes),
            output / "sam2_decoder.onnx",
            input_names=["emb0", "emb1", "emb2", "boxes"],
            output_names=["masks", "iou_scores"],
            dynamic_axes={"boxes": {1: "n"}, "masks": {1: "n"}, "iou_scores": {1: "n"}},
            opset_version=17,
            dynamo=False,
        )

    encoder = ort.InferenceSession(str(output / "sam2_encoder.onnx"))
    decoder = ort.InferenceSession(str(output / "sam2_decoder.onnx"))
    onnx_embeddings = encoder.run(None, {"pixel_values": pixel_values.numpy()})
    onnx_masks = decoder.run(
        None,
        {
            "emb0": onnx_embeddings[0],
            "emb1": onnx_embeddings[1],
            "emb2": onnx_embeddings[2],
            "boxes": boxes.numpy(),
        },
    )[0]
    drift = float(np.abs(onnx_masks - torch_masks.numpy()).max())
    if drift > 1e-2:
        raise SystemExit(f"ONNX export drifts from PyTorch: max mask-logit diff {drift}")
    print(f"ONNX matches PyTorch (max mask-logit diff {drift:.2e})")

    manifest = {
        "model": REPO,
        "revision": REVISION,
        "input_size": INPUT_SIZE,
        "mask_size": int(torch_masks.shape[-1]),
        "mean": [float(value) for value in processor.image_mean],
        "std": [float(value) for value in processor.image_std],
        "encoder": "sam2_encoder.onnx",
        "decoder": "sam2_decoder.onnx",
        "sha256": {
            name: _sha256(output / name) for name in ("sam2_encoder.onnx", "sam2_decoder.onnx")
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"SAM 2.1 model exported under {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        export(args.output)
    except ImportError as exc:
        print(
            f"missing export tooling ({exc.name}); run with the --with flags in this "
            "script's docstring",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
