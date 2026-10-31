# Initial discovery: demo SAM prompt on the page, per-scene default

**Date**: 2026-10-31

## Where the prompt lives today

- `scripts/demo.py` — `--sam-label` (default `"object"`) is passed to
  `make_demo_server(sam_label=...)`. It is the single concept prompt for
  every scene and every run of the server's lifetime.
- `src/surmap/demo/server.py` `make_demo_server` — the label is baked into
  the SAM adapter at construction:
  - real SAM 3.1 (`sam31_video_streamer(..., prompt=sam_label)`),
  - ONNX export (`sam3_video_detector(..., label=sam_label)`) — the export's
    concept is fixed at export time; `label` only names its detections,
  - `--sam-fake` (`CentredBoxVideoSamDetector(sam_label)`).
  `server.sam_label` is stored but not used by the page.
- `src/surmap/survey/sam3_torch.py` `Sam31VideoStreamer` — `self._prompt` is
  sent with `add_prompt(state, 0, text_str=...)` once per 16-frame window and
  is the label of every detection.
- `src/surmap/survey/sam.py` — ports `VideoSamDetector` (`reset`, `track`,
  `close`) and `VideoSamStreamer` (`stream(frame_paths)`, `close`); neither
  takes a prompt.
- `DemoPlayer.events()` calls `sam_source.reset()` per playback, or builds a
  `_SamStreamWorker` that calls `streamer.stream(paths)` per playback.

## Scenes

`src/surmap/demo/datasets.py` `DatasetSpec` holds per-scene tuning (display
size, fps, depth stops, credit). Scenes are chosen on the page at runtime
(`/?dataset=<id>`), so a per-scene default must live on the spec, not on the
launcher. Scenes: EuRoC V1_01 (indoor Vicon room), KITTI 0009 (city street),
NTU VIRAL sbs_01 (drone over a campus plaza).

## Page

`src/surmap/demo/page.py` — server-rendered per scene; `openStream()` opens
`/stream?dataset=<id>`; Restart is `location.reload()`; switching scene
navigates to `/?dataset=<id>`. The SAM pane is spliced in only when SAM is
enabled (`sam_pane`).

## Tests touching this

`tests/test_demo.py` — `test_the_page_shows_sam_masks_when_sam_is_enabled`,
`test_sam_streamer_events_arrive_for_each_frame_in_order`,
`test_sam_video_events_arrive_for_each_frame_in_order`;
`tests/test_sam31_torch.py` (streamer with a fake model);
`tests/test_sam_video.py` (ONNX video detector).

## Deferred-work cross-check

`src/surmap/docs/code-issues/` records `demo/server.py` and `demo/page.py`
as oversized; this change adds a few lines to each, no restructure needed
first. No `todo/` item on this path.
