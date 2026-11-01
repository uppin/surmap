# RTAB-Map demo: real SAM 3.1 video segmentation on GPU, separate pane

**Date:** 2026-10-31
**Feature:** browser demo

The RTAB-Map run page (`scripts/demo.py`) gained an optional SAM
mode: `--sam-device cuda:0` runs SAM in continuous (video) mode on
that GPU and shows its detections. The device argument is the whole
switch — without it no SAM runs and playback is unchanged.
`--sam-model` overrides the model (an HF id, a local SAM 3.1 `.pt`,
or an `.onnx` export) and `--sam-label` is the concept prompt (`car`
on KITTI). The default model is the real `facebook/sam3.1`
(multiplex checkpoint, ~3.5 GB, downloaded with `HF_TOKEN` from the
project `.env`).

The checkpoint is Meta's native PyTorch format, so it cannot use
the ONNX session; `survey/sam3_torch.py` runs Meta's official
`sam3` multiplex video model behind the new `VideoSamStreamer`
port (`survey/sam.py`, with an in-memory adapter). The vendor
session is driven at model level (`init_state` / `add_prompt` /
`propagate_in_video` — the package's `handle_request` wrapper
passes a kwarg the multiplex model rejects), prompted once per
window, and its `out_*` arrays are converted at the edge: SAM's
object id is the track id, the (normalised, despite the `xywh`
name) boxes are scaled to frame pixels, binary masks become
outline polygons. Propagation runs in 16-frame windows with the
video offloaded to CPU, so a long stream fits a 16 GB card
(measured ~7–10 GB alongside RTAB-Map); object ids restart per
window. A per-frame ONNX path (`Sam3VideoDetector`, IoU-carried
ids) still serves `.onnx` exports behind `VideoSamDetector`.

SAM runs in a separate preview pane below the main pane, at its
own rate — the two are deliberately decoupled. `sam` SSE events are
released as results arrive, each carrying its own frame's JPEG
(256-frame cache in `_Display`), and the pane draws image + masks
whenever one lands; the main preview is never delayed by SAM (an
earlier frame-hold design made the preview lag or sit black, and
is gone). Superseded viewers' SAM workers cancel at the next
frame; stacked GPU sessions previously OOM'd the card. Prompting
and propagation run under bf16 autocast on the worker thread (the
vendor predictor's constructing-thread context does not reach it;
the mismatch was a real dtype-crash).

Also in this change: `.env` support (`surmap/env.py`,
dependency-free loader; shell always wins, values never logged)
wired into the launcher, `.env` git-ignored with an
`.env.example`. The history recorder initially treated `sam`
events as frames and killed the stream on their missing keys;
it now attaches the image payload for `sam` and persists only
`frame` events.

Verification: gates green (ruff, format, mypy strict, pytest
637 passed / 2 skipped). Live on the RTX 5060 Ti: KITTI stream
with prompt `car` produced 64/64 non-empty SAM events (538 car
detections, 0.73–0.89, persistent ids) in a 90 s probe, and after
the pane split 150 main-frame events vs 16 SAM events (all with
images) in 55 s. EuRoC yields no detections for the prompts tried
(grayscale, no clear concept instances); the model itself scores
0.98 on a colour car photo.
