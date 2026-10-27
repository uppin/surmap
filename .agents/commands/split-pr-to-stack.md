---
description: Split a PR (or unpushed branch) into a stacked PR sequence with correct bases - A→B→C split B becomes A→B1→B2→C
---
## Split PR to Stack — Carve one PR into stacked PRs

Turn **one** branch/PR into a **stack** of smaller PRs, each based on its predecessor — not on
`master`. This is the stacked counterpart of `/split-branch`.

Load the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`) first — it defines the stack model,
the `gh stack` tooling contract, base tracking, per-changeset stack context, the forward-only doc
linking rule, the golden rules (a deleted base branch **closes** its dependent PR), and the
worktree-pinning constraint. This command assumes those definitions.

**Use this, not `/split-branch`**, when the slices must land as dependent PRs
(`B1` mergeable first, `B2` based on `B1`). `/split-branch` produces sibling branches, typically
both off `master`, and does not register a stack.

**Use `/plan-pr-stack`**, not this command, when the work is not written yet and you are planning a
stack from requirements (PRD + changeset + stubs + failing tests per PR). This command carves up
**existing** commits/files.

`$ARGUMENTS` may name the PR/branch to split (`#123`, a URL, a branch) and/or describe the two
slices. Default: current branch. **This command always produces exactly two new layers (B1, B2).**
A third slice is a second invocation, on B1 or B2. Confirm the distribution before touching git.

## Topology this command produces

```
Before (B may or may not have a PR; C, D may or may not exist):

  A  →  B  →  C  →  D
        ▲
     the PR/branch being split

After:

  A  →  B1  →  B2  →  C  →  D
        ▲       ▲
   B's existing    new PR
   PR (kept)       (base = B1)
                   C's base moves B → B2
                   D's base stays C (C is rewritten; D is rebased onto the new C)
```

- **B1** is the **same GitHub PR as B** when B already has one (same number, same head branch, same
  predecessor A). Its diff shrinks to the bottom slice. Do **not** close B and open two new PRs —
  that drops review history.
- **B2** is a **new** branch + PR whose base is B1. After the split, **B2's tree equals original B**
  so C rebases onto it without picking up a second copy of B1.
- **The stack successor of B** (C) is retargeted onto **B2**. Descendants further down (D, …) **keep
  their existing parent** — D stays based on C — but each must be rebased onto that parent's new tip.
  Never leave C basing on B1: its diff would swallow B2.
- **A** is unchanged. Resolve it — it is **not** always `master`.

If B has **no PR**, both B1 and B2 are created as a registered 2-PR stack, with B1 based on the
resolved predecessor A (which may itself be an open PR).

A GitHub stack is **linear**. Two open PRs that both base on B are **siblings**, not a chain. Stop
and ask; do not feed them both to `gh stack init`.

`gh stack modify` **cannot split a branch** (it can only insert an empty one). Do not use it here.
`gh stack add` only appends on **top** — wrong when C already sits above B.

## Step 0: Preflight — `gh stack` is REQUIRED

```bash
gh auth status
gh extension list | grep -q 'github/gh-stack' && gh stack --version
```

If the extension is missing, **stop**. Do not fall back to plain `gh pr create`. Ask the user to
install it (`gh extension install github/gh-stack`) rather than installing it yourself.

Also:

```bash
git status --porcelain                 # uncommitted tracked files → commit first, never stash silently
git branch --show-current
git worktree list
gh stack view 2>/dev/null || echo "not a registered stack"
```

Worktree pinning is re-checked in Step 1d **after** A, B, the successor chain, and trunk are known —
and again immediately before `unstack` / `init` in Step 6. Do not unstack while any of those refs is
pinned.

## Step 1: Resolve B, A, the successor chain, and local refs — MANDATORY

### 1a. Resolve B and A

Identify **B** from `$ARGUMENTS` or the current branch:

```bash
gh pr view <B> --json number,url,title,isDraft,state,baseRefName,headRefName,reviewDecision
```

