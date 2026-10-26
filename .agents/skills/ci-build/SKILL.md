---
name: ci-build
description: Lessons and anti-patterns for SurMap's CI — GitHub Actions running uv, Ruff, mypy (strict) and pytest on Python 3.11 and 3.12. Use when a CI run fails, when adding a workflow step or dependency, or when a check passes locally but fails in CI (or the reverse).
---

# CI Build — SurMap

The whole CI contract is `.github/workflows/ci.yml` plus `pyproject.toml`:
every push to `main` and every pull request runs, on Python 3.11 and 3.12,

```bash
uv sync --group dev
uv run ruff check src tests
uv run mypy          # strict, over src and tests
uv run pytest -q
```

There is one package (`src/surmap/`), no build matrix beyond the Python
version, and no native build in CI. Anything more elaborate is a smell.

## Lessons

1. **CI has no RTAB-Map, no Coral, no camera, no GPS.** That is by design:
   `RtabmapBackend` loads the system binding at runtime and raises
   `RtabmapUnavailable` without it, and tests use `InMemorySlamBackend`
   and stub bindings (`tests/test_slam.py`). A test that needs the native
   install is a test written at the wrong seam — fix the seam, never add
   a system install to the workflow to satisfy it.
2. **Local green must mean CI green.** Run the three gates with the
   project's own environment (`uv run …`), not a globally installed
   pytest/mypy: uv resolves the locked versions from `uv.lock`, a global
   tool may not. A version-only failure on one Python (3.11 vs 3.12) is
   usually a newer-syntax or typing construct — `target-version = "py311"`
   in Ruff and `python_version = "3.11"` in mypy exist to catch it early.
3. **mypy is strict and covers tests.** Untyped defs, implicit `Any` and
   unreachable code fail CI, including in `tests/`. Annotate test helpers
   and builders too; a `# type: ignore` needs its error code and a reason.
4. **Dependencies change the lockfile or they don't count.** Add deps in
   `pyproject.toml` (runtime) or the `dev` group (tools), commit the
   resulting `uv.lock`, and expect CI's `uv sync --group dev` to be the
   first place a bad pin shows up.
5. **Keep the workflow boring.** No codegen, no caches beyond uv's, no
   artefact uploads unless a named consumer exists. A failing step should
   be reproducible with one of the three commands above, verbatim.

## When CI fails and local passes (in order)

1. Python version: reproduce under the failing version first.
2. Environment: a test reading files outside fixtures, the wall clock, or
   the network. Make it deterministic (fixed `t_ns`, recorded fixtures).
3. Native/system state: a test reaching for RTAB-Map or hardware. Move it
   behind the adapter seam (see `hexagon-testable-architecture`).
4. Only then suspect the workflow file itself.
