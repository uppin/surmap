# Coral Edge TPU model spike — Meta first, honestly

**Date:** 2026-10-27
**Question:** can a small Meta model do object detection + tracking on
the Coral Edge TPU (M.2 2230; ~8 MB on-chip SRAM for cached parameters,
INT8 TFLite models compiled by the Edge TPU compiler), the way
RTAB-Map runs as a pinned sidecar?

## What was checked

- **Meta's own SAM line** (`facebook/sam-vit-*`, SAM 2 hiera): the
  smallest Meta checkpoint is ViT-B class — hundreds of MB in FP32,
  ~90 MB+ in INT8. Two orders of magnitude over the parameter cache,
  transformer-heavy (attention/LayerNorm/GELU ops are the known-hard
  set for the Edge TPU compiler), and — decisively — SAM is a
  *promptable segmenter*, not a detector: it produces no labels or
  boxes without a separate proposal + classification stage. It cannot
  fill a detection stream on its own.
- **MobileSAM** (the usual "small SAM"): not a Meta model (Zhang et
  al., distilled from SAM), ~9.7 M parameters → ~10 MB INT8, still
  over the 8 MB cache; TinyViT encoder has the same transformer op
  problem; no Edge-TPU-compiled artifact is published anywhere we
  could find (checked Hugging Face artifact listings: PyTorch and
  partial ONNX exports only, no TFLite, no `_edgetpu`); and it keeps
  SAM's prompt-based interface, so the detector problem above stands.
- **Meta detectors** (DETR/Mask2Former families): smallest published
  variants are ~40 M+ parameters of transformer architecture. No
  INT8 TFLite export, no Edge TPU artifact, same op-set risk.

**Spike verdict:** within a bounded attempt there is no Meta(-family)
model that can be honestly claimed to run compiled on the Edge TPU
as our detector. Pursuing a PyTorch→ONNX→TFLite→`edgetpu_compiler`
conversion of a transformer segmenter would be a research project
with an unproven op-coverage outcome, and its output would still not
be detections.

## Fallback taken (recorded deviation from Meta-first)

Google's Coral-native **EfficientDet-Lite0** INT8, from the official
`google-coral/test_data` artifacts:

| Artifact | Bytes | SHA-256 | Role |
|---|---|---|---|
| `efficientdet_lite0_320_ptq_edgetpu.tflite` | 5,958,680 | `4b17288c…44a5` | on-device (Edge-TPU-compiled; fits the 8 MB cache) |
| `efficientdet_lite0_320_ptq.tflite` | 4,561,184 | `33a3b622…6704` | CPU twin — same model for CI/local proof |
| `coco_labels.txt` | 661 | — | 90 COCO labels (incl. background handling as published) |

The `_edgetpu` artifact contains `edgetpu-custom-op` and cannot run
without the Edge TPU delegate — verified locally: LiteRT refuses it
on CPU with "unresolved custom op: edgetpu-custom-op". The CPU twin
runs the identical network via LiteRT on CPU, which is how E2Es
prove real detections without a board; on CM5 hardware the same
backend loads the `_edgetpu` artifact with the Edge TPU delegate.
Tracking is not a neural model at all: a small CPU IoU tracker
(`surmap.detection.IouTracker`) assigns persistent track IDs.

If a future Meta model ships an Edge-TPU-compilable INT8 artifact,
the swap is one fetched model behind the same
`surmap.detection` port — the Meta-first policy is deferred by
evidence, not abandoned.
