# Demo SAM prompt on the page, with a per-scene default

**Date:** 2026-10-31
**Feature:** Browser demo / station SAM ports

SAM's concept prompt was fixed for the demo server's lifetime by
`--sam-label` (default `object`), so a KITTI run showed only cars
because it had been started with `car`. The prompt is now chosen per
run. The SAM pane has a **SAM prompt** box: applying it reloads the
page with `/?dataset=…&prompt=…` and the stream (`/stream?prompt=…`)
restarts with that concept. Restart keeps the prompt, and switching
scene goes back to the new scene's default. Each persisted run's title
names its prompt (`… · SAM: person`).

A run's prompt is the page's (non-blank, at most 100 characters), else
the launcher's `--sam-label` (now unset by default), else the scene's
`DatasetSpec.sam_prompt`: `box` on EuRoC V1_01, `car` on KITTI 0009,
`person` on NTU VIRAL sbs_01. An `.onnx` export's concept was fixed
when it was exported, so it wins over all of these and the box is
read-only (`demo/sam_prompt.py`).

The prompt reaches SAM through the ports, as an optional argument where
`None` keeps the adapter's configured concept:
`VideoSamDetector.reset(prompt=None)` and
`VideoSamStreamer.stream(frame_paths, prompt=None)`. SAM 3.1 prompts
every 16-frame window and labels its detections with the run's
concept. The ONNX video detector refuses any other concept by name, the
model-free `--sam-fake` stand-in relabels, and the in-memory adapters
record each video's prompt. A live change in the middle of a run is not
offered: SAM propagates ahead of playback, and a restart keeps every
result attributable to one prompt.

Verification: ruff, format, mypy strict and pytest green (703 passed,
3 skipped; 14 new tests). The rendered page script passes
`node --check`. The real launcher was run with `--sam-fake` on the
cached KITTI scene and checked over HTTP: the box is prefilled with
`car`, `?prompt=person` labels every SAM result `person`, and the run is
persisted as `KITTI 2011_09_26 drive 0009 · SAM: person`. Real SAM 3.1
on a GPU was not run for this change.
