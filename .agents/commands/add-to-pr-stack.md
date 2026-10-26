---
description: Open a new ad-hoc draft PR at the tail of a registered stack (or a user-named parent that is that tail)
---
## Add to PR Stack — ad-hoc draft PR on an existing stack

Start **new work** as a stacked PR **without waiting** for the rest of the stack to merge. Create a
new layer on a **registered** `gh stack`, commit the new work, and open a **draft** PR whose base is
the stack tail (or another parent the user named — only if that parent *is* the tail).

`$ARGUMENTS` may carry:

- a **parent** — PR number (`#123` / `123`), PR URL, or branch name
- a **name** for the new branch
- a short description of the new work

This is the command that **opens the PR**. `/follow-up-branch` only creates and switches to a branch;
it never opens a PR and never silently defaults to the current branch or `master`. `/plan-pr-stack`
plans a whole stack from requirements. `/split-pr-to-stack` carves an existing PR into slices.

Load the **`pr-stack` skill** (`.agents/skills/pr-stack/SKILL.md`) first — this command assumes that
model (`gh stack` required, linear stack, drafts via `submit --auto`, never `--open`).

## Default parent: the tail

Unless the user named a parent, the new PR sits on the **tail** of the current stack (the branch
furthest from trunk — last entry in `gh stack view --json` `.branches[]`).

`gh stack add` **only appends on top**. It cannot insert a layer under an existing successor, and it
refuses to run unless HEAD is already the top (`gh stack top`, then `gh stack add`).

## If the user named a parent

Resolve it (PR → `headRefName`, or the branch name). Then:

| Named parent | What to do |
|---|---|
| **Tail of the current stack** | Same as the default. Proceed. |
| **Tail of a different registered stack** | `gh stack checkout <PR#\|branch>` so that stack is current, then proceed on **its** tail. |
| **In a stack, but not the tail** | **Stop.** Adding there would fork the stack: two open PRs with the same base are **siblings**, and a stack is linear. Inserting in the middle is `/split-pr-to-stack` (or `unstack` + `init` with consent), not this command. |
| **No registered stack** | **Stop.** Do not fall back to `git checkout -b` or `gh pr create --base`. Point at `/follow-up-branch` (branch only) or `/plan-pr-stack` (new stack). |

Never silently default to `master` or the current branch when they are not the tail.

## Step 0: Preflight — `gh stack` is REQUIRED

```bash
gh auth status
gh extension list | grep -q 'github/gh-stack' && gh stack --version
```

If the extension is missing, **stop**. Do not open the PR with `gh pr create`. Ask the user to
install `gh extension install github/gh-stack` (do not install it unprompted).

```bash
git status --porcelain | grep -v '^?? '
```

If there are **tracked-file** changes, **stop** and ask the user to commit or stash them. Never
discard uncommitted work to switch branches. Never `gh stack add -A` / `-u` — that scoops unrelated
files (and untracked files, with `-A`) into the new layer.

Untracked files may stay in the tree; do not add them unless they belong to this new work.

## Step 1: Resolve the stack and the parent

```bash
gh stack view --json
gh stack view
```

- **Current stack exists** → tail = last `.branches[]` entry. Default parent = that branch.
- **No current stack** and `$ARGUMENTS` names a PR → `gh stack checkout <PR#>` to discover it from
  GitHub, then re-read `gh stack view --json`. If that PR is not in a stack, stop (see the table).
- **No current stack** and no PR in `$ARGUMENTS` → **ask** which stack / PR to extend. Do not guess.

Apply the parent table above. Confirm the new branch name: use the name from `$ARGUMENTS` if given;
otherwise propose one in the stack's convention (e.g. `pr-<k>-<slug>` or `<area>/<slug>`) and
confirm.

If the proposed branch already exists, stop.

## Step 2: Add the layer on top

HEAD must be the stack top — `gh stack add` errors otherwise:

```bash
gh stack top                         # checkout the tail; merged layers are skipped
gh stack add <new-branch>            # empty layer at the same commit as the tail
```

Do **not** pass `-A`, `-u`, or `-m` here. Stage and commit in Step 3 so the new PR contains only the
intended files.

Stay on `<new-branch>`. Unlike `/plan-pr-stack`, **do not** restore the previous branch — the point
is to start the new work here.

## Step 2b: Cross-check the deferred-work records for this layer

Before writing the new layer's changeset, run planning-phase **Step 2b** for the packages *this*
layer touches — `<package-dir>/docs/todo/`, `<package-dir>/docs/code-issues/` and the open deferred
answers (`<package-dir>/docs/deferred-answers/`, `docs/<area>/deferred-answers/`). Load the
`deferred-work` skill (`.agents/skills/deferred-work/SKILL.md`).

