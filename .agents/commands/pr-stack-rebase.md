---
description: Rebase a stack branch onto the latest of its own base - this worktree's branch by default, or a bottom-up cascade over a PR range, each layer in a worktree that owns it
---
## PR Stack Rebase — one branch at a time, in a worktree that owns it

Bring a stack branch up to date with the latest tip of **its own base**. Two modes:

| Mode | Invocation | Scope |
|---|---|---|
| **Single** (default) | `/pr-stack-rebase` · `/pr-stack-rebase <base-branch>` | the branch checked out in **this** worktree, and nothing else |
| **Cascade** | `/pr-stack-rebase from #2 to #4` · `#2..#4` · `2..4` · a list of PR numbers or branches | each named layer, **bottom-up**, each rebased in a worktree that owns it |

Single mode is the per-worktree counterpart to the stack-wide `gh stack sync`: it is what each
`/green` worktree runs for itself while a stack is being implemented concurrently. **It remains the
default and the mode every hard-gate caller uses.**

Cascade mode exists for the case single mode cannot serve: several layers have gone stale at once —
typically because a predecessor was greened and force-pushed — and nobody is sitting in each of those
worktrees to run the command themselves.

**Scope rule.** In either mode, exactly one branch is rewritten at a time, and only ever from a
worktree that owns it. Trunk is never fast-forwarded. Branches outside the requested set are never
touched.

**Hard-gate callers.** `/green`, `/green-attack`, `/validate-changes`, and `/pr-wrap` **always**
invoke this command in **single mode** on a stack branch **before any implementation or code diff**.
A ⚠-free `gh stack view` is not permission to skip it: leaked ancestor commits can still sit in
`HEAD` relative to a stale merge-base, and treating that as this PR's work (or deleting the "extra"
files) is how predecessor code gets destroyed. `/green` and `/green-attack` also need the latest
ancestor implementation before they start. If the branch already contains the latest base tip and the
commit range is this PR only, this command is a **verify-and-publish** — it does not rewrite history,
but it still makes sure the remote branch holds exactly this state (Step 4b). **A hard-gate caller must never widen itself into cascade mode**: rewriting branches
its user did not name is not part of "get my branch current".

> ### Cascade mode is still NOT `gh stack sync` / `gh stack rebase`
> Those rewrite **every** branch in the stack and force-push them **atomically from one worktree**.
> Git refuses to update a branch checked out elsewhere, so in the concurrent-green model they either
> fail outright or, where they succeed, rewrite a branch somebody is mid-implementation on. Use them
> only from a dedicated stack-wide worktree with every stack branch free — see the `pr-stack` skill.
>
> Cascade mode differs on all three counts: it rebases **only the layers you named**, it runs each
> layer **inside a worktree that owns that branch**, and it pushes each branch **individually,
> stopping at the first failure** rather than atomically.

Contrast with the neighbours:

| Command | Scope | What it changes |
|---|---|---|
| `/pr-stack-rebase` (single) | this worktree's branch | replays this branch's commits on the **latest tip of its existing base** |
| `/pr-stack-rebase` (cascade) | the named layers, bottom-up | the same, per layer, each in a worktree that owns the branch |
| `/merge` | this branch | **merges** the base in instead of rebasing (keeps history, adds a merge commit) |
| `/repoint` | this branch | **changes** the base (usually to `origin/master` after the predecessor landed) |
| `gh stack sync` | the whole stack | cascade-rebases and force-pushes every branch, atomically, from one worktree |

## Step 0: Parse the argument — which mode?

- **No argument** → single mode on the current branch.
- **One token that names a branch** (`/pr-stack-rebase pr-1-slug`) → single mode with an explicit base.
- **A range or list** — `from #2 to #4`, `#2..#4`, `2..4`, `pr-2-slug..pr-4-slug`, or two or more
  PR numbers / branch names → **cascade mode**.

