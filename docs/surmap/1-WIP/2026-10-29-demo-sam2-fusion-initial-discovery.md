# Initial discovery — SAM 2.1 + RTAB-Map demo

## Conclusions

- **SAM 3 and SAM 3.1 are blocked for now.** `facebook/sam3` and
  `facebook/sam3.1` are gated on Hugging Face. On 2026-10-29 the
  developer's account (`mantasindrasius`) was logged in, but downloads
  failed with "Cannot access gated repo" while the access request was
  under review. `facebookresearch/sam3` on GitHub ships code only
  (weights come from the gated repos) and requires CUDA.
- **SAM 2.1 needs no approval.** `facebook/sam2.1-hiera-small` downloads
  without approval (`config.json` OK). It is Apache-2.0, 46M params,
  with a 184 MB `model.safetensors`. It takes box prompts but has no text
  prompts, which fits the Coral boxes the demo already has
  (`architecture.md` §3.1: Coral detections steer SAM).
- **The ONNX export works** (spike, tooling-only env with
  `torch 2.15`, `transformers 5.22`, `torchvision`, `onnx`,
  `onnxscript`). `Sam2Model.get_image_embeddings(pixel_values[1,3,1024,1024])`
  returns three embeddings, `[1,32,256,256]`, `[1,64,128,128]` and
  `[1,256,64,64]`. `Sam2Model(image_embeddings=[…], input_boxes=[1,N,4],
  multimask_output=False)` returns `pred_masks [1,N,1,256,256]` (logits)
  and `iou_scores [1,N,1]`. Exported as two graphs, encoder 138 MB and
  decoder 16.5 MB, with a dynamic box count. ONNX matches torch with max
  mask-logit diff `2.9e-5`. CPU timings on the dev Mac: encoder about
  1.2 s per frame, decoder about 0.08 s for 3 boxes.
- **Mac GPU (Metal).** ONNX Runtime 1.31.1's macOS wheel ships
  `CoreMLExecutionProvider`. Encoder times per frame: CPU 1,009 ms,
  CoreML `CPUAndGPU` 337 ms, `ALL` 491 ms, `CPUAndNeuralEngine`
  652 ms, with max diff vs CPU `3e-5`. CoreML compiles the graph on
  first load (45 s), then about 12 s with `ModelCacheDirectory`. The
  decoder fails to compile under CoreML (unbounded dynamic box
  dimension), so it stays on the CPU (about 80 ms).
- **Preprocessing** (`Sam2ImageProcessor`): plain resize to 1024×1024
  (bilinear, aspect not kept), `/255`, ImageNet mean `[0.485,0.456,0.406]`
  and std `[0.229,0.224,0.225]`. Boxes are scaled per axis into the
  1024 input space.
- **Batch RTAB-Map** over 200 demo frames (index 1000+) took 11.8 s to
  flush and exported 10 poses, one keyframe per 20 frames (about 1 Hz).
  The full 2,912-pair run is therefore about 145 keyframes. The
  assembled cloud had 23,439 points.
- **Camera→pose frame.** RTAB-Map poses are base frame (x forward,
  z up). Demo stereo points are optical camera frame (z forward). The
  transform is `B · T_BS(cam0)` with `B = [[0,0,1],[0,-1,0],[1,0,0]]`
  (RTAB-Map's EuRoC base←IMU rotation), which is about the plain
  optical→base rotation. Placing keyframe stereo points with it gave a
  median nearest-cloud distance of 0.58 m. Identity gave 1.74 m and
  `T_BS` alone 1.81 m. The residual is the demo's coarse stereo
  (unrectified half-res block matching).
- **Pre-existing finding, not fixed here.** `cm5_server.py` places
  stereo points with `to_map_frame(point, result.pose)` directly, with
  no camera→base transform. Under the sidecar's base-frame poses this
  is the "identity" row above.
- `todo/` cross-check: none of the six `src/surmap/docs/todo/` records
  are on this path.

## Explore

- `src/surmap/survey/sam3.py`: the ONNX Runtime adapter pattern
  (typed `Protocol` session, `_mask_outline`) to mirror for SAM 2.
- `src/surmap/demo/server.py`: `DemoPlayer.events` (pacing loop,
  `detections` event, batch flush, `final` event) and the page.
- `src/surmap/detection/source.py`: `CoralDetectionSource.detect_tracked`
  returns `TrackedDetection(label, score, box_xyxy, track_id, frame_id)`.
- `src/surmap/geometry.py`: `to_map_frame` (reused for both hops).
- `scripts/make_fake_sam3_model.py`: the tooling-only dependency
  pattern (`uv run --with …`).
