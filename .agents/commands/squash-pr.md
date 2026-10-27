---
description: Squash-land a PR - to origin/master (common), or fold it into its base PR (rare, 2 PRs → 1); detects the ambiguity and asks. Offers to repoint any open successors and deletes the branch once nothing references it
---
## Squash PR

Squash a PR's commits and land it. The **target** of a squash-merge is always the PR's **base**, so
for a stacked PR the target is ambiguous — this command detects that and **asks** before doing
anything destructive.

Load the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`) for the stack model, the `gh stack`
tooling contract, base tracking, and the golden rules referenced below.

> **On a registered stack, prefer `gh stack` for the repoint/restack half of this.** After landing a
> PR, `gh stack sync` moves the remaining branches onto the advanced trunk and retargets them in one
> atomic push — safer than repointing successors one at a time. Check first with `gh stack view`; the
> manual repointing below is the fallback for an unregistered stack. Note that a branch pinned by a
> worktree cannot be rebased, so free them before syncing.

## Step 1: Resolve the PR, its base, and its successors — MANDATORY

- Identify the PR (current branch by default, or a branch/number passed as an argument).
- Resolve its base per `pr-stack.md`
  (arg → `gh stack view --json` → this PR's changeset `## Stack Context` → `gh pr view <branch> --json baseRefName`).
- **Note whether the PR belongs to a registered stack** — it changes how successors are handled:
  ```bash
  gh stack view 2>/dev/null || echo "not a registered stack"
  ```
- Fetch the base PR's status (if the base is a branch with an open PR):
  ```bash
  repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
  gh pr view <base-branch> --json number,state,url,mergeStateStatus 2>/dev/null
  ```
- **Detect successors** — open PRs whose base is **this** branch. They decide both the repoint offer
  and whether the branch is safe to delete (Step 4); deleting a branch a successor still bases on
  **closes** that successor (golden rule 2):
  ```bash
  gh pr list --state open --base <this-branch> --json number,headRefName,url \
    --jq '.[] | "#\(.number) \(.headRefName) \(.url)"'
  ```

## Step 2: Check CI status (and optional skip-review)

**Always check CI before landing** — a squash-merge (Case A or B) must not run against a red or
still-pending PR:

```bash
gh pr view <N> --json statusCheckRollup,mergeStateStatus,reviewDecision \
  --jq '{checks: ([.statusCheckRollup[].conclusion] | unique), merge: .mergeStateStatus, review: .reviewDecision}'
```

- Checks **failing** → stop and report; do not squash.
- Checks **pending** → wait for them to settle (poll), or report and ask before proceeding.

**Skip-review — only when the user explicitly asked for it.** If (and only if) the `/squash-pr`
invocation contains a skip-review reference (e.g. `skip review`, `skipreview`, `#skipreview` in
`$ARGUMENTS`), post the token so the CI/merge infra opens the PR for merge, then **await** that:

```bash
gh pr comment <N> --body '#skipreview'
# await the CI infra opening the PR for merge (mergeStateStatus → CLEAN)
for i in $(seq 1 12); do
  s=$(gh pr view <N> --json reviewDecision,mergeStateStatus --jq '.reviewDecision+" "+.mergeStateStatus')
  echo "$s"; case "$s" in *CLEAN*) break;; esac; sleep 6
done
```

Do **not** post `#skipreview` unless the user explicitly referenced skip-review in the command — it
bypasses the review gate. A later conflict-resolution commit dismisses the approval, so re-post after
any such commit (see the approval-dismissal note in `.agents/skills/pr-stack/SKILL.md`).

## Step 3: Choose behavior by base

### Case A — base is `origin/master` (common)

Squash-land straight to master:

```bash
gh pr merge <N> --squash            # no --delete-branch here — successors + deletion are handled in Step 4
```

**Golden rule:** do **not** `--delete-branch` in this call. Successors (Step 1) may base on this
branch; deleting it while one is open closes that PR (unreopenable). Hand off to **Step 4**, which
offers to repoint successors and then deletes the branch once nothing references it. The new base for
any successor here is `origin/master`.

### Case B — base is another (open) PR branch (rare) — ASK, do not assume

