#!/usr/bin/env python3
"""Generate the tiny fake SAM3 ONNX model used by station tests.

The fake is a real ONNX graph executed by the same ONNX Runtime
session code as the production SAM 3.1 model — only the weights are
fake. It segments "brighter than mid-grey" regions: masks are a
sigmoid over the mean channel intensity, and each mask's score is
its mean probability. That makes the station's SAM3 adapter fully
exercisable on CPU in tests, through the exact runtime the station
GPU uses (CUDA provider there, CPU provider here).

Requires the `onnx` package, which is tooling-only:

    uv run --with onnx python scripts/make_fake_sam3_model.py

Output: tests/fixtures/sam3_fake/fake_sam3.onnx (committed; CI does
not need `onnx` installed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "sam3_fake" / "fake_sam3.onnx"
INPUT_SIZE = 256


def build(output: Path) -> Path:
    import onnx
    from onnx import TensorProto, helper

    image = helper.make_tensor_value_info(
        "image", TensorProto.FLOAT, [1, 3, INPUT_SIZE, INPUT_SIZE]
    )
    masks = helper.make_tensor_value_info(
        "masks", TensorProto.FLOAT, [1, 1, INPUT_SIZE, INPUT_SIZE]
    )
    scores = helper.make_tensor_value_info("scores", TensorProto.FLOAT, [1, 1])
    nodes = [
        helper.make_node("ReduceMean", ["image"], ["gray"], axes=[1], keepdims=1),
        helper.make_node("Sub", ["gray", "mid"], ["centred"]),
        helper.make_node("Mul", ["centred", "gain"], ["logits"]),
        helper.make_node("Sigmoid", ["logits"], ["masks"]),
        helper.make_node("ReduceMean", ["masks"], ["score4"], axes=[1, 2, 3], keepdims=1),
        helper.make_node("Reshape", ["score4", "score_shape"], ["scores"]),
    ]
    initializers = [
        helper.make_tensor("mid", TensorProto.FLOAT, [1], [0.45]),
        helper.make_tensor("gain", TensorProto.FLOAT, [1], [12.0]),
        helper.make_tensor("score_shape", TensorProto.INT64, [2], [1, 1]),
    ]
    graph = helper.make_graph(nodes, "fake-sam3", [image], [masks, scores], initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(output))
    print(f"fake SAM3 model written to {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    build(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
