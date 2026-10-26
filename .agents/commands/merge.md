---
description: Merge the latest of a branch's actual base into it safely with backup (base-aware, not master-locked)
---
## Merge Branch

Bring the current branch up to date by merging in the **latest of its actual base branch** — with a
backup and a merge plan document. By default this is **decoupled from `origin/master`**: the base is
whatever the branch is really built on (its PR base / stack predecessor), refreshed to latest.

Use this mid-flight to keep a branch current with its (still-open) base. To move an already-merged
branch onto `master` after its predecessor lands, use `/repoint` instead.

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


## Resolve the base — MANDATORY (do not assume master)

Determine what to merge **from**, in this order (see the `pr-stack` skill):

1. **Explicit argument** — if the user passed a branch (`/merge <branch>`), use it.
2. **Registered stack** — `gh stack view --json` from a branch in the stack. Most authoritative when
   the stack is registered; it errors when the branch is not part of one, which itself tells you the
   stack was never registered.
3. **This PR's changeset** — if it carries a `## Stack Context` section, use the **Base** it names.
4. **GitHub PR base** — `gh pr view <current-branch> --json baseRefName --jq '.baseRefName'`.

5. **Ask the user** — if none resolve, ask which branch to merge from. **Never silently default to
   `master`.**

**Then always compare with the live remote PR base** (even when rule 1–3 resolved). If it differs
(PR repointed on GitHub, e.g. to `master` after the predecessor merged), the remote wins for rules 2–3
and the changeset's **Base** is updated to match; for an explicit argument, ask. See `pr-stack` skill
§ *Remote base drift*.

Always merge the **latest** of the resolved base:

```bash
git fetch origin <base>
# merge origin/<base> (or the local base branch if it is the up-to-date source)
```

## Workflow

1. **Make a backup branch** of the current branch before touching anything.
2. **Resolve the base** (above) and fetch its latest.
3. **Analyze** current vs. incoming changes.
4. **Prepare a merge plan document** in `tmp/` outlining incoming and current functionality.
5. **Prefer changes in the branch** over the base on conflict — branch code is considered newer.
6. **Do not overwrite** branch code from the base without the user's consent.
7. **Compile the code** — record state in the merge document.
8. **Run tests** — record state in the merge document. Tests guide merge quality and confirm nothing
   was lost.

## After Plan Created

Output: `**CRITICAL FOR CONTEXT & SUMMARY** The git merge document is: <path>.md`

Also state clearly which base was resolved and by which rule (argument / stack object / changeset /
PR base / asked).

## Merging Steps

1. Merge `origin/<base>` and resolve conflicts. Branch code is considered newer.
2. Make sure merged code compiles. Fix until it does.
3. Run tests to confirm none are missing and state hasn't changed.
4. Verify functionalities from both branches retained.
5. Commit once tests pass. Never use `--no-verify`.
6. Fix any failures.
7. Update the document with the merge outcome (including the resolved base).

## Related

**Commands**: `/repoint`, `/plan-pr-stack`, `/split-pr-to-stack`, `/pr`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
