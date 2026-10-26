---
description: Python code style for SurMap
---

# Python Code Style

Source of truth: `pyproject.toml` (Ruff + mypy config) and `README.md`.

- Python 3.11+, line length 100, Ruff rules `E,F,I,UP,B`.
- Fully typed: mypy strict covers `src` and `tests`. Annotate arguments and
  returns; prefer concrete types and typed data contracts over `dict`/`Any`.
- Keep data contracts explicit (see `src/surmap/types.py`): named types for
  values that cross module boundaries, validated at the edge.
- Functions should do one thing; extract before nesting deepens. Prefer plain
  functions and small classes over framework magic.
- Errors: raise specific exceptions with actionable messages; never swallow
  an exception silently. Optional/native dependencies fail with a named
  error carrying install guidance (see the RTAB-Map adapter).
- Comments answer *why*, not *what* — see `references/general-code-style.md`.
- Tests are pytest under `tests/`, mirroring the module they cover, and must
  pass together with `uv run ruff check src tests` and `uv run mypy`.
