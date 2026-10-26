# AGENTS.md — working in SurMap

Guidance for any coding agent (and human) changing this repository.
Project overview: [README.md](README.md).
Design: [docs/architecture.md](docs/architecture.md).

## Skills you must load

| When | Skill |
|---|---|
| Implementing or fixing anything (test-first) | [.agents/skills/tdd/SKILL.md](.agents/skills/tdd/SKILL.md) |
| Writing or editing tests | [.agents/skills/fluent-tests/SKILL.md](.agents/skills/fluent-tests/SKILL.md) |
| Starting, planning, resuming, or wrapping a change / PR | [.agents/skills/pr-lifecycle/SKILL.md](.agents/skills/pr-lifecycle/SKILL.md) |

Do not restate these skills here or in changesets — reference them and
follow them. Where this file and a skill disagree, the skill wins.

## TDD is the default way code changes

Per the `tdd` skill:

1. **Red first.** Write the failing test before the implementation —
   acceptance tests for a planned feature, a reproduction test for a
   bug, a focused red test for a behaviour change. Run it and confirm
   it fails because the implementation is missing, not because the
   environment is broken.
2. **Green.** Write the minimum code that makes the red tests pass.
   Tests define the requirement; do not weaken, skip, or delete a test
   to get green.
3. **Refactor** only with the suite green.
4. If a test cannot be made to pass honestly, halt (per the `tdd` and
   `pr-lifecycle` skills) and record the blocker — never fake a pass.

## Documentation cycle for every PR: 1-WIP → wrap → PR green

Planning documents live exactly as long as the PR is a draft
(`pr-lifecycle` skill, `references/changeset.md`):

```text
1-WIP ──► draft PR, work proceeds by [wf] rows ──► wrap ──► PR ready ──► PR green
```

1. **1-WIP.** Before implementation, create the changeset in
   `docs/<area>/1-WIP/YYYY-MM-DD-<slug>.md` plus its
   `<slug>-initial-discovery.md` companion. Classify the change
   (`Type` + `Behaviour`), write the `## Workflow` rows
   (`- [wf <n>] <status> \`<command>\` <Step> · <Result>` with nested
   TODOs), and keep the rows updated — they are the single progress
   record. Nothing stable may link into `1-WIP/`.
2. **Draft PR.** Open the PR as a draft. Work moves one `[wf]` row at
   a time (`/next` runs the next row); a command runs only its own row
   and never names a successor.
3. **Wrap.** Draft → ready requires the wrap, with no exception:
   - every Wrap-row TODO done, including *Verification executed —
     result recorded*;
   - `/wrap-context-docs`: State B folded into the stable docs,
     changelog/history entries written, and the changeset, PRD (if
     any), and discovery companion deleted from `1-WIP/`;
   - the `[wf]` rows carried into the wrap commit message and the
     PR body;
   - then `gh pr ready`. A ready PR must contain no files under
     `docs/**/1-WIP/` — check before readying:
     `git diff --name-only origin/main...HEAD | grep '1-WIP/'`
     must be empty.
4. **PR green.** Ready is not done. The PR is done when CI
   (`.github/workflows/ci.yml`) is green and review threads are
   resolved. Only then merge.

An ad-hoc PR with no planning documents has nothing to wrap; say so in
its body instead of inventing documents after the fact.

## Quality gates (run before every push)

```bash
uv sync --group dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy            # strict — untyped code is a failure
uv run pytest -q
```

- Strong types everywhere: all of `src` and `tests` must pass `mypy`
  in strict mode (configured in `pyproject.toml`). No untyped
  definitions, no implicit `Any` leaking out of adapters — contain
  untyped native boundaries behind a typed protocol (see
  `src/surmap/slam/rtabmap.py`).
- The environment is project-local and uv-managed (`.venv`,
  `uv.lock`); never install into the system Python.

## Git and PR ownership

- Commits and PRs on this repo are authored as
  `uppin <mantas.indrasius@gmail.com>` (repo-local git config is
  already set). Open PRs with `gh` while authenticated as `uppin`.
- GitHub cannot transfer PR authorship. A PR opened under the wrong
  account must be closed and re-created under `uppin` (same branch,
  base, title, and body) — do not just reassign it.
- Never commit or push unless the user asked for that exact action.

## Scope guardrail

Passive survey only (see [docs/architecture.md](docs/architecture.md)
§1): no flight control, navigation, or mission orchestration. Object
points are layered onto RTAB-Map's output, never written back into
RTAB-Map's internal map, and moving objects are never fused into the
static scene.