PR numbers may be written as `#2` meaning *the second PR of this stack* (its position), or as a real
PR number like `#2206`. **Disambiguate explicitly and say which reading you used** — a small integer
is almost always a stack position, but never guess silently. Resolve positions against
`gh stack view`, bottom-up, where position 1 is the branch based on trunk.

If the argument names layers that are not contiguous, say so and rebase the contiguous span that
covers them — a gap would leave a middle layer on a stale parent while its successor moved.

## Step 1: Preflight

```bash
git rev-parse --show-toplevel                 # the worktree we are pinning
git branch --show-current                     # the branch checked out here
git status --porcelain                        # must have no tracked-file changes
git worktree list                             # which branches are pinned where
gh stack view                                 # topology, and which PRs are open/merged
```

**Single mode.** If the current branch is not part of a stack (no `gh stack view` entry, no
`## Stack Context` in its changeset, no stacked PR base), stop and tell the user — `/merge` is the
command for an ordinary branch.

**Cascade mode.** The current branch does **not** need to be in the stack — cascade mode may be run
from a planning worktree, or any worktree sitting on an unrelated branch. What it does need:

- **A clean tree here**, because cascade may borrow this worktree (Step 3b). Commit first — never
  `--no-verify`, never amend, do not stash silently.
- **`ORIGINAL_BRANCH` recorded** before anything else, and restored at the end **including on
  failure**:
  ```bash
  ORIGINAL_BRANCH=$(git branch --show-current)   # must not be empty; refuse a detached HEAD
  ```
  A detached start cannot be restored to a named branch. Stop and ask the user to check one out.

## Step 2: Resolve each layer's base — MANDATORY (never assume master)

For every branch to be rebased, resolve what to rebase **onto**, in this order (the base-tracking
order from the `pr-stack` skill):

1. **Explicit argument** — the base named by the user (single mode only).
2. **Registered stack** — `gh stack view --json`; read that branch's parent.
3. **That PR's changeset** — the **Base** named in its `## Stack Context` section.
4. **GitHub PR base** — `gh pr view <branch> --json baseRefName --jq '.baseRefName'`.
5. **Ask the user.** Never silently fall back to `master`.

State which rule resolved each base before doing anything.

### Step 2b: Reconcile with the remote PR base — MANDATORY, every layer, every run

Rules 1–3 are local or cached views; someone may have **repointed the PR on GitHub** since — usually
to `master` after its predecessor merged (GitHub retargets automatically when the base branch is
deleted), or to another branch. **The remote PR base is live truth** and is checked on every run,
whichever rule resolved the base above:

```bash
PR_JSON=$(gh pr view "$BRANCH" --json state,baseRefName 2>/dev/null) || PR_JSON=""   # live API, never cached
PR_STATE=$(jq -r '.state // empty' <<<"$PR_JSON")
REMOTE_BASE=$(jq -r '.baseRefName // empty' <<<"$PR_JSON")
```

- **No PR found** (`gh pr view` failed, or `PR_STATE`/`REMOTE_BASE` is empty — e.g. a local-only
  cascade layer) → nothing to reconcile; keep the resolved base and say so.
- **`PR_STATE` is `MERGED` or `CLOSED`** → skip the layer here, exactly as Step 3's "never rebase a
  merged or closed PR" rule says; do not reconcile or rebase it.
- **Normalize before comparing.** The changeset form is `Base: origin/master` while GitHub returns
  `master`: strip a leading `origin/` (and `refs/heads/`) from the resolved base, then compare
  branch names. Always build refs as `origin/<name>` from the **normalized** name — never
  `origin/$REMOTE_BASE` on a value that may already carry the prefix (`origin/origin/master`). A
  difference that disappears after normalizing is **not** drift.

| Normalized resolved base vs `REMOTE_BASE` | Action |
|---|---|
| equal | proceed |
| differ, and the base came from the **stack object, changeset, or local state** | **the remote wins.** Rebase onto `origin/$REMOTE_BASE` (below), then fix the local record of the base (below) |
| differ, and the base came from an **explicit argument** | **STOP and ask.** The user named one base, GitHub says another — rebasing onto the argument while the PR base stays different leaves a PR diff that does not match the branch |

