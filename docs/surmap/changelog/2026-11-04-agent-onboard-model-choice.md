# The survey agent chooses the on-board detector model, or none

**Date:** 2026-11-04
**Feature:** Survey agent / on-board detection choice

- **Tool.** `list_onboard_models` (`SurveyTools.ListOnboardModels`, SYNC · 10 s · FAIL) lists
  every Coral profile with its title, note, whether this station has its files, and which is
  the station default (`default_model`, `"none"` when runs default to no on-board model).
- **Run choice.** `run_demo` and `run_rtabmap` take `onboard_model`: a profile name runs that
  model on the frames, `"none"` runs none, absent uses the station default. An unknown name is
  `INVALID_ARGUMENT`; a profile the station lacks is `FAILED_PRECONDITION` and records no run.
  Each run builds its own detection source, so no tracker state carries between runs.
- **What it can recognise.** Each listed model carries `classes`, the 80 COCO classes
  (`surmap.detection.COCO_CLASSES`); `run_demo` answers `onboard_recognises_prompt` — whether the
  on-board model has a class for the run's SAM concept (`debris`, buildings and fire: no). A
  cross-check of the three models on the Bevy sim capture found them detecting none of its
  (tarp-covered) cars at score 0.3; sim realism is a follow-up PR.
- **Reporting.** `RunInfo.onboard_model` (and `RunDemoResponse.onboard_model`) name the model a
  run used, read back from the run title's ` · On-board: <model>` part; empty for none.
- **Process.** `python -m surmap.agent --coral-model-dir <dir> --coral-model <profile|none>`;
  the dir falls back to `$SURMAP_CORAL_MODEL_DIR`. Code: `surmap.agent.tools.onboard`.
- **Tests.** `tests/test_agent_onboard_models.py` (16) and four config tests in
  `tests/test_agent_server_app.py`.

Docs: [docs/agent.md](../../agent.md).
