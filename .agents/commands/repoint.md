---
description: Repoint a stacked branch onto origin/master (default) after its predecessor merged - change PR base + restack
---
## Repoint Branch

After a stacked PR's **predecessor has merged**, move this branch onto its new base — **`origin/master`
by default**, or a branch the user specifies. This does two things:

1. **Change the PR base** on GitHub to the new base.
2. **Restack** — rebase/merge the branch onto the new base so its diff is clean (only this PR's own
   delta remains, now that the predecessor's changes are in the new base).

Contrast with `/merge`, which keeps a branch current with its **existing** base mid-flight. `/repoint`
**changes** the base. See the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`).

> **First check whether the stack is registered.** GitHub supports stacked PRs officially via the
> `gh stack` extension. On a **registered** stack, prefer `gh stack sync` — it cascade-rebases every
> branch onto its parent, retargets, and pushes atomically with `--force-with-lease --atomic`, which
> is safer and less error-prone than doing it a branch at a time:
> ```bash
> gh stack view          # errors if this branch is not part of a stack
> gh stack sync
> ```
> This command is the **manual fallback**, for an unregistered stack or when `gh stack` cannot run.
> See the `pr-stack` skill for the tooling contract and the worktree-pinning constraint.


## Resolve the new base

- Default: `origin/master`.
- If the user specified a different target (`/repoint <branch>`), use that instead.

## Preconditions — verify before restacking

- The current predecessor's changes are actually present in the new base (i.e. the predecessor PR is
  merged). If not, warn the user — repointing onto master before the predecessor lands will pull the
  predecessor's still-unmerged work into this PR's diff. Ask before proceeding.

## Workflow

1. **Make a backup branch** of the current branch before touching anything.
2. **Fetch** the new base: `git fetch origin <new-base>`.
3. **Change the PR base** on GitHub via the **REST API** (not `gh pr edit --base`, which can fail
   with a *"Projects (classic) is being deprecated"* GraphQL error in some  orgs):
   ```bash
   repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
   n=$(gh pr view <current-branch> --json number --jq .number)
   gh api -X PATCH "repos/$repo/pulls/$n" -f base=<new-base> --jq '"#'"$n"' base→"+.base.ref'
   ```
   **Golden rule:** never delete a branch while an open PR still bases on it — that closes the
   dependent PR (unreopenable via API). Retarget the dependent's base first, then delete. See
   `.agents/skills/pr-stack/SKILL.md`.
4. **Restack the branch onto the new base:**
   - Prefer `git rebase --onto origin/<new-base> <old-base> <current-branch>` so only this PR's own
     commits are replayed and the predecessor's (now-merged) commits drop out of the diff.
   - If the history makes rebase risky, merge `origin/<new-base>` instead and note it — but the goal
     is a clean diff containing only this PR's delta. Never use `--no-verify`.
5. **Resolve conflicts**, preferring this branch's own changes (it is newer for its owned surface).
6. **Compile** — fix until it builds.
7. **Run tests** — confirm nothing regressed.
8. **Push** the restacked branch (`git push --force-with-lease`, never plain `--force`).
9. **Update this PR's changeset** — the **Base** in its `## Stack Context` becomes the new base. Only
   this PR's own changeset; a predecessor's is not yours to edit, and there is no shared document.
10. **Re-check the registered stack**, if there is one: `gh stack view` should show this branch on its
    new parent with no `⚠`. A manual repoint can leave the stack object disagreeing with the branches;
    `gh stack sync` reconciles it.
11. **Update the stack's epic**, if this branch belongs to one (its PR body's `## Stack` block links an
    epic): the line edge into this node now comes from the new base (or from the trunk), and a
    predecessor that merged is gone from the block. Run `roadmap-cli issue sync <slug>` and check the
    epic's line edges match `gh stack view`. `issue sync` re-adds every stored dependency edge, so
    **first delete from the fenced block each dependency edge whose endpoint is the merged node** —
    a dangling edge makes the next epic read reject the whole block. See
    `pr-stack` skill § *The epic must be correct*.

## After Repoint

Output which base was set, that the PR base was updated on GitHub, and whether restack was done via
rebase or merge. Confirm the PR diff now contains only this PR's own delta.

## Related

**Commands**: `/merge`, `/plan-pr-stack`, `/split-pr-to-stack`, `/pr`, `/pr-wrap`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
