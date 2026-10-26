---
description: Git usage guidelines and repository integrity rules
---

# Git Usage

- Work on a branch; never commit directly to the default branch.
- Keep commits focused: one logical change per commit, message says *why*.
- Never rewrite published history (no force-push to shared branches, no
  amend of pushed commits) unless the user explicitly asks for it.
- Before opening a PR, run the gates from `pyproject.toml`:

  ```bash
  uv run pytest -q
  uv run ruff check src tests
  uv run mypy
  ```

- Do not commit generated or local state: `.venv/`, caches, `dist/`,
  session recordings and `*.bag` files are covered by `.gitignore` — keep
  it that way and flag new artifact types instead of committing them.
- For stacked or dependent PRs, use the `pr-stack` skill; for the full
  lifecycle (PRD, changeset, landing), use `pr-lifecycle`.
