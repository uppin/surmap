---
description: Open a PR from current changes
---
User wants to open a PR from the changes in the current focus.

## No row

Opening the PR is never a `[wf]` row and never a TODO (`pr-lifecycle` skill § *Post-wrap*). On a
planned change `/pr-wrap` step 9 runs *Creation of the PR* below as the wrap's last act; on an
ad-hoc branch with no changeset, this command runs it on its own. Either way: open it ready, or
mark the existing draft ready (title corrected first, per `/pr-wrap`'s title rules). Halts, in the
summary's **⛔ Needs you**: uncommitted changes that do not belong to this change, a current branch
unrelated to the change, lint errors with no fix, a rejected push.

You should:
1. Analyze the current changes and compose the commit.
2. Commit should only include relevant work. If there are irrelevant functionality changes, halt ⛔ and list them — the developer decides whether they are included.
3. Add relevant files that are not added to git yet.
4. Make a commit with summary of the changes. Markdown format should be used.
5. Push the changes to a newly created remote branch.
6. **CRITICAL**: Only include files that are relevant to the PR.

## Working branch selection

1. **If the user is in main/master branch**:
   - **CRITICAL**: Create a new local branch from master first
   - Switch to the new branch: `git checkout -b feature-branch-name`
   - Commit changes to this new branch
   - Push to remote with tracking: `git push -u origin feature-branch-name`
   - **Why**: Never push master to a differently-named remote branch — it's error-prone and confusing

2. **If the user is in a different branch but not related to the current change**:
   - Halt the row ⛔ with the options *a) use this branch* · *b) create a new one*

3. **If the user has manually created the relevant branch**:
   - Just use this branch as-is

## Creation of the PR

1. Run `uv run ruff check src tests` (changed-files only — never `uv run ruff check src tests`) and fix any remaining lint errors before committing.
2. Always check git status if everything is added to commit as expected.
3. Do not skip linting errors that are preventing commit. Fix them.
4. Open the PR ready for review. Draft → ready requires the wrap (`pr-lifecycle` skill
   § *Lifecycle*): with planning documents still in `docs/<area>/1-WIP/`, halt ⛔ naming the
   Wrap row instead. On a planned change this runs as the Wrap row's last step, so it is going up now:
   ```bash
   base=master   # or the stack parent's branch
   gh pr create --base "$base" --head "$(git branch --show-current)" --title "$title" --body-file tmp/pr-body.md
   gh pr view --json number,url --jq '"#\(.number) \(.url)"'
   ```
   When a draft PR already exists for the branch, do not open another: correct its title, update
   its body as below, and `gh pr ready <N>`.
   The title follows `/pr-wrap`'s title rules (what the branch delivers, no process artifact,
   subject ≤ 100 characters). The body states what the branch delivers (the changeset's
   `## Summary`, captured before the wrap), the verification that ran, the `/pr-wrap` step 7.6
   table with its decisions, and the `## Workflow` section — rows with their TODOs (`pr-lifecycle`
   skill § *PR description*), ending at the ✅ Wrap row; no row or TODO for the PR itself. End it with the PR attribution line from the session's git
   instructions.
5. Give the user the PR URL.