- **PR exists** → `headRefName` is B, `baseRefName` is the GitHub base (candidate for A).
- **No PR** (`gh pr view` fails) → B is the current (or named) branch. Resolve A with the
  base-tracking order from the `pr-stack` skill:
  1. Explicit argument.
  2. Registered stack — `gh stack view --json` (this branch's parent).
  3. This branch's changeset — `## Stack Context` → **Base**.
  4. `git merge-base` / upstream vs `origin/master` — **ask** if it is not obvious.
  5. **Never silently default to `master`.** If B was cut from an open PR, A is that PR's head.

### 1b. Materialize every needed branch locally

`gh pr view` can succeed for a URL/number while `git rev-parse` / `checkout` / `rebase` fail if the
ref is remote-only. **Fetch and create a local branch** for B, for A when A is a branch (not trunk),
and for every successor discovered in 1c. Do this **before** any `git rev-parse` of those names.

```bash
git fetch origin <branch>
if git show-ref --verify --quiet "refs/heads/<branch>"; then
  git merge-base --is-ancestor "origin/<branch>" "<branch>" \
    && echo "<branch> contains origin/<branch>" \
    || { echo "local <branch> does not contain origin/<branch> — stop, do not force-update a diverged local"; exit 1; }
else
  git branch --track "<branch>" "origin/<branch>"
fi
```

If the local branch has **unpushed** commits the remote lacks, **stop** and ask — never discard them
to match origin. A registered stack can also be materialized with `gh stack checkout <PR#>` (that
checks the branch out; free it again before Step 6).

### 1c. Walk the successor **chain** — stop on siblings

A stack is one line. Discover descendants of B by walking **one child at a time**:

```bash
# Direct children of a branch:
gh pr list --state open --base <branch> --json number,headRefName,url
```

1. List open PRs whose base is **B**. Cross-check `gh stack view` for stack members that are not
   yet PRs — they still belong in the chain.
2. **Zero children** → B is the top; chain is empty.
3. **Two or more children** → **siblings**. **Stop.** Do not pass them as one list to
   `gh stack init` (that either fails or makes one sibling depend on the other, changing its base
   and diff). Ask which PR is the successor **in this stack**. The others stay **outside** this
   stack as a separate branch/stack. Default: rebase and retarget each non-chosen sibling onto
   **B2** (B2's tree equals original B, so their diff is unchanged) — do **not** leave them on B1
   (B1 is the shrunken slice; their diff would swallow B2). Only leave a sibling on B1 if the user
   explicitly wants it based on the B1 slice alone. Do not put any sibling in this stack's `init`
   list.
4. **Exactly one child** → that is C. Append it to the chain. Repeat from C: exactly one child →
   D, and so on. If any later layer has two or more children, **stop** the same way (fork below C).

The chain is `[C, D, …]` in stack order. Record each member's **original tip SHA**
(`orig_C`, `orig_D`, …) after 1b, before any rewrite. State A, B, the chain, sibling decisions, and
whether B already has a PR **before** splitting.

### 1d. Free every branch Step 6 will move — before any rewrite

`gh stack init` / `sync` / `rebase` cannot update a branch pinned by a worktree, including **A**
(when A is in the init list) and **trunk**. On the registered-stack path, discovering this *after*
`unstack` means the GitHub stack object is already gone.

Build the pin-set: **trunk** (usually `master`), **A** (if it is a branch in this stack), **B**,
the to-be-created **B2**, and **every chain member**.

```bash
git worktree list
```

If any pin-set branch is checked out in **another** worktree, free it (or run from a worktree that
does not pin them). If **this** worktree is on a pin-set branch, that is fine through Step 5 (the
git split checks B out); **switch off every pin-set branch, including trunk, before Step 6**.

## Step 2: Agree the two slices — MANDATORY

Do not split until the user confirms:

1. **What stays on B1** (bottom slice — independently mergeable, lands first).
2. **What moves to B2** (top slice — based on B1).
3. **Branch name for B2** — it **must** be `pr-<k>-<slug>` with `k` an integer: the `gh stack` object and each changeset's node numbers find a
   stack's nodes by that pattern, so `<B>-2` or `pr-<k>b-<slug>` makes B2 invisible to the stack.
   When B is the **top** of the stack, B2 is `pr-<K+1>-<slug>`. When B has successors there is no
   free integer between B and C: the successors' branches would have to be renamed too — a larger,
   consented operation, so stop and ask rather than pick a non-conforming name. **Keep B's branch
   name as B1** so the existing PR's head does not move.
4. **Independence check.** B1 must not call symbols that only exist on B2. If it currently does,
   those calls belong on B2, or the split is inverted. Do not paper over this with a fallback.
   Compile-only stubs are allowed only when B1 must *name* a successor API it does not implement
   — the stub is **owned by B2** (see the `pr-stack` skill). Prefer moving the call up to B2.

**Exactly two layers.** If the user wants B3, say so and stop: finish this split, then run
`/split-pr-to-stack` again on B1 or B2. Do not invent a third branch in this invocation.

Present the proposed topology (`A → B1 → B2 → [C → D → …]`) and wait for approval.

## Step 3: Backup and split document

**Keep backups frozen (never modify):**

```bash
ts=$(date +%Y%m%d-%H%M%S)
git branch backup/${B}-${ts} <B>
# backup every chain member that will be rebased (C, D, …)
```

Record `orig_B=$(git rev-parse <B>)` and `orig_<X>` for each chain member. Create
`tmp/split-pr-stack-${ts}.md` (do **not** add to git) with: original SHAs, A/B/chain branches and PR
numbers, the two slice lists, sibling decisions, and a checklist of the procedure below.

## Step 4: Git split — B2's tree must equal original B

Work in **one** worktree. B is checked out here; other worktrees must not pin the pin-set.

```bash
orig_B=$(git rev-parse <B>)
git branch <B2> "$orig_B"            # B2 starts as a copy of original B
```

**4a. Shrink B to B1** (bottom slice only):

```bash
git checkout <B>
# Remove B2-only files/changes. Shared files keep the B1 version.
git add -A
git commit -m "Split: keep [B1 slice] on this PR"
```

Never `--no-verify`. B1 must **type-check / build**. If it does not, stop — the slice boundary is
wrong, or a B2-owned stub is missing. Do not force-push a broken B1.

**4b. Point B2 at B1 and commit only the B2 delta**, preserving original B's tree:

```bash
git checkout <B2>
git reset --soft <B>                 # HEAD = B1; index + worktree still orig_B
git commit -m "Split: [B2 slice] stacked on predecessor"
```

**Invariant — verify before continuing:**

```bash
git diff "$orig_B" <B2>              # MUST be empty: B2 tree == original B
git log --oneline <A>..<B>           # B1's own commits only
git log --oneline <B>..<B2>          # B2's own commits only
```

If the diff against `orig_B` is not empty, the split corrupted the combined tree and successors
will not rebase cleanly. Fix or restore from backup before touching GitHub.

**4c. Rebase the full successor chain**, each onto **its own parent**'s new tip. Direct children
only is not enough: after C is rewritten, D (based on C) is stale until it is rebased onto the new
C.

```bash
# C was based on orig_B; replay C's unique commits onto B2
git rebase --onto <B2> "$orig_B" <C>
# D was based on orig_C; replay D's unique commits onto the new C (not onto B2)
git rebase --onto <C> "$orig_C" <D>
# …one hop at a time, chain order, preserving each descendant's parent
```

If a hop conflicts, restore from backup and re-examine the slice (usually a shared file that no
longer composes to `orig_B`). Do **not** rebase D onto B2 — that would fold C into D's diff.

Non-chosen **siblings** of C (Step 1c) are rebased the same way as C (`--onto <B2> "$orig_B"`) unless
the user asked to leave them on B1. They are not chain members.

**4d. Build / test each rewritten branch** (B1, B2, every rebased chain member). B1 must be
independently mergeable: its tests must not assert B2 behaviour.

## Step 5: Point the GitHub bases — PRs that already exist

Retarget via the **REST API**, not `gh pr edit --base` (that can fail with a *"Projects (classic)
is being deprecated"* GraphQL error in some  orgs):

```bash
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X PATCH "repos/$repo/pulls/<N>" -f base=<new-base> --jq '"#<N> base→"+.base.ref'
```

Order — **move C onto B2 on GitHub before rewriting B's remote**. Otherwise C stays based on B
while B shrinks to B1, and C's PR diff swallows B2:

1. **Push B2** (`git push -u origin <B2>`). Do not open its PR yet if you will use `gh stack submit`.
2. **Retarget only the direct stack successor C** from B → **B2** (REST API above). **Do not**
   retarget D, E, … — their base stays their current parent. Force-push the rebased chain
   **bottom-up** (`C`, then `D`, …) with `--force-with-lease`, back-to-back with C's retarget so C
   is never publicly based on a head whose tree does not match. Golden rule: never delete B.
   After this, C's diff is unchanged because B2's tree equals original B, and D's diff is unchanged
   because it still diffs against C.
3. **Force-push B1** (`git push --force-with-lease origin <B>`). B's existing PR now diffs against
   A as the B1 slice. Warn first if the PR is not a draft and has an approval — a force-push can
   dismiss it.

If the chain is empty, skip step 2. If B had **no PR**, there is no GitHub PR to retarget and no
force-push of B1 yet — push B1 and B2 with `git push -u` so Step 6's `gh stack submit` can create
both PRs with the correct bases.

Siblings left outside this stack (Step 1c) default to **B2** (rebase `--onto <B2> "$orig_B"` and
retarget base B → B2) so their diff stays the original-B delta. They are **not** in this stack's
`init` list. Only keep a sibling on B1 when the user asked for the B1 slice as its base.

## Step 6: Register the stack — MANDATORY

The stack is not delivered until GitHub knows the new order. `gh stack add` / additive `link` will
**append B2 on top of the current top**, which is wrong. Recreate with an explicit **linear**
bottom-to-top list: A (if in this stack), B1, B2, then the chain `C D …`. **Never** put sibling
heads in that list.

**Immediately before `unstack` / `init` / `sync` / `submit`:** re-read `git worktree list`. The
pin-set from Step 1d (trunk, A, B1, B2, every chain member) must all be free, **including this
worktree** — check out a non-pin-set ref (detached `origin/<trunk>` is fine) first. Do not unstack
while any of them is pinned.

**PRs do not exist yet** (typical no-PR split, or B2 not yet opened):

```bash
gh stack init <A-if-it-is-in-this-stack> <B1> <B2> <C> <D> ... --base <trunk-of-this-stack>
gh stack view                    # confirm A → B1 → B2 → C → D, no ⚠
gh stack submit --auto           # creates missing PRs as DRAFTS; never --open
```

`--base` is the trunk **below** the bottom PR of this stack (usually `master`). If A is itself an
open PR in an existing stack, A belongs **in the `init` list**, not as `--base`. Do not start a
second stack whose bottom is A while A already lives in another stack — adopt the predecessor's
stack so there is one chain.

**PRs already exist** and the stack is **already registered**:

`submit` / `link` are **additive** (new PRs go on top; they will not insert B2 between B and C).
**Ask** to recreate the stack object. Explain: the PRs stay open; only the stack grouping is
rebuilt. `gh stack unstack` without `--local` removes the GitHub stack object — that is the point,
and it needs explicit consent (see the `pr-stack` skill). Then:

```bash
gh stack unstack                 # after consent AND after the pin-set is free
gh stack init <A...> <B1> <B2> <C> <D> ... --base <trunk>
gh stack view
gh stack sync                    # all PRs exist: restack + link, does not flip draft state
# If B2 still has no PR, use `gh stack submit --auto` instead of sync.
```

If the user **refuses** to unstack: still complete Step 5 (PR bases are what reviewers see) and
report that the GitHub stack object still has the old grouping. Do not pretend the stack is
registered in the new order.

**PRs already exist** but there was **no** registered stack: `gh stack init` … then `gh stack sync`
(or `submit --auto` if B2 has no PR yet). No unstack. Same pin-set rule.

Confirm:

```
✓ Stack created on GitHub with N PRs
```

Then `gh stack view` — order is `A → B1 → B2 → [C → D → …]`, every row `○` or `◎`, **no ⚠**.

Verify each PR shows **only its own files**:

```bash
gh pr view <N> --json number,isDraft,baseRefName,changedFiles \
  --jq '"#\(.number) draft=\(.isDraft) base=\(.baseRefName) files=\(.changedFiles)"'
```

B1's base is A, B2's base is B1, C's base is B2, D's base is C. A file count on C that includes B2's
work means C was not retargeted. A file count on D that includes C means D was not rebased onto the
new C (or was wrongly retargeted onto B2).

## Step 7: Update changesets (when they exist)

There is no shared `STACK-*.md`. Each PR's own changeset carries `## Stack Context`.

- **B1** (existing changeset, if any): successor is now B2 (not C). Add `## Successor PRs` linking
  **forward** to B2's docs. Owned API surface = the B1 slice.
- **B2**: new (or split-out) changeset, started per the `pr-lifecycle` skill § *Start a changeset*, with
  `## Stack Context` (base B1, successor C or `none`) and `## Inherited Dependencies — do not
  implement here`. Do **not** link back to B1's docs (forward-only rule). Its `[wf]` rows are a copy
  of B's, each TODO kept with the half whose slice it belongs to, each status set by what B2's slice holds (§ *Step contract*, step 2); its Wrap row
  readies draft `#<N>`. B1 keeps B's rows, re-checked against its slice the same way.
- **C**: **Base** becomes B2. Do not add a back-link to B1/B2 docs.
- **D, …**: base unchanged (still the previous chain member). No back-links.

**Both halves need a `### Green wave`** — a split is where a wave most often changes, because the
whole point of most splits is that the bottom slice is startable and the top one is not:

- **B1** keeps B's wave when its own slice needs no predecessor behaviour. If B was above wave 1
  *because of work that went into B2*, B1 drops to the wave its remaining needs allow — usually
  wave 1, and that is the throughput the split bought.
- **B2** sits one wave above whatever behaviour it now needs from B1, and lists B1 under the
  dependency edges. If B2 needs nothing from B1 at *behaviour* level, both stay in the same wave and
  say so — same wave, one above the other in the line, is normal after a flattening.
- Each changeset states **its own** wave only, and `Concurrent with:` / `Blocks:` are updated on the
  PR that owns the row. `m` (the wave count) changes only if the split created a new wave.
- **Written in node numbers** (`n1 … nN`), as everywhere else. A split **inserts a node**, so every
  node above B2 shifts by one — the same shift their `K/N` titles get. Their wave rows are stale by
  that amount; each PR owns its own row, so report which need re-checking rather than editing them
  from here. Where the dependency is on what an already-open slice actually **contains**, write the
  PR number alongside the node: `n3 (#2403)`. See the `pr-stack` skill § *Node numbers*.
- Keep each half's wave consistent with its `Greenable independently?` line: wave 1 ⇔ `yes`.

A split does **not** re-derive the whole stack's line — the branches already exist. If it leaves a
wave no longer led by its blockers, report that to the user rather than silently reordering.

If there is no changeset, do not invent a full `/plan-pr-stack`. Report the gap; the GitHub stack
object is the topology source of truth.

Commit changeset updates on the branch that owns them, then push. Never `--no-verify`.

## Step 8: Retitle B1 and B2, and renumber the whole stack — MANDATORY

A split changes `K` for everything above B and `N` for everything in the stack, so every title's
trailing `(#<slug> K/N)` is now wrong. A stale position is read as fact, so this is not optional.
See **PR titles** in the `pr-stack` skill.

1. **Read the slug** from any changeset's `## Stack Context`. It was chosen at planning and does not
   change when a stack is split — B1 and B2 belong to the same stack B did.
2. **B1 keeps its PR number and gets a new subject**: it now delivers only the bottom slice, and its
   old title described the whole of B. Rewrite it to what B1 actually ships.
3. **B2 gets a title for the top slice**, same slug, position `K+1`.
4. **Renumber every other open PR** in the stack — subject unchanged, trailing group only.

```bash
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
gh api -X PATCH "repos/$repo/pulls/<pr>" \
  -f title="<type>(<pkg>): <subject> (#<slug> <K>/<newN>)" --jq '"#\(.number) → \(.title)"'
```

Use `gh api`, not `gh pr edit --title` (Projects-classic GraphQL fault in some  orgs).
**Skip merged PRs.** Their titles are already commits on `master`; editing the PR page only suggests
history was corrected when it was not.

Subjects must state the delivery **as shipped** — never `red`, `stubs`, `WIP`, `phase N`. Everything
after `: ` must be ≤ 100 characters including the trailing group.

## Step 8b: Revise the wave records — MANDATORY

Before syncing: (1) **B2's changeset** gets the same `## Stack Context` (`### Green wave`) as B1's — commit
and push it (a new commit, never an amend) rather than leaving it in the worktree; (2) **B2's PR
description** gets a `## Stack` block with `**Kind:**`; (3) B2's branch must be `pr-<k>-<slug>` (see Step 2).

The split adds node B2, changes B1's scope and moves every later `K/N`. No epic issue is created for a stack: topology is the `gh stack` object + PR bases; waves/edges live in each changeset's Stack Context and PR body's Stack block.
Update the affected changesets' Stack Context and PR bodies' Stack blocks in this run: the new node, B1→B2 and B2→C line
edges, **each dependency edge that pointed at or from B re-pointed to whichever slice actually
carries the dependency**, and every renumbered title. Verify with `gh stack view` that the recorded waves still match the PRs' `Wave k of m`. Report what changed.

## Output

```markdown
## Split PR → stack complete

### Topology
A (`<A>`) → B1 (`<B>`, PR #<n1>) → B2 (`<B2>`, PR #<n2>) → C (`<C>`, PR #<n3>) → D (`<D>`, PR #<n4>)

### GitHub
- Stack registered: yes/no — `gh stack view` (quote the created-with-N-PRs line)
- B1 is the original PR (kept): #<n1>
- B2 opened with base B1: <url>
- Direct successor retargeted onto B2: C
- Chain rebased onto new parents (bases unchanged below C): <D, …>
- Siblings left outside this stack: <none | list>
- Each PR `changedFiles` is its own slice: ✅/❌

### Invariant
- `git diff orig_B B2` empty: ✅
- No ⚠ in `gh stack view`: ✅

### Backups (FROZEN)
- `backup/<B>-<ts>` @ <sha>
- chain backups…

### Docs
- B1 / B2 / C Stack Context updated (base, successor, **green wave**): ✅ / none existed
- whether the split moved either half into a different green wave, and whether each wave is still
  led by its blockers

### Open
- Each half's remaining work is its own changeset's `## Workflow`; worktrees only for PRs being implemented
- Successors that were force-pushed may need `#skipreview` if an approval was dismissed
- Further slices: `/split-pr-to-stack` again on B1 or B2 (this command is two layers only)
```

## Recovery

```bash
git checkout backup/<B>-<ts>
# restore B, delete the failed B2 if needed
git branch -D <B2>
```

Do **not** delete B2 while any open PR still bases on it (C may). Retarget those PRs back to B
first. This command should not delete B at all.

## Rules

- **`gh stack` is required.** Never substitute a chain of `gh pr create --base` for a stack.
- **Never `--open`** on `gh stack submit` here; new PRs are drafts. Existing draft state stays.
- **Never `gh stack add`** to insert in the middle. **Never `gh stack modify`** (TUI, cannot split).
- **Never `gh stack unstack`** without explicit consent, and never while the pin-set is pinned.
- **Never delete a branch** an open PR still bases on.
- Keep B's existing PR as B1; create B2; retarget **only** the direct stack successor onto B2;
  rebase the rest of the chain onto their existing parents' new tips.
- **Stop on siblings** — two PRs with the same base are not one `init` list.
- **Exactly two layers** per invocation. Fetch remote heads before `rev-parse` / `checkout`.
- B2's tree **equals** original B before any successor rebase.
- Resolve A — never silently use `master`.
- Free trunk, A, B1, B2, and the whole chain before `unstack` / `init` / `sync`.
- Never `--no-verify`, never plain `--force` (use `--force-with-lease`).
- Do not add the `tmp/split-pr-stack-*.md` document to git.

## Related

**Commands**: `/split-branch` (sibling branches, not a stack), `/plan-pr-stack` (plan a stack from
scratch), `/add-to-pr-stack` (new draft PR on the tail, do not split), `/follow-up-branch` (branch
only on top, do not split), `/pr-stack-rebase`, `/repoint`, `/merge`, `/pr`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
**GitHub docs**: <https://gh.io/stacks>
