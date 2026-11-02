# SAM 3.1 on Apple's GPU (MPS) for the local demo

**Date:** 2026-11-02
**Feature:** Browser demo / SAM 3.1 adapter

`--sam-device mps` runs Meta's SAM 3.1 locally on an Apple-silicon GPU,
so a Mac can record runs with real SAM masks (for example a replay
journal to tune segmentation against) without a CUDA station.

- `parse_sam_device` accepts `mps`. `sam31_torch_detector(device="mps")`
  builds the image model on CPU, moves it to MPS, and runs it under bf16
  autocast, as on CUDA.
- `surmap.survey.sam3_mps.prepare_sam3_for_mps` contains the vendor's
  CUDA-only corners, only inside the `sam3` package:
  - `sam3.model.edt` imports `triton`, which macOS lacks. A stand-in
    that fails by name replaces it; `edt_triton` only samples clicks for
    interactive refinement.
  - Each vendor module's `torch` is swapped for `OnDevice`, which reads
    an explicit `"cuda"` device (tensors, `torch.device`, autocast) as
    `mps`.
  - `aten::_addmm_activation` has no MPS kernel. `sam3.perflib.fused`
    gets the same addmm followed by exact GELU / ReLU, identical to the
    fused op on CPU.
- `Sam31TorchVideoDetector` turns the per-frame image model into a
  `VideoSamDetector`, with ids by box overlap. `BoxTracks` is extracted
  from the ONNX `Sam3VideoDetector`, which now uses it too.
- The demo builds it for `--sam-device mps`. The multiplex video model
  stays CUDA-only: it queries CUDA as it is imported.

Verification: gates green (ruff, format, mypy strict; pytest 1068
passed). `tests/test_sam31_mps_e2e.py` (skipped without torch, sam3,
MPS or the weights) finds the cars of a KITTI 0009 frame on the GPU,
about 2.4 s a frame on an M-series Mac. A full recording of KITTI 0009
used it: 447 frames, real streaming sidecar, 4,024 car masks, every
region answered, at `--fps 0.35` in 21.5 min. Its journal replays in
about 2 min.