**Rebasing across a repoint.** The old base is no longer the upstream, and the branch still carries
the old base's commits (or their pre-squash originals), so a plain `git rebase origin/$REMOTE_BASE`
would replay the predecessor's work into this PR. Use the `--onto` form of Step 4.5 with the old
base's tip as `<upstream>`, found in this order:

1. `$OLD_TIP_<k-1>` recorded earlier in this run (cascade);
2. `origin/<old-base>` if that branch still exists on the remote;
3. else `git merge-base HEAD origin/<old-base-or-backup>` / `git reflog show origin/<old-base>` / the
   `backup/<old-base>-*` branch;
4. else the parent of this branch's first own commit (its real fork point).

Confirm it with `git merge-base --is-ancestor <upstream> HEAD` and read
`git log --oneline <upstream>..HEAD` — it must be **this PR's own commits only** — before rewriting.
When the predecessor was squash-merged into `REMOTE_BASE`, this is what makes its commits drop out.

**Do the same to the local branch.** The branch being rebased *is* the local branch; after the rebase
it must also agree with the remote everywhere else:

- the local branch's upstream/tracking still points at `origin/<branch>` (`git branch -vv`);
- **this PR's changeset** `## Stack Context` → **Base** is updated to `REMOTE_BASE` (this PR's own
  changeset only, as `/repoint` does) and committed with the push;
- a local-only branch that **was** the old base and is now merged/superseded is left alone — never
  delete it (a successor may still base on it), just report it as stale;
- `gh stack view` is re-checked in Step 5; if the stack object still shows the old parent, say so and
  point at `gh stack sync` — this command never edits the PR base itself (that is `/repoint`).

In cascade mode, run 2b for **every** layer up front and show the user any layer whose remote base
drifted **before** rewriting anything: a repointed layer changes which layers are contiguous, and a
layer repointed onto `master` is no longer a successor of the layer below it.

## Step 3: Choose where each layer is rebased — the cascade's core rule

**A branch is only ever rebased from a worktree that owns it.** Per layer, in order:

### 3a. Delegate — a worktree already pins this branch

```bash
W=$(git worktree list --porcelain | awk -v b="refs/heads/$BRANCH" '
  /^worktree /{p=$2} $0=="branch "b{print p}')
```

If `$W` is non-empty, run that layer's whole rebase **inside that worktree** with `git -C "$W" …`.
This is the case that matters most, and it comes with a hard gate — **that worktree may belong to
somebody mid-`/green`**:

```bash
git -C "$W" status --porcelain | grep -v '^?? '                  # must be empty
git -C "$W" rev-list --count "origin/$BRANCH..$BRANCH"           # must be 0 — nothing unpushed
```

If either check fails, **STOP the whole cascade** and report which worktree and why. Rebasing under
somebody's uncommitted or unpushed work destroys it, and no amount of "it was probably fine" makes
that recoverable. Offer: they commit and push, or they run single-mode `/pr-stack-rebase` there
themselves.

### 3b. Borrow — no worktree pins this branch

Check the branch out **here**, rebase, push, and move on. This is safe precisely because nothing else
holds it:

```bash
git fetch origin "$BRANCH"
git checkout "$BRANCH"
```

Restore `$ORIGINAL_BRANCH` when the cascade finishes — see Step 6. Borrowing switches the working
tree, so `node_modules`, `dist`, `src/protogen` and venvs may no longer match; the build/test step
of that layer may need a reinstall, and a layer whose build cannot be verified must say so rather
than claim green.

### Never

- Never update a pinned branch from **this** worktree — git refuses, and forcing past it is how
  concurrent work is lost.
- Never `git worktree add` a new worktree per layer here. Each costs **~7 GB** in this monorepo once
  dependencies exist. Borrow-and-restore is the cheap path; delegate is the correct one.
- Never rebase a layer whose PR is **merged or closed**. Skip it, say so, and continue from the next
  open layer.

