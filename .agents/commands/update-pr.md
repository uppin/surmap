---
description: Update existing PR with current changes
---
User wants to update an existing PR with the current changes.

You should:
1. Run code quality checks and fix any issues:
   - `uv run ruff check src tests` — fix ESLint and Prettier issues (changed-files only — never `uv run ruff check src tests` or repo-wide prettier)
2. Analyze the current changes and compose the commit.
3. Commit should only include relevant work. If there are irrelevant functional changes, ask the user if they should be included.
4. Add relevant files that are not added to git yet.
5. Make a commit with a summary of the changes. Use markdown format.
6. Push the changes to the current remote branch.
7. **CRITICAL** only include files that are relevant to the PR.

## Working branch

- Commit and push to the **current branch** (no new branch creation).
- Ensure the branch is tracking the remote: `git push` or `git push -u origin <branch-name>` if needed.

## Before commit

1. Always run `git status` to verify everything is staged as expected.
2. Do not skip linting or type errors that prevent commit — fix them.
3. After pushing, the git command may return a URL; you can open it with `open <URL>` if the user wants to view the PR.
