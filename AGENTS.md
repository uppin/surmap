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
| Verifying Gazebo/PX4 SITL → EuRoC on the WSL host | [.cursor/skills/px4-sitl-test/SKILL.md](.cursor/skills/px4-sitl-test/SKILL.md) |

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

## Lint and quality gates — mandatory before commit and before pushing a PR

These are the lint rules of this repository. They are not advisory:
the branch ruleset requires the same checks green in CI
(`test (3.11)` / `test (3.12)`) before any PR can merge, so a red
local run is a red PR.

| Gate | Command | Rules configured in |
|---|---|---|
| Ruff lint | `uv run ruff check src tests` | `pyproject.toml` `[tool.ruff.lint]` (`E`, `F`, `I`, `UP`, `B`) |
| Ruff format | `uv run ruff format --check src tests` | `pyproject.toml` `[tool.ruff]` |
| Type check | `uv run mypy` | `pyproject.toml` `[tool.mypy]` — `strict = true` |
| Tests | `uv run pytest -q` | `pyproject.toml` `[tool.pytest.ini_options]` |

Rules for the agent:

1. **Run the full set after your final edit and before `git commit`.**
   Then run it again before pushing the PR branch (and again before
   `gh pr ready` if anything changed since). One green run on stale
   code proves nothing.
2. **Never commit or push a red gate and hope CI or review catches
   it.** Fix the code until every gate passes locally, in this order:
   `ruff format` (auto-fix), `ruff check`, `mypy`, `pytest`.
3. **Never silence a gate to get green** — no new `# noqa`,
   `# type: ignore`, per-file ignores, relaxed mypy settings, or
   skipped tests — unless the change itself is the subject of the PR
   and the reason is stated in the PR body.
4. If a gate failure looks pre-existing, prove it on the untouched
   base (`git stash` / a clean checkout) before claiming so; report
   it as a finding instead of letting your PR go red.
5. Strong types everywhere: all of `src` and `tests` must pass `mypy`
   in strict mode. No untyped definitions, no implicit `Any` leaking
   out of adapters — contain untyped native boundaries behind a typed
   protocol (see `src/surmap/slam/rtabmap.py`).
6. The environment is project-local and uv-managed (`.venv`,
   `uv.lock`); run the gates through `uv run`, never the system
   Python.

```bash
uv sync --group dev   # once per checkout / after dependency changes
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest -q
# only when all four pass: git commit, git push, open/update the PR
```

## Git and PR ownership

- **All work lands through a pull request. Never push to `main`.**
  Every change — features, fixes, docs, this file — goes on a branch,
  is pushed as that branch, and merges only via its PR (green CI,
  review resolved; see the documentation cycle above). A direct push
  to `main` is a process failure even when the change is correct: if
  it happens, disclose it immediately and let the user decide whether
  to keep it or move it into a PR retroactively. Landing on `main`
  via a merged PR is the only exception.
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