## Step 4: Rebase one layer

Run these for the layer's branch, in the worktree Step 3 chose (`git -C "$W"` when delegating).

1. **Fetch only what is needed** (no trunk fast-forward, no `--all`):
   ```bash
   git fetch origin <base> <branch>
   ```
2. **Already current? Verify leak-free, then return without rewriting.**
   ```bash
   git merge-base --is-ancestor origin/<base> HEAD && echo CURRENT || echo STALE
   git log --oneline origin/<base>..HEAD                   # must be ONLY this PR's own commits
   ```
   - **CURRENT and the log is this PR only** → report "already current, leak-free, no rewrite", skip
     the backup and the rebase, **but still run Step 4b** — current locally is not the same as
     current on the remote. In single mode, continue from Step 5 afterwards. In cascade
     mode, **record this layer's tip as unchanged and move to the next layer** — a layer that did not
     move does not make its successor stale. (If Step 4b then *changed the remote tip* — a local-ahead
     branch got pushed — the layer did move for its successors: record it as **published**, and treat
     its successors as stale exactly as after a rebase.) Do **not** treat this as a skip of the command: the leak
     check *is* the work.
   - **CURRENT but the log contains predecessor commits** → ancestor work leaked into this range.
     This is the rewritten-base / wrong-merge-base case. Do **not** analyze those files as this PR's
     work and do **not** delete them to "clean" the diff. Use the `--onto` form below with the
     predecessor's previous tip as `<upstream>`.
   - **STALE** → continue; the branch does not contain the latest base tip.
3. **Backup branch** — cheap insurance before any history rewrite:
   ```bash
   git branch backup/<branch>-$(date +%Y%m%d-%H%M%S)
   ```
4. **Record this layer's pre-rebase tip — REQUIRED IN CASCADE MODE.**
   ```bash
   OLD_TIP_<k>=$(git rev-parse "origin/<branch>")
   ```
   **This is the mechanic that makes a cascade correct, and the reason running single mode N times by
   hand goes wrong.** Once layer K has been rebased, layer K+1's recorded merge-base is a commit that
   no longer exists on K. A plain `git rebase origin/<base>` at layer K+1 would then replay **K's old
   commits** as if they were K+1's own, silently duplicating the predecessor's work into the
   successor's diff. So each layer's `<upstream>` is the tip its base had **before** this run
   rewrote it.
5. **Rebase this branch only:**
   ```bash
   # first layer, base not rewritten by this run:
   git rebase origin/<base>

   # any layer whose base WAS rewritten by this run (every cascade layer after the first that moved),
   # or a base that was force-pushed earlier by somebody else:
   git rebase --onto origin/<base> "$OLD_TIP_<k-1>" <branch>
   ```
   When the base was rewritten by somebody else before this run and no `OLD_TIP` was recorded,
   recover it from `git reflog show origin/<base>` or the backup branch.

   Never `git rebase --update-refs` — it rewrites sibling stack branches all at once, which is the
   atomic, all-branches behaviour this command deliberately does not have.
6. **Resolve conflicts preferring this branch's own surface.** This PR owns its symbols; the base owns
   its own. On a shared catalog or index file, resolve by **union** — keep both contributions
   (see the recurring-conflicts section in the `pr-stack` skill). **Never implement a
   predecessor-owned symbol while resolving** — if the base's stub conflicts with your code, keep the
   stub. **Never delete predecessor-owned files or stubs to resolve a conflict.**

   **In cascade mode a conflict stops the run.** Resolve this layer, or abort it
   (`git rebase --abort`) and report — never continue to the next layer, which would rebase it onto a
   half-resolved parent. Say which layers were completed, which one stopped, and which were not
   attempted.
7. **Build and test** — package-level `build` / `type-check` / tests for the affected packages. Fix until the branch
   is in the same state it was before the rebase (green stays green; a still-red `/green` in progress
   stays red for the same reasons, not new ones). In cascade mode, report each layer's state
   separately; a layer whose build could not be verified (borrowed worktree, stale dependencies) must
   be reported as unverified, never as green.
