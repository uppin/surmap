---
description: Package, dependency and script rules for SurMap (pyproject.toml)
---

# Package Rules

- One Python package: `surmap` under `src/surmap/`, built with Hatchling.
  New modules live inside it; tests mirror it under `tests/`.
- Dependencies are declared in `pyproject.toml` only.
  Runtime deps in `[project] dependencies`; dev tools in the `dev` group
  (`mypy`, `pytest`, `ruff`). Install with `uv sync --group dev`.
- Every change must keep the three gates green:

  ```bash
  uv run pytest -q
  uv run ruff check src tests
  uv run mypy
  ```

- mypy runs in strict mode over both `src` and `tests`: fully annotate new
  code, no implicit `Any` returns, no unreachable code.
- Ruff: line length 100, target `py311`, rules `E,F,I,UP,B` (includes import
  sorting — run the checker rather than hand-ordering imports).
- Do not add a dependency for something the standard library or an existing
  dependency already covers. When you do add one, say why in the PR.
