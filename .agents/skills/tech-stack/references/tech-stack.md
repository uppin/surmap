---
description: SurMap technology stack and where each decision is recorded
---

# SurMap Tech Stack

Source of truth: `README.md`, `docs/architecture.md` and `pyproject.toml`.
If this file and those disagree, those win — update this file in the same change.

| Area | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | `requires-python = ">=3.11"` in `pyproject.toml` |
| Env / deps | uv, project-local `.venv` | `uv sync --group dev`; never install into the system interpreter |
| Layout | `src/surmap/` package, `tests/` mirror | Hatchling build; `packages = ["src/surmap"]` |
| Lint / format | Ruff, line length 100, `py311` | `uv run ruff check src tests`; rules `E,F,I,UP,B` |
| Types | mypy strict (src and tests) | `uv run mypy`; untyped defs are CI failures, not warnings |
| Tests | pytest | `uv run pytest -q`; test paths configured in `pyproject.toml` |
| Mapping | RTAB-Map via system/ROS 2 binding | No PyPI package; loaded at runtime, see `references/native-package.md` |
| On-board detection | Edge TPU detector + lightweight box tracker | Pi CM5 + Coral; Meta has no Edge TPU detector (documented exception) |
| Segmentation | SAM 3.1 (Meta) on the base station | RTX 5060 Ti; measure throughput/VRAM, do not assume H100 figures |
| Semantic labelling | Newest Meta Llama model via a Models API | Exact model ID recorded per run |
| Model policy | Meta first | Use a non-Meta model only where Meta offers none; record why in `docs/architecture.md` |

Scope guardrails (from `README.md`): passive survey only — no flight control,
no autonomous navigation, no mission orchestration in the current phase.
