---
description: Start and switch to a new branch based on a referenced branch or PR (e.g. a stacked follow-up off an open PR)
---
## Follow-up Branch

Create and switch to a **new branch based on a referenced branch or PR** — for continuing work on top
of something that hasn't merged yet, most often a **stacked successor** off an open PR. `$ARGUMENTS`
carries the reference (a branch name, a PR number like `#123`, a PR URL) and, optionally, a name for
the new branch.

This is the building block for extending a stack by hand. It **does not open a PR**. To add a layer
**and** open a draft PR on a registered stack, use **`/add-to-pr-stack`** (defaults to the tail;
`gh stack add` then `gh stack submit --auto`). For the full stacked-PR model (base tracking,
forward-only docs, landing rules) use the **`pr-stack` skill**
(`.agents/skills/pr-stack/SKILL.md`).

## Step 1: Resolve the reference to a base branch

Interpret `$ARGUMENTS`:

- **PR** (`#123`, `123`, or a `github.com/.../pull/123` URL) → resolve its head branch:
  ```bash
  gh pr view <ref> --json number,headRefName,url,state,mergeStateStatus
  ```
  Base branch = `headRefName`. Note the PR's `state` — a follow-up normally targets an **open** PR;
  if it is already merged, tell the user (they may want `/plan-pr-stack`/master instead).
- **Branch name** → use it directly.
- **Nothing given** → ask which branch or PR to base on. **Do not** silently base on the current
  branch or `master`.

## Step 2: Fetch the base and branch off it

**If the base branch belongs to a registered stack, use `gh stack add` instead of a raw checkout** —
it creates the branch *and* keeps the stack object correct, so the new layer is part of the stack from
the start:

```bash
gh stack view                                  # is this branch in a stack? shows the topology
gh stack checkout <base-branch-or-PR#>         # make that stack current
gh stack add <new-branch>                      # new layer on top of the stack
```

Then `gh stack submit` once there is something to publish. Extending a stack by raw `git checkout -b`
leaves the new branch outside the stack object, which has to be repaired later with
`gh stack init`/`sync`.

Only when there is **no** registered stack (or `gh stack` is unavailable):

```bash
git fetch origin <base-branch>
git checkout -b <new-branch> origin/<base-branch>    # base off the fetched ref, not local stale state
```

- **New branch name**: use the name from `$ARGUMENTS` if given; otherwise propose one and confirm
  (for a stack, follow the existing convention, e.g. `pr-<k>-<slug>`).
- If the base branch only exists locally (no remote), branch off the local ref instead and say so.
- If the working tree has uncommitted changes, stop and let the user stash/commit first — never
  discard work to switch branches.

## Step 3: Report

State the resolved base (and the PR it came from, if any), the new branch, and that HEAD switched to
it. Remind the user of the base relationship for when they open the PR:

> When you open the PR for `<new-branch>`, set its **base to `<base-branch>`** (not `master`) so the
> stack relationship holds. On a registered stack that is `gh stack submit`, which also updates the
> stack object; otherwise `/pr` then `/repoint` once the base lands. See the `pr-stack` skill.

Do not open a PR here — that's `/add-to-pr-stack` on a registered stack, or `/pr` otherwise. This
command only creates and switches to the branch.

## Rules

- Resolve the reference explicitly (branch / PR / ask) — never default to `master` or the current
  branch silently.
- Base off the freshly fetched ref so the new branch starts from the reference's latest.
- Never discard uncommitted work to switch branches.
- Never use `--no-verify`.

## Related

**Commands**: `/add-to-pr-stack` (same add-on-top, but opens a **draft PR**), `/plan-pr-stack`,
`/split-pr-to-stack` (carve an existing PR into stacked slices; this command only **adds on top**),
`/pr`, `/repoint`, `/merge`, `/squash-pr`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
