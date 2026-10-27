# Changeset: PX4 SITL → EuRoC session bridge

**Date**: 2026-10-27
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 2 — one package (`surmap.simulation`), filesystem I/O adapter, unit/acceptance tests with synthetic fixtures

## Workflow

- [wf 1] ✅ 2026-10-27 `/plan-red` Plan — PRD, changeset, initial discovery · this file + PRD + discovery
- [wf 2] ✅ 2026-10-27 `/plan-red` Red — acceptance and failing lower-tier tests · 4 tests in `tests/test_simulation_euroc_export.py`
  - [x] Acceptance: capture dir → EuRoC mav0 with matching L/R `t_ns` PNGs
  - [x] Calibration `sensor.yaml` carries intrinsics, resolution, baseline
  - [x] GPS CSV written beside the EuRoC tree
- [wf 3] ✅ 2026-10-27 `/green` Green — implement until every red test passes · `surmap.simulation` + CLI + Harmonic stereo SDF + ROS2 dumper; demo `load_calibration` reads export
  - [x] `surmap.simulation` exporter + capture loader
  - [x] `scripts/export_sitl_session.py` + runbook
  - [x] Preflight: Harmonic models lack stereo → `docs/simulation/gz/` + dump script
  - [x] Park live ConnectRPC + GPS-on-wire as Future enhancement TODOs
- [wf 4] ⬜ `/pr-wrap` Wrap — fold State B, delete 1-WIP, ready PR ·
  - [ ] Verification executed — result recorded
  - [ ] Architecture open decision notes Gazebo/PX4 SITL for WSL Machine 3
  - [ ] changelog / history entry
  - [ ] 1-WIP removed; `gh pr ready`

## Initial Discovery

Full dump: [2026-10-27-px4-sitl-session-bridge-initial-discovery.md](2026-10-27-px4-sitl-session-bridge-initial-discovery.md).

## State A

- Machine 3 software unevaluated; Gazebo listed as a candidate only.
- No PX4/SITL bridge code; EuRoC ingest exists for demo/sidecar.
- Branch `feat/PX4_sitl` tip identical to `main`.

## State B

- Documented SITL **capture directory** format (no ROS2 dependency in SurMap).
- `surmap.simulation` loads capture → writes EuRoC session + GPS CSV.
- CLI script + `docs/simulation/px4-sitl.md` runbook.
- Passive-survey guardrail explicit: PX4 flies externally; SurMap reads sensors only.

## Delta

| Area | Change |
|---|---|
| `src/surmap/simulation/` | New: calibration yaml render, capture load, EuRoC export |
| `scripts/export_sitl_session.py` | CLI |
| `docs/simulation/` | Runbook + this WIP set |
| `tests/` | Acceptance tests + tiny capture fixture |

## Verification

```bash
uv run pytest -q tests/test_simulation_euroc_export.py
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

Manual (operator WSL, not CI): dump Gazebo stereo+GPS into a capture
dir → `uv run python scripts/export_sitl_session.py …` →
`uv run python scripts/demo.py` / sidecar against the export.
