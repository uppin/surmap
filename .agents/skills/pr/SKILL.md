---
name: pr
description: Prepare, update, and land pull requests, including branch hygiene and merge workflows. Use when the user wants help creating a PR, updating an existing PR, merging changes, splitting work across branches, splitting a PR into a stacked sequence, adding a new draft PR on top of a registered stack, preparing a stack to land (`/fix-pr-stack`), landing it (`/merge-pr-stack`), or cleaning up local branches.
---

# PR Workflow

Handle the branch and pull-request lifecycle cleanly.

## Workflow

1. Check branch and diff state.
Understand what changed, what is staged, and whether the branch is appropriate for the requested action.

2. Prepare the update.
Run the expected validation commands, compose a clean summary, and make sure the branch reflects the intended scope.

3. Create or update the PR.
Use the repo’s normal PR flow without bypass flags or hidden shortcuts.

4. Land or reorganize the work.
When asked, merge carefully, split branch contents intentionally, split a PR into a stacked
sequence (`/split-pr-to-stack`), add a draft PR on top of a registered stack (`/add-to-pr-stack`),
or clean up branches that are no longer needed.

## Use These Source Prompts

- `.agents/commands/pr.md`
- `.agents/commands/update-pr.md`
- `.agents/commands/merge.md` (base-aware merge; not master-locked)
- `.agents/commands/repoint.md` (repoint a stacked branch onto master after its predecessor lands)
- `.agents/commands/squash-pr.md` (squash-land a PR to master, or fold it into its base PR — detects the stacked-base ambiguity and asks)
- `.agents/commands/follow-up-branch.md` (start a new branch based on a referenced branch or PR; does not open a PR)
- `.agents/commands/add-to-pr-stack.md` (new draft PR at the tail of a registered stack)
- `.agents/commands/fix-pr-stack.md` (rebase, comment sweep, local-gated fixes — before landing)
- `.agents/commands/merge-pr-stack.md` (land a whole registered stack bottom-up — async merge, GitHub restacks)
- `.agents/commands/split-branch.md` (sibling branches, typically both off master)
- `.agents/commands/split-pr-to-stack.md` (split one PR into a stacked sequence; `A→B→C` → `A→B1→B2→C`)
- `.agents/commands/cleanup-local-branches.md`

## Stacked PRs

For any stacked-PR work — planning a stack, splitting an existing PR into stacked slices,
implementing one of its PRs, rebasing a single stack branch, keeping a branch current with its base,
repointing after a predecessor lands, squash-landing, preparing a stack to land (`/fix-pr-stack`)
then landing it (`/merge-pr-stack`), branching a follow-up
off an open PR, or adding a new draft PR on top of a registered stack — use the **`pr-stack` skill**
(`.agents/skills/pr-stack/SKILL.md`). It is the shared model behind `/plan-pr-stack`,
`/add-to-pr-stack`, `/split-pr-to-stack`, `/pr-stack-rebase`, `/fix-pr-stack`, `/merge-pr-stack`, `/green`,
`/validate-changes`, `/merge`, `/repoint`, `/squash-pr`, and `/follow-up-branch`.

Inside a stack, each PR is implemented in its own worktree, in the order its changeset's
`[wf]` rows set. `/pr-wrap` runs the `/validate-changes` procedure itself, and both
**always** run `/pr-stack-rebase` (this branch only — never `gh stack sync` from a per-PR worktree)
**before any code diff**, not only when the base has visibly moved.

## The `## Workflow` rows this skill's commands own

`/pr-wrap` (the `code-cleaning` skill) owns **Wrap**, the last row, under
`.agents/skills/pr-lifecycle/SKILL.md`; opening the PR ready, or `gh pr ready` on the draft, is its
closing act. `/pr` (on an ad-hoc branch) and `/fix-pr` are post-wrap procedures with no row and no
TODO (§ *Post-wrap*); reacting to and replying on review threads is `/fix-pr`'s own work.

## Comments posted on the user's behalf

A comment or reply an agent posts goes out under the user's GitHub identity, so a reader cannot
tell it from one the user typed. Every such comment — review-thread replies, PR-level comments,
issue comments, review bodies — starts with this prefix line, then a blank line, then the message:

```markdown
🤖 **<login>'s agent:**

<message>
```

`<login>` is the user's GitHub login (`gh api user -q .login`). Write the prefix into the scratch
body file, never into shell source:

```bash
{ printf "🤖 **%s's agent:**\n\n" "$(gh api user -q .login)"; cat tmp/reply-text.md; } > tmp/reply.md
```

**Control tokens are exempt.** `#skipreview`, `#automerge`, `#rebuild` and any other comment a bot
parses as a command are posted with **exactly** that body — a prefix would stop the bot from
recognising it. Reactions, PR titles and PR descriptions are not comments and take no prefix.

## References

Read `references/git-usage.md` when you need the old Muse git workflow guidance.

## Guardrails

- Never use `--no-verify`.
- Keep destructive branch actions explicit and intentional.
