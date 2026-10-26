---
name: analyze-build-issues
description: Survey recent CI runs for this repo (main and PRs) with GitHub Actions data, and answer which runs fail, on which gate (Ruff, mypy, pytest) and Python version, whether a failure is flaky or a real breakage, and which merged PR introduced it. Use for fleet-level CI health rather than one failing run (that is trace-ci-build).
---

# Analyze Build Issues

SurMap's CI is GitHub Actions: one workflow (`.github/workflows/ci.yml`),
three gates (`ruff`, `mypy`, `pytest`), two Python versions (3.11, 3.12).
Fleet analysis is therefore a `gh` exercise, not a build-system one.

## Collect

```bash
gh run list --workflow ci.yml --limit 50 --json databaseId,headBranch,conclusion,createdAt,headSha
gh run view <id> --json jobs          # which gate, which Python
gh run view <id> --log-failed | head -n 100
```

## Answer, in this order

1. **Is main red?** Since when, and which merged PR's run first failed
   (`gh run list --branch main`). A red main outranks every PR failure.
2. **Which gate breaks?** Ruff and mypy failures are deterministic —
   they are real breakage, never flake. Say which rule/test, not "CI failed".
3. **Which Python?** A 3.12-only or 3.11-only failure points at a
   version-specific construct; reproduce under that interpreter.
4. **Flaky or real?** Only pytest can flake here, and in this repo a
   "flake" is usually a test touching wall clock, ordering, the network
   or a native binding. Re-run once (`gh run rerun <id> --failed`);
   a second identical failure is real. Name the suspect test either way.

Write the summary to `tmp/build-analysis/` when the user wants a report:
runs examined, first-red run and PR, gate/version split, flake evidence.
There are no upstream build services or per-target timeouts to consult —
do not invent any.
