# 2026-11-04 — The chat's simulation preview outlines the on-board model's detections, labelled

- Agent: `set_onboard_model` (`FleetTools.SetOnboardModel`: `scenario_id`, `onboard_model` from
  `list_onboard_models` or `"none"`) → `onboard_model`, `streaming`. The station's stereo bridge
  runs that Coral model on the scenario's processed drone frames; the choice is kept per scenario
  (`PerceptionRegistry.choose_detector`) for pages that connect later. `NOT_FOUND` /
  `INVALID_ARGUMENT` / `FAILED_PRECONDITION` for an unknown scenario / model / a model without
  files. SYSTEM_PROMPT and the `flying-the-fleet` skill (§ 6) say when to use it.
- Wire: the bridge `status` reply gains `detections: [{frame_id, objects: [{label, score, box,
  track_id}]}]` (omitted when empty; goldens unchanged), filled by `DroneSession` from the model
  run on the pair's grey left eye; a failing model finds nothing and leaves the map running.
- Page: `HeldFrames` is generic; the bridge stream holds detections by frame and attaches them to
  the `FpvFrame` with its keypoints. The FPV outlines each object and adds a label card
  `<label> #<track> <score>%` laid out by `layout_cards` (the demo's `layoutCards` ported): near
  its object, joined by a leader, never overlapping another card, inside the image, in display
  pixels.
