# SurMap survey tools for the agent (`surmap.agent.tools`)

**Date:** 2026-11-03
**Type:** Feature
**Packages:** surmap
**PR:** #83 (`#survey-agent` 7/9)

Added eight `SurveyTools` handlers behind a `SurveyWorkspace` port: `list_demos`, `run_demo`, `get_run`,
`prompt_sam`, `find_objects`, `get_object`, `get_object_geometry`, `get_frame`.
`survey_tool_handlers(workspace)` plugs them into `survey_tools_module`; the runtime binding is the
next node's. `DemoWorkspace` drives the demo's run host headlessly, records into its history and
publishes object GLB at `surmap-glb://<run>/<obj>.glb`. Objects are `obj_<surface_id>` in frame
`map`, up `-y`. `get_frame` crops by box or object mask box and downscales to `max_side`.

At wrap the module was split into `port.py`, `geometry.py` and `workspace.py` and the object tests
into three suites (file-length gate); a run that started after `run_demo` was cancelled mid-start
is now stopped. Recorded for the sweep node:
`src/surmap/docs/code-issues/private-reach-agent-tools-workspace.md` (per-call options on
`DemoRunHost.start_run`).

Reference: `docs/agent.md` § Tools..

Tests: 67 in `tests/test_agent_tools_{demo,sam,objects,object_summary,frames}.py`, builders in
`tests/agent_tool_fakes.py`; offline (fake SAM, tiny EuRoC, no RTAB-Map).