A plain squash-merge here would merge **this PR into its base PR** (the base branch absorbs this PR's
squashed commit; this PR closes as merged; the base PR's diff grows to cover both). That collapses
**2 PRs → 1** — which may or may not be intended. **Ask the user which they meant:**

> This PR's base is the open PR **#\<base-N\> (\<base-branch\>)**, not master. Did you intend to:
> **(A) Land this PR to master** — `/repoint` it onto `origin/master` first, then squash-merge; both
>   PRs stay separate. *(repoint + squash)*
> **(B) Fold this PR into its base PR** — squash this PR's commits into `\<base-branch\>`, closing this
>   PR and making the base PR contain both. *(2 PRs → 1)*

**Wait for an explicit answer.** Then:

**If (A) repoint + squash:**
1. Run `/repoint` to move this PR's base to `origin/master` and restack.
2. `gh pr merge <N> --squash` (now lands to master). Then go to **Step 4** for successor repoint +
   branch deletion (new base for successors = `origin/master`).

**If (B) fold into base PR:**
1. Confirm the base PR is the intended combine target and is still open.
2. Squash-merge this PR into its base branch as-is:
   ```bash
   gh pr merge <N> --squash        # base is <base-branch>, so this folds into the base PR
   ```
   (Equivalently: `git checkout <base-branch> && git merge --squash <this-branch> && git commit && git push`.)
3. **Successor handling** — defer to **Step 4**; the new base for any successor here is
   `<base-branch>` (the branch this PR folded into), not master.
4. Update the base PR's title/body to reflect the combined scope, and merge this PR's changeset/PRD
   content into the base PR's docs (respecting the forward-only linking rule — the base is the
   predecessor).
5. Note in the base PR's changeset `## Stack Context` that this PR folded into it, and correct its
   `k of n`. This PR's own changeset went with its content in step 4 — there is no shared document to
   prune.

## Step 4: Successors — repoint (opt-in) and branch deletion

After the squash-merge lands, resolve the fate of this PR's branch and any **successors** (Step 1).
The new base for successors is `origin/master` (Case A) or `<base-branch>` (Case B).

### 4a. Successor repoint (opt-in)

If open PRs base on this branch, deleting it would **close** them (golden rule 2). List them and let
the user **opt in** to repointing each onto the new base:

> This branch has open successors: **#\<n\> \<branch\>**, … Repoint them onto **\<new-base\>** so they
> stay open and their diffs stay clean? *(all / pick which / none — leaving them keeps this branch)*

- **Opt in** → run `/repoint <new-base>` for each chosen successor (changes base via REST API +
  restacks). Do this **after** the squash-merge landed, so the merged commit drops out of each
  successor's diff. If the squashed PR belonged to a stack, update the successors' changeset Stack Context and PR bodies' `## Stack` blocks afterwards so the merged node leaves the wave records — removing every dependency edge that has the merged node as an endpoint. No epic issue is created for a stack: topology is the `gh stack` object + PR bases; waves/edges live in each changeset's Stack Context and PR body's Stack block.
- **Decline (or no successors chosen)** → leave those successors as-is. The branch still has open
  references, so it MUST NOT be deleted (skip 4b for it).

### 4b. Branch deletion (default when safe; opt-out)

**Delete the squashed branch once no open PR still bases on it** — this is the default. Re-check after
any repoints:

```bash
gh pr list --state open --base <this-branch> --json number --jq 'length'   # must be 0 to delete
```

- Result `0` → delete the branch: `git push origin --delete <this-branch>` (drop the local branch too
  if it lingers: `git branch -D <this-branch>`).
- **Opt-out:** if the user asked to keep it (e.g. `keep-branch` / `--no-delete` / "don't delete" in
  the invocation), skip deletion and say the branch was kept by request.
- **Still referenced** (user declined a repoint) → **keep the branch** and report that it survives
  because open successors depend on it.

Never pass `--delete-branch` to `gh pr merge` — branch deletion happens here, only after 4a is
resolved.

## Step 5: Report

State the CI status that was verified, whether `#skipreview` was posted (only if the user asked) and
that the PR reached a mergeable state, which case ran, the squash target (master or the base PR),
which successors (if any) were offered and which were repointed, whether the branch was deleted / kept
by request / kept because it is still referenced, and the resulting open-PR set
(`gh pr list --state open`). Never use `--no-verify`.

## Related

**Commands**: `/repoint`, `/merge`, `/plan-pr-stack`, `/pr-wrap`, `/wrap-context-docs`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
