---
description: Push unpushed work to remote and clear the worktree for garbage collection
---
Abandon the current worktree by saving any work to the remote branch, then clearing all local artifacts.

## Workflow

### 1. Check for uncommitted changes
- Run `git status` to see if there are uncommitted changes.
- If there are staged or unstaged changes, commit them with a `wip:` prefix message summarizing what's there.
- If there are no changes at all (committed or uncommitted) ahead of the remote, inform the user and ask if they still want to clear the worktree.

### 2. Push to remote
- Push the current branch to its remote tracking branch.
- If no upstream is set, push with `-u origin <branch-name>`.
- **If the push fails, STOP and report the error. Do NOT proceed to clearing.**

### 3. Clear the worktree
- Only after a successful push, run `uv run pytest -q` (`git clean -fdx -e '.env' -e '.env.*'`) to remove all ignored and untracked files (node_modules, dist, .nx/cache, etc.). `.env` files are kept — they hold local secrets and are not in git.
- This returns the worktree to a minimal state so git can garbage-collect it later.

### 4. Report
- Confirm the branch name and remote URL that was pushed to.
- Confirm the worktree has been cleared.
- Remind the user they can delete the worktree with `git worktree remove <path>` when ready, or leave it for garbage collection.