8. **Reviewed-PR gate.** A rebase rewrites SHAs and requires a force-push, which can dismiss
   approvals under branch protection. If the layer's PR is **not a draft and has an approval**, say
   so and **ask before force-pushing that layer**. In cascade mode ask about all affected layers up
   front, in Step 3, rather than interrupting halfway through.
9. **Publish this branch only** — Step 4b, below. It is not optional and does not wait for the
   caller's own work to finish.

### Step 4b: Publish the rebased state — BEFORE the caller starts any work

The rebased (or verified-current) branch **must be on the remote before the caller's own work
begins.** `/green`, `/fix-pr`, `/pr-wrap` and the rest then start from a pushed baseline: a rebase
that lives only in this worktree is invisible to successors, to CI, and to every other worktree's
`/pr-stack-rebase`, and it is lost if the worktree is. This also runs on the already-current path,
where it covers a branch rebased locally earlier but never pushed.

```bash
# 1. Does the remote branch exist? Probe first — a fetch of a missing ref is an error, not a state.
if git ls-remote --exit-code --heads origin <branch> >/dev/null; then
  git fetch origin <branch>
  git rev-parse HEAD "origin/<branch>"                       # same SHA → nothing to push
  git merge-base --is-ancestor "origin/<branch>" HEAD && echo REMOTE-BEHIND   # we are ahead
  git merge-base --is-ancestor HEAD "origin/<branch>" && echo REMOTE-AHEAD    # remote has more
else
  echo NO-REMOTE
fi
```

| State | Action |
|---|---|
| `HEAD` == `origin/<branch>` | already published — nothing to do |
| `NO-REMOTE` | `git push -u origin <branch>` |
| `REMOTE-BEHIND` (remote tip is an ancestor of `HEAD`; only local is ahead) | `git push origin <branch>` — a plain push, no force |
| `REMOTE-AHEAD` (`HEAD` is an ancestor of the remote tip) | **STOP — never push.** Another worktree or person pushed commits this one lacks. Refresh this branch from the remote (`git merge --ff-only "origin/<branch>"`, then re-run the leak check and Step 4.2) before anything else |
| Diverged (neither is an ancestor of the other) | Push **only if this run rewrote the branch** *and* `origin/<branch>` still equals the pre-rebase tip recorded in item 4 (a recorded tip is the proof that the remote holds nothing but the history this run replaced): `git push --force-with-lease=<branch>:<recorded-old-tip> origin <branch>`, after the Reviewed-PR gate (item 8). Anything else — an already-current branch that diverged, or a remote tip that is not the recorded one — is **STOP**: someone else's commits are on the remote; report, never force |

The explicit `--force-with-lease=<branch>:<sha>` form matters: bare `--force-with-lease` trusts the
remote-tracking ref Step 4b just fetched, so it would happily "lease" a newer tip and overwrite it.

The leak check (Step 4.2) has passed by now and the tree is clean (Step 1), so only this PR's own
commits go up. Never plain `--force`, never `--no-verify`, never push a branch other than the layer
being processed, and never push several branches atomically. If the push is rejected, re-fetch and
re-evaluate the table — the remote moved; never escalate to `--force`.

**If the branch could not be published** (reviewed-PR gate answered no, push rejected, remote ahead or
unexplained divergence), **stop and
tell the caller: nothing is published, so it must not start its work.**

## Step 5: Report successors as stale

Rebasing a branch leaves every successor **outside the processed set** on a stale parent —
`gh stack view` will mark them `⚠`. That is expected, not a defect: each such successor's own
worktree clears it with single-mode `/pr-stack-rebase`. Name them in the output so the user knows who
runs it next.

In cascade mode this applies only to layers **above the top of the range** — the layers inside the
range were just brought current by the run itself. Skip the step entirely for any layer that Step 4.2
reported already-current **and** Step 4b left the remote tip unchanged; a layer whose remote tip moved
because 4b published it counts as moved — its successors are stale, name them.