A layer added on top of a stack has a specific hazard the original planning did not: some of the
items in that record were **deferred by the PRs below it**, and their *when it becomes possible* line
may name a PR that is now green. Read those first — this layer may be exactly where they become
actionable.

Put the verdicts in this layer's own `## Prerequisites` (`pr-lifecycle/references/changeset.md` §2.5), and if the fix is
a restructure inside this layer's own files, its **Restructure Prerequisite** block too.

If the structure would make this layer harder to implement, the ground-softening suggestion applies
here as well — propose it and **ask**
(`.agents/skills/deferred-work/references/planning-cross-check.md` § *Softening the ground*). But a
restructure that reaches into code the PRs **below** this one own is not this layer's to do — it goes
to `/fix-pr-stack`'s reckoning or a follow-up PR after the stack lands, never into a layer bolted onto
the tail. A tail layer has no successors to disturb, but every PR beneath it is already
reviewed — and restructuring their code from here would rewrite diffs their reviewers have signed
off on.

## Step 2c: Place this layer in a green wave

A tail layer joins an existing grouping, so its wave is **derived, not chosen**: it is one above the
highest wave whose *behaviour* this layer needs, and wave 1 when it needs none. Read the predecessor
waves from the open PRs' `### Green wave` sections (or their descriptions) — do not re-derive the
whole stack's grouping from scratch, and do not edit a sibling's row.

Then put it in this layer's own changeset `## Stack Context` → `### Green wave` — `**Wave:** k of m`
(`m` grows if this layer starts a new wave), its **node number** (the new tail position, `nN`),
`Concurrent with:` the other nodes of that wave, `Blocks:` `nothing` (a tail layer has no successors
yet), and the real dependency edges. Keep it consistent with `Greenable independently?`: wave 1 ⇔
`yes`. See the `pr-stack` skill § *Order inside a green wave*.

**Node numbers here, PR numbers where the dependency is on composition.** The grouping is written in
node numbers like every other changeset's. But unlike a stack planned from scratch, this layer's
predecessors are **already open**, so a dependency on what one of them actually contains — the case
this command exists for — is exactly when a PR number is warranted. Write it alongside the node:
`n3 (#2403)`. See the `pr-stack` skill § *Node numbers*.

**Renumbering moves node numbers.** If this append shifts anyone's `K/N` (Step 3 renumbers titles),
the same PRs' `### Green wave` rows are stale by the same amount. Each PR owns its own row — report
which ones need re-checking rather than editing a sibling's changeset from here.

**A tail layer cannot lead its wave.** `gh stack add` only appends, so a layer that turns out to be a
blocker for PRs already in the stack is in the wrong position — that is `/split-pr-to-stack` or a
replan, not an append. Say so rather than recording a wave the line contradicts.

## Step 2d: Start the layer's changeset

When this layer has a changeset, start it per the `pr-lifecycle` skill § *Start a changeset*
(`.agents/skills/pr-lifecycle/SKILL.md`) with its kind's preset, as every `/plan-pr-stack` node does;
its Wrap row readies the draft Step 3 opens (`/pr-wrap` step 9). A layer with no changeset gets no
rows.

## Step 3: Commit the new work, then submit a draft PR

GitHub will not open a PR for a branch that has no commits ahead of its base. An empty
`gh stack add` is not enough.

- If the new functionality (or this command's own files) is ready, stage **only those files**,
  commit, then submit.
- If there is nothing to commit yet, **do not** create an empty commit and **do not** submit. Report
  the new branch, the resolved base, and that `gh stack submit --auto` will open the draft PR once
  there is a commit. `/follow-up-branch` is the better fit when the user only wanted a branch.

When there is a commit:

```bash
gh stack submit --auto
```

**Never `--open`.** New PRs are drafts. `--open` marks **new and existing** PRs ready for review and
would flip earlier drafts in the stack. Do not change the draft/ready state of predecessors.

Do not use `gh pr create` — that leaves the new branch outside the GitHub stack object.

### Title the new PR, and renumber the ones below it

`--auto` leaves a title derived from the branch or the commit. Replace it, and fix the position on
every other PR in the stack: adding a layer changes `N` for all of them, and a stale `3/5` on a
six-PR stack is read as fact. See **PR titles** in the `pr-stack` skill.

1. **Read the slug** from any changeset's `## Stack Context` in this stack — it was chosen at
   planning and never changes. Do not invent a second one.
2. **Title this PR** as `<type>(<package>): <what it delivers> (#<slug> <new-K>/<new-N>)`. The
   subject states the delivery as shipped — never `red`, `stubs`, `WIP`, `phase N`.
3. **Renumber every open PR below it**, subject unchanged, only the trailing group moving:

```bash
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X PATCH "repos/$repo/pulls/<pr>" \
  -f title="<type>(<pkg>): <unchanged subject> (#<slug> <K>/<newN>)" --jq '"#\(.number) → \(.title)"'
```

Use `gh api`, not `gh pr edit --title` (Projects-classic GraphQL fault in some  orgs).
**Skip merged PRs** — their titles are already commits on `master`, and editing the PR page only
suggests history was corrected when it was not.

### Revise the stack's epic — MANDATORY

The stack's epic issue (label `overstack-epic`, linked from every PR's `## Stack` block) is what
overstack reads, and a new PR it does not list is invisible to it. In this run, edit only the
fenced DAG block, per `pr-stack` skill § *The epic must be correct*:

0. **Record the epic in this PR's changeset** — `## Stack Context → Epic`, read from a sibling PR's
   `## Stack` block (its absence is the first sign the stack has no epic). Do this **before** the
   commit above so it ships in it; if the commit and push already happened, make a new commit and
   push it — never leave the edit only in the worktree, never amend.
0b. **Write this PR's `## Stack` block** into its description (`**Kind:**`, wave line, epic link,
   with the `gh api -X PATCH` above): `issue sync` takes every node's kind from that line and
   refuses the whole sync for a PR without it.
1. **Add the node** (`n<new-K>`, branch, PR number, title, `**Kind:**`) and the **line edge** from
   the tail.
2. **Add a `kind: dependency` edge for each predecessor whose *behaviour* this layer needs**
   (not for a stub-level need — wave assignment ignores `level`, so it would push the node up a wave). A layer with no such need is **wave 1** —
   no dependency edge, however high it sits. Never add one by default just because it is on top: that
   is how a stack collapses into a chain.
3. Renumbered titles (the step above) are mirrored in the block.
4. Run `roadmap-cli issue sync <slug>`, then check the waves derived from the block against this PR's
   `Wave k of m`.

No epic on the stack: say so in the report and offer `/plan-pr-stack`'s epic step — never skip
silently.

## Step 4: Report

Print `gh stack view` and state:

- the new branch and its base (tail / named parent)
- the new **draft** PR URL
- the stack topology (predecessor → this PR)
- the **epic** URL and the edges added to it (or that the stack has none)
- this PR's **green wave**, and whether it is startable now or waits on a predecessor's behaviour
- any `⚠` on the stack — do not cascade-rebase (`gh stack sync`) from this worktree to “clean it
  up” unless the user asked; `/pr-stack-rebase` is the per-branch fix

Remind: merge order is still bottom-up. This PR must not merge before its predecessors.

## Rules

- **Run Step 2b for the new layer** — record every relevant `<package-dir>/docs/todo/`,
  `<package-dir>/docs/code-issues/` and deferred-answer item in its own `## Prerequisites` with a verdict, and check whether items the
  PRs below deferred are now unblocked.
- **Never restructure code a lower PR owns from a tail layer.** That belongs to `/fix-pr-stack`'s
  reckoning or a follow-up PR.

- **`gh stack` is required.** Never substitute `gh pr create --base` or a raw `git checkout -b`.
- Default parent is the **tail**. A named parent is allowed only when it **is** the tail (of this
  stack, or of another stack after `gh stack checkout`).
- **Stop on a non-tail parent** — siblings are not a stack; inserting is `/split-pr-to-stack`.
- **Never `--open`** on `gh stack submit`. New PRs are drafts.
- **Title the new PR and renumber the stack** in the same run. `K/N` that no longer matches the
  stack is worse than absent. Never renumber a merged PR.
- **Never `gh stack add -A` / `-u`.** Never discard uncommitted work. Never `--no-verify`.
- Do not flip predecessor draft/ready state. Do not `gh stack unstack` or `gh stack modify`.
- Stay on the new branch after submit.

## Related

**Commands**: `/follow-up-branch` (branch only, no PR, never default the base), `/plan-pr-stack`
(plan a stack from requirements), `/split-pr-to-stack` (carve an existing PR; this command only
**adds on top**), `/fix-pr-stack` (Wave 1 may call this to add tail PRs for stack TODOs / code
issues), `/pr`, `/pr-stack-rebase`, `/repoint`, `/merge-pr-stack`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
**GitHub docs**: <https://gh.io/stacks>
