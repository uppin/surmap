---
description: Create a reviewable DRAFT PR from current changes, skipping all checks
---
User wants a fast, reviewable **draft** pull request from the current changes. This command
**intentionally skips all validation** — no `uv run ruff check src tests`, no `uv run mypy`, no `uv run pytest -q`, no
`/pr-wrap` or any wrap/validation workflow. The point is to get eyes on work-in-progress quickly; the
draft state signals the branch is not merge-ready.

**Not a `## Workflow` row.** A draft PR closes no `[wf]` row of the changeset and does not wrap —
leaving draft is what requires the wrap (`pr-lifecycle` skill § *Lifecycle*); the
changeset stays in `1-WIP`. Its Wrap row readies it, as the wrap's last act
(`.agents/skills/pr-lifecycle/SKILL.md` § *Lifecycle*).

**Do NOT** run linting, type-checking, tests, or validation steps, and do not block on failing or
unfinished checks. Skipping them is the purpose of this command — do not silently run them anyway.

You should:
1. Review the current changes (`git status`, `git diff --stat`) and stage the files relevant to this
   work. Only include relevant files; if unrelated changes are present, ask the user before including
   them.
2. **Bring the context documentation up to date** before committing, by conducting the
   `update-context-docs` workflow (`.agents/commands/update-context-docs.md`): update the PRD (in
   `docs/{product-area}/1-WIP/`) if one exists, otherwise the feature doc; update the active
   changeset in `docs/<area>/1-WIP/` (the TODOs under its `[wf]` rows, status sections,
   test-result counts, implementation evidence) to reflect the current implementation state. This is
   documentation sync, **not** a validation gate — do not run tests/lint/type-check to satisfy it;
   just make the docs match reality (including honestly noting anything WIP or not-yet-passing). Stage
   the updated docs so the draft PR ships with current context documentation.
3. Commit with a clear Markdown summary of what changed and why (use the repo's standard commit
   trailer conventions).
4. Push to a remote branch (create one if needed — see branch selection below).
5. Create a **draft** PR with `gh pr create --draft`, giving it a concise title and a Markdown body
   that summarizes the scope and explicitly notes this is a WIP draft with checks skipped (use the
   repo's standard PR body trailer conventions). When the branch has a changeset, the body also
   carries its `## Workflow` section, rows with their TODOs (`pr-lifecycle` skill § *PR description*).
6. Return the PR URL to the user.

## Working branch selection

1. **If on main/master**: create a new branch first (`git checkout -b <feature-branch-name>`), commit
   there, and push with tracking (`git push -u origin <feature-branch-name>`). Never push master to a
   differently-named remote branch.
2. **If on a different, unrelated branch**: ask whether to use it or create a new one.
3. **If on a branch the user created for this work**: use it as-is.

## Guardrails

- Never use `--no-verify`.
- This is a **draft** — never mark it ready-for-review and never merge it.
- Keep the commit scoped to relevant files only.
