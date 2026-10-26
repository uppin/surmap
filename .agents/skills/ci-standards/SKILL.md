---
name: ci-standards
description: Preflight SurMap's CI standards locally before pushing — Ruff, mypy (strict) and pytest exactly as GitHub Actions runs them — explain a specific failing rule, or check current CI status. Use when the user asks to check CI readiness, why a lint/type/test rule fires, or whether CI is green.
---

# CI Standards — Local Preflight

SurMap's standards are three commands, configured in `pyproject.toml` and
run by `.github/workflows/ci.yml` on Python 3.11 and 3.12. There is no
separate standards service to consult: if these pass locally under uv,
they pass in CI.

```bash
uv run ruff check src tests   # line length 100, py311, rules E,F,I,UP,B
uv run mypy                   # strict: src and tests, warn_unreachable
uv run pytest -q
```

## Explain a failing rule

- **Ruff**: name the rule code, show the offending line, fix the code —
  do not add the code to an ignore list to make the run green. Import
  order (`I`) is fixed by running Ruff, not by hand-sorting.
- **mypy strict**: the usual causes are an unannotated helper (tests are
  typed too), an implicit `Any` from an untyped dependency, or code
  `warn_unreachable` proves dead — delete dead code, do not guard it.
- **pytest**: a failure is a finding. Reproduce it alone
  (`uv run pytest -q tests/test_slam.py::<name>`), then use the `tdd` /
  `testing` skills. Never skip to green (see `/skip-tests` for the
  documented last resort).

## Check CI status

```bash
gh pr checks            # for the current branch's PR
gh run list --limit 5   # recent workflow runs
```

Report which of the three gates failed, on which Python version, with
the first real error — not a summary of the log's tail.