Then check the topology (read-only, safe from any worktree):

```bash
gh stack view
```

## Step 6: Restore the borrowed worktree — MANDATORY in cascade mode

If any layer was borrowed (Step 3b), this worktree is sitting on a stack branch and **pinning it**,
which blocks whoever should be greening it:

```bash
git checkout "$ORIGINAL_BRANCH"
git branch --show-current      # must equal ORIGINAL_BRANCH
```

Do this **even when the cascade failed part-way** — an aborted run must not leave the worktree
parked on somebody else's branch. Confirm the restore in the report. Never delete a stack branch:
a successor bases on it, and deleting it closes that PR.

## After the rebase

Report:

- **which mode ran**, and for cascade, the resolved layer list bottom-up and how `#N` was read
  (stack position vs PR number);
- the resolved base for each layer and **which rule resolved it**, and whether the **remote PR base
  differed** (Step 2b) — old base → remote base, and the `<upstream>` used for `--onto`;
- per layer: **already current vs rebased**, where it ran (**delegated** to which worktree path, or
  **borrowed** here), old → new HEAD SHA (or unchanged), and the commits in `origin/<base>..HEAD`
  (that PR's own delta only);
- whether each layer's leak check passed (commit range is that PR only);
- conflicts resolved and how;
- build/test state per layer — explicitly flagging any layer reported **unverified**;
- **which successor branches now need their own `/pr-stack-rebase`, and in what order** (none when
  everything in range was already current);
- whether a force-push may have dismissed an approval (and the `#skipreview` re-trigger if so);
- **for cascade: that `$ORIGINAL_BRANCH` was restored**, and any layer skipped (merged/closed) or not
  attempted (stopped at a conflict).

## Rules

- **One branch rewritten at a time, always from a worktree that owns it.** Delegate with `git -C` to
  the worktree that pins it; borrow this worktree only when nothing pins it.
- **Never rewrite a branch pinned by another worktree from here**, and **never** proceed when that
  worktree has uncommitted or unpushed work — stop the cascade and report.
- **Cascade runs bottom-up and stops at the first conflict or failure.** Never continue onto a
  half-resolved or stale parent.
- **In cascade mode, each layer after a rewritten base uses `git rebase --onto <base> <recorded
  pre-rebase tip>`.** A plain rebase there duplicates the predecessor's commits into the successor.
- **Restore `$ORIGINAL_BRANCH`** when cascade mode borrowed this worktree — including after a failure.
- **Publish before the caller works.** A rebased or verified-current stack branch is pushed (Step 4b)
  before `/green`, `/fix-pr`, `/pr-wrap`, etc. begin; an unpublished baseline blocks them.
- **Hard-gate callers use single mode only.** `/green`, `/green-attack`, `/validate-changes`, and
  `/pr-wrap` never widen into a cascade; a ⚠-free view is not a skip, and already-current is
  verify-and-publish, not a rewrite.
- Never run `gh stack sync` / `gh stack rebase` from a per-PR worktree.
- Never `git worktree add` a worktree per layer — ~7 GB each in this monorepo.
- Never rebase a merged or closed PR's branch; skip it and say so.
- Never delete a stack branch — a successor bases on it, and deleting it closes that PR.
- **Always compare against the live remote PR base** (Step 2b). If it was repointed, the remote wins and
  the branch is rebased `--onto` the new base using the old base's tip as upstream — never plain rebase.
- Never `--force` (use `--force-with-lease`), never `--no-verify`, never amend, never
  `git rebase --update-refs`.
- Never implement a predecessor-owned symbol while resolving conflicts.
- Never delete predecessor-owned files or stubs to "clean" a leaked diff — rebase (or `--onto`) instead.

## Related

**Commands**: `/merge`, `/repoint`, `/plan-pr-stack`, `/add-to-pr-stack`, `/split-pr-to-stack`,
`/green`, `/green-attack`, `/validate-changes`, `/pr-wrap`, `/fix-pr-stack`, `/merge-pr-stack`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
