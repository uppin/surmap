---
description: Plan a stack of dependent PRs in two passes - interview each slice for its KIND (behaviour-adding / changing / preserving - feature, bugfix, migration, refactor, infra, test rebalance) and the verification method it can reach, group the PRs into green waves (wave 1 = startable immediately, wave k = unblocked once the waves below are green), derive the branch order from those waves with blockers leading each wave, then open every draft PR (including ground-softening / code-improvement nodes) with its changeset, discovery and - only where its kind warrants one - a PRD (commit 1), then revisit each PR bottom-up for the red step ITS kind calls for: stubs and failing tests for a feature, a reproduction for a bugfix, a plan.jsonl and a baseline for a refactor, a recorded proof for a migration or infra node (commit 2) - and finish with a cascade /pr-stack-rebase. Every node carries a changeset and a mandatory ## Verification section; a code change with no way to tell whether it worked does not get a branch. Every PR this command opens is a stack member. Each node must stay mergeable to trunk without breaking
production or local dev (local dev data may break; production data only with explicit planning consent).
---
## Plan PR Stack — From Requirements to a Stack of Draft PRs, in Two Passes

Alternative to `/plan-red` when the work is large enough to split across **multiple PRs planned
ahead**. Interview the user, decompose the work into an ordered stack, then build the stack in
**two passes**, both in the **current worktree**, one branch at a time.

**A stack is usually a mix of kinds, and each node is planned as the kind it is.** `/plan-red` is the
path for a node that *adds* behaviour; a bug fix, a migration, a restructure, an infra change or a
test rebalance each has its own planning command, its own artifacts and its own idea of what "red"
means — a reproduction, a `plan.jsonl`, a recorded baseline. What no node may skip is its
**changeset** (a stacked PR is picked up context-free, so it is the only carrier of the background)
and its **`## Verification`** section: tests wherever they reach, and where they genuinely cannot, a
named and executable proof. A node with a code change and no way to tell whether it worked is not an
acceptable PR, and it does not get a branch. See *Node kinds — settle one per node* and
*Verification* below.

**Trunk-merge safety — every node, non-negotiable.** A stack is not an excuse to land a broken
`master`. **Each PR must be mergeable on its own** (green CI, no dependency on a successor's
implementation) **and must not break production or local dev** when it is the only slice that lands.
That is separate from *independently greenable* (concurrent `/green` while predecessors are still
red) — see the `pr-stack` skill § *Two independence properties*. When a slice would leave production
or `uv run pytest -q` (and the usual local workflows for the touched packages) worse off until a successor
merges, the plan is wrong: add stubs, register routes with safe empty behaviour, gate incomplete
wiring behind a later node, or move the breaking change — do not ship "404 until n12". **Data:**
invalidating **local dev data** (reset DB, wipe caches, re-run migrations locally) is acceptable
without a separate ask. Anything that breaks or irreversibly migrates **production data** must be
surfaced in **Step 1** and recorded in the changeset (`## Stack Context → Trunk-merge safety` and,
when needed, `## Decisions & Trade-offs`) — never assumed OK.

- **Pass 1 — plan every PR (commit 1 of each).** For each PR in stack order: cut the stacked
  branch, write its own changeset + initial discovery (**plus a PRD when its kind warrants one**),
  commit those **docs only**, push, and **open the draft PR immediately** with `gh stack submit`.
  When pass 1 ends, every PR of the stack exists on GitHub, registered as a stack, with a one-commit
  planning branch each.
- **Pass 2 — red every PR, bottom-up (commit 2 of each).** Revisit PR₁ → PRₙ. For each: check it
  out, `/pr-stack-rebase` it onto its now-moved base, verify the build and record the baseline, then
  run **the red step this node's kind calls for** — for a feature node the `/plan-red` step (stub API
  it owns, failing acceptance tests, failing unit/integration tests); for a bug fix a reproduction;
  for a refactor a `plan.jsonl` and a baseline; for a migration or an infra node its recorded proof —
  verify that guardrail, and commit it as the PR's **second commit**. Push. The next layer's rebase
  picks those stubs up, which is what lets it compile against them. What each guardrail contains goes
  into the end-of-turn summary under **Decided without review** (Step 9), not into a mid-turn gate.
- **The changeset decides each node's workflow.** Every node's changeset carries `[wf]`
  rows filled from the preset for its kind (`.agents/skills/pr-lifecycle/SKILL.md`
  § *Presets*; the mapping is in *Node kinds* below). Commit 1 closes its Plan row, commit 2 its
  guardrail row; every later row is the node's own to run, and nothing in this command names it.
- **Completion gate.** When pass 2 ends, restore the starting branch and run a **cascade
  `/pr-stack-rebase` over the whole stack** (`from #1 to #n`). Every layer is expected to come back
  *already current, leak-free*; anything else is brought current before the stack is handed off.

Another agent may pick up any node's next `[wf]` row **only after the completion gate** — pass 2 rewrites
predecessors and rebases successors, and a branch pinned in another worktree cannot be checked out
here. After the gate, **this worktree is back on the branch it started on** — if that was `master`,
it must be on `master` again (a named branch checkout, not detached `origin/master` and not a stack
branch).

Load the `pr-stack` skill (`.agents/skills/pr-stack/SKILL.md`) first — it defines the stack model,
the `gh stack` tooling contract, base tracking, per-changeset stack context, the forward-only doc
linking rule, the worktree-pinning constraint, and the independence invariant. This command assumes
those definitions.

**Prerequisites**
- `gh` CLI authenticated (`gh auth status`).
- **`gh stack` extension installed** — see Step 0. The stack must end up registered on GitHub, not
  merely chained by base branches.
- User has described a body of work that plausibly spans more than one PR.

### Step 0: Preflight — `gh stack` is REQUIRED

```bash
gh auth status
gh extension list | grep -q 'github/gh-stack' && gh stack --version
```

If the extension is missing, **stop**. Do not fall back to plain `gh pr create` — that produces an
unregistered chain, which this command treats as incomplete. Ask the user to install it:

```bash
gh extension install github/gh-stack
```

Ask rather than installing it yourself: it changes their tooling, and external dependencies are the
developer's call. When they confirm, re-run the preflight and continue.

## Execution Flow

**Record the starting branch before anything else.** This worktree is the planning worktree — do
**not** create a second one — and it must be restored when the stack is complete, **including when
that starting branch is `master`**:

```bash
ORIGINAL_BRANCH=$(git branch --show-current)
TRUNK=master   # override after the interview if the user named a different trunk
git status --porcelain | grep -v '^?? '   # must be empty: no tracked-file changes
```

If `$ORIGINAL_BRANCH` is **empty**, HEAD is detached. **Stop.** A detached start cannot be restored
to a named branch in Step 7, and the worktree would be left on the top stack branch (pinning it).
Ask the user to check out a named branch first — usually `master`, or the trunk they intend to
return to.

If the tree has tracked-file changes, **stop** and ask the user to commit or stash them. If
`ORIGINAL_BRANCH` is already a stack branch from a previous attempt, confirm with the user before
continuing. `master` (or whatever named branch this worktree started on) is the common case — record
it and put this worktree back on that branch in Step 7; do not leave it detached or on a stack
branch.

### Step 1: Interview — MANDATORY

**A Roadmap page as the input.** When the invocation names a Roadmap tracker page
(`<service-url>`) — a roadmap, a spec, a plan someone published — load the
`roadmap-driven-development` skill (`.agents/skills/roadmap-driven-development/SKILL.md`) and read it
first (§ *Read the page*, § *Using a Roadmap page for a stack*): its items are the starting draft of
the slices, its order and stated dependencies the starting draft of the edges, and its open review
comments are requirements. **Its progress markers are claims** — check every item against the code
and GitHub (Rule 1) before the interview, and open the interview with the *Claims vs code* table: an
item the page calls done but the code lacks is a slice or a prerequisite, an item the code already
has is not a slice. With an item after the URL (`/plan-pr-stack <stash-url> <item>`, typically
from `/roadmap-red`'s size check) the stack covers that one item and the rest of the page is context.
Settle the page's mode (editable / manual, Rule 2) here too, and say in the
decomposition question what the plan will publish to the page and when. The page never replaces a
question below.

Run the interview from `.agents/skills/planning/references/planning-phase.md` **Step 1**
(What / Why / Where / Constraints / UX / Scope). Then ask the **stack-specific** questions:

1. **Decomposition** — What are the natural, independently-shippable slices? (e.g. API/proto →
   server → client; or data layer → service → UI.)
2. **Kind, per slice — ask it before the edges.** For each slice, one question about the diff it
   will produce: *what does it do to observable behaviour?* The answer is the slice's **family**, and
   the family decides which artifacts that node's pass 1 writes and what its pass-2 commit contains
   (`pr-stack` skill § *Node kinds*, and the matrix in *Node kinds — settle one per node* below).

   | Family | The diff | Kinds |
   |---|---|---|
   | **behaviour-adding** | behaviour that does not exist yet | Feature |
   | **behaviour-changing** | behaviour that exists and is wrong, or must become something else | Bug fix · contract change (behaviour-changing migration, deprecation, removal) |
   | **behaviour-preserving** | nothing observable changes; only the code that produces it moves | Refactor / restructure · mechanical migration · infra & toolchain · test rebalance · test-style migration |

   Ask it per slice and **never infer it from the stack's overall purpose**. A stack that exists to
   ship a feature routinely carries a bug fix under it and a migration beside it; planning those as
   features is what produces a PRD for a move nobody observes and acceptance tests that accept
   nothing. A slice whose kind the user cannot settle is a slice whose **boundary is wrong** — two
   families in one diff — and splitting it here is free.

   **Propose the kind; the developer settles it.** State the family you read from the slice and the
   workflow that follows, per slice — then let them overrule it. If they name a different workflow,
   or the slice fits no listed kind, follow *The matrix is the default routing, not a gate* below:
   present the consequence, recommend, and record what they chose. What they may not overrule is
   that the node has **some** verification — that is the repo's rule, not the planner's preference.

   Settle, per slice, **how it will be proven** too — the highest rung of the verification ladder it
   can reach (V1 an executable test … V4 a scripted manual procedure with consent; `pr-stack` skill
   § *Verification — required in every node*). Where a slice can only reach V4, say so **now**: it
   needs the developer's consent, and that belongs with the decomposition rather than at 6e.

3. **Dependency edges** — for each pair of slices, does one *need* the other, and at which level:
   only at the **compile** level (→ the other side publishes a stub; no ordering forced beyond the
   stub being below) or at **runtime / behaviour** level (→ it must be a real predecessor, and the
   dependent lands in a later green wave)? Record the edges as a graph, `a → b` meaning *b needs a*.
   **Do not ask which slice merges first** — that is derived in question 8, not volunteered.
4. **Ownership** — Which PR owns which API surface / files? (Each symbol has exactly one owning PR.)
5. **Stack size** — How many PRs? (Prefer the fewest that keep each PR independently reviewable and
   mergeable.)
6. **Trunk-merge safety — per slice, before green waves.** For each slice, answer: *if only this PR
   merged to `master`, would production deploy/runtime and local dev still work?* Production and
   local dev **workflows** must stay intact (servers start, primary dev commands succeed, APIs the
   UI needs are served — even when behaviour is stubbed or empty). If the honest answer is no, name
   the mitigation in the plan (stub, servicer with safe default, dev-only dependency, deferred
   wiring) or split the slice — **do not** defer fixing production/local dev to a successor without
   documenting that successor as a hard merge blocker (which defeats independent merge). **Data:**
   breaking or wiping **local dev data** is fine — say so in the slice note so implementers know to
   reset. **Production data** (schema migrations, backfills, destructive transforms) is **not** fine
   to slip through: ask the developer explicitly here, and record approval or the agreed rollout in
   the node's changeset.
7. **Green waves** — for each PR, which predecessor-owned symbols does it *build on*? A stacked branch
   inherits its predecessors' **stubs, not their behaviour**, so a PR whose tests drive a
   still-stubbed predecessor cannot finish until that predecessor is green. Decide per symbol: code
   against the stub, inject a double at the test seam, or accept the sequencing. See the two
   independence properties in the `pr-stack` skill.

   Then group the PRs from the question-3 edges: **wave 1** is every PR that needs no predecessor
   *behaviour* — the ones an implementer could start the minute the stack is planned; **wave k** is
   every PR whose unmet needs are all met by the waves below it. The grouping is **wider than the
   branch line** — several PRs share a wave, and a PR sitting sixth in the line can still be wave 1.

8. **The line, derived from the waves — do not skip this.** This is the step most easily skipped,
   and skipping it leaves each wave in whatever order its PRs happened to be named in above.
   Authority: the `pr-stack` skill § *Order inside a green wave*.

   - The line is the **waves concatenated**: all of wave 1, then all of wave 2, and so on.
   - **Inside a wave, blockers lead.** Sort by what waits on the PR — most transitive dependents
     first, PRs nothing depends on last. Break a tie with the most foundational PR first.
   - Every PR's predecessors sit in a strictly *earlier* wave, so any intra-wave permutation is
     still a valid topological sort. Nothing forces this order, which is exactly why it must be
     **chosen** rather than inherited from the interview's phrasing.

   ```
   edges    n1 → n2, n3, n4, n5      n2 → n4      n5 → n6, n7, n8
   waves    1: n1     2: n2, n3, n5     3: n4, n6, n7, n8
   line     n1 · n5, n2, n3 · n4, n6, n7, n8      (bottom of the stack on the left)
                 wave 2 led by its blockers — n5 (3 dependents), n2 (1), n3 (none)
   ```

   **Everything about waves is written in node numbers `n1 … nN`, never PR numbers** — the whole
   grouping is decided here, before a single PR exists. `n<k>` is the `k` in branch `pr-k-<slug>`
   and the `K` in the title's `K/N`; it survives into the changesets and the PR descriptions
   unchanged. A PR number is used only to point at the **composition of an already-open PR**, which
   in a stack planned from scratch is nothing. See the `pr-stack` skill § *Node numbers*.

Present the **green waves first**, then the **stack order derived from them** (PR₁…PRₙ with one-line
scope + owned API + **kind** + **verification rung** each) and the predecessor/successor edges. The
kind belongs in the decomposition the user approves, not in the detail of pass 1: it is what says
this node gets no PRD, that one's commit is a `plan.jsonl`, and this third one is proven by a
baseline rather than by a test. Name the transitive-dependent count that
put each wave-leading PR where it is, and say what flattening the graph into a line cost — which PRs
could have been worked in parallel and now sit one above the other. **The decomposition is the
interview's last question, and nothing is created until the user has answered it** — it gathers
the input every later step plans from (slices, kinds, edges, rungs); it is not a review of produced
work, of which there is none yet. If they named a trunk
other than `master`, set `TRUNK` to that branch (the repo-default trunk stays `master` unless they
did).

### Step 2: Analyze Existing Code

Pick a **whole-work discovery slug** before launching Explore — there is no per-PR slug yet, but the dump must exist as soon as the first pass returns (rejected PRD / stop before 4b must not lose it):

```
docs/<area>/1-WIP/{YYYY-MM-DD}-{stack-work-name}-whole-work-initial-discovery.md
```

`{stack-work-name}` is a short kebab name for the whole stack (from the interview), not a PR changeset slug. Create that file **before** the first Explore / Grep / Glob / Read, then persist each pass into it per `.agents/skills/pr-lifecycle/references/initial-discovery.md` (combined conclusions at the top; each pass as `## Exploration N` at the tail).

Then run `.agents/skills/planning/references/planning-phase.md` **Step 2** (code analysis → State A),
**Step 2b** (deferred-work cross-check, below) and **Step 3** (product area), once for the whole body
of work. Record which packages each PR touches.

### Step 2b: Cross-check the deferred-work records — MANDATORY, and it matters more here

Follow `.agents/skills/deferred-work/references/planning-cross-check.md` — the scan commands, the
verdict table, the right-sizing rules, the restructure-prerequisite contract, and the
systemic-restructure section all live there. The bar for *writing* to either record is in
`.agents/skills/deferred-work/SKILL.md`.

**Step 2b matters more for a stack than for a single PR, because a stack has somewhere to put the
answer.** Classify each hit, then decide its **shape** — and for a stack there is one shape a single
PR does not have:

| Size and location of the fix | Shape |
|---|---|
| Small, inside one node's own files | do it in that node; record it in that node's `## Prerequisites` |
| Small, in shared code more than one node touches | **its own stack node** (typically PR₁, or immediately before the first node that needs it), with the **kind the fix actually is** — a bug fix is a Bug fix node, a tidy-up is a Refactor node. Name it in every affected node's `## Prerequisites`. **Never a PR outside this stack** |
| Large, or `Restructure: required`, inside **one** node's files | that node's own **Restructure Prerequisite** — its own `Type: Refactor` changeset, executed by that node's `/green` before implementation |
| Large, or `Restructure: required`, spanning **more than one** node | **its own stack node** — see below |

⚠ **`/plan-pr-stack` only creates PRs that are members of this stack.** A ground-softening or
code-improvement change the user approved is a stack node like any other — not a sibling PR off
`$TRUNK`. Landing it first is merge order, not a separate stack. A PR opened with bare `gh pr create`
is an unregistered chain and a defect of this command.

**Placement is creation order, not insertion.** `gh stack add` only appends to the **top**. Pass 1
creates layers bottom-up in the settled order, so a node that belongs immediately before the first
dependent node is simply that position in the `init` / `add` sequence — typically PR₁ when it is
the ground the whole stack builds on, otherwise PRₖ when PR₁…PRₖ₋₁ do not need it. Do **not**
create the feature layers first and then try to `gh stack add` the softening node: that puts it
on top, after the nodes that need it.

If the stack **already exists** and the node must sit under an existing successor, `gh stack add`
cannot place it. Do not move it to the bottom as a shortcut. Reconstruction is `gh stack unstack`
(explicit consent — it deletes the GitHub stack object) then `gh stack init` with the explicit
bottom-to-top branch list, or `/split-pr-to-stack` when the work is splitting an existing layer.
Agents do not drive `gh stack modify`'s TUI.

⚠ **Do not absorb a large restructure into a feature node.** It buries a reviewable change under a
mechanical one and breaks the boundary contract's promise that a node is independently reviewable.

Carry the verdicts into Step 4b: each node's `## Prerequisites` lists the items **that node** runs
into, and a blocking one also earns a TODO under the row that clears it. Record the ones you decide not
to fix too. Name any in-scope package with **no** `<package-dir>/docs/code-issues/` directory; that means
nobody has analyzed it, not that it is clean.

### Softening the ground — restructures you propose, not ones a record asked for

The scan finds debt somebody recorded. Your own reading of the code in Step 2 is the other source:
where the structure as it stands would make the nodes you are about to plan harder or riskier. Full
guidance and the presentation format are in
`.agents/skills/deferred-work/references/planning-cross-check.md` § *Softening the ground*.

**Suggest; do not decide.** A preparatory restructure spends review budget before any feature has
earned it. Present the difficulty it removes, the operations, the measured blast radius, the cost,
and what skipping it costs — then ask. The bar is a named difficulty in *this work*, not general
tidiness, and a restructure larger than what it enables has stopped being preparation.

Two things are specific to a stack:

- **Do it once, for the whole body of work**, alongside the decomposition — not per node later. A
  seam softened before pass 1 shapes every node's owned surface; the same seam softened after pass 2
  rewrites every node above it.
- **The decomposition is itself a signal.** If a slice can only be cut by splitting a layer rather
  than a capability, or two candidate nodes keep wanting the same file, the structure is fighting the
  decomposition — say so, and propose the restructure that makes a vertical slice possible. That is
  the most valuable form of this suggestion, because the alternative is a stack whose boundaries are
  wrong.

Approved and scoped to one node → that node's **Restructure Prerequisite**, with
`**Source:** planner judgment`. Approved and spanning nodes, or a small shared-code fix more than
one node would touch → **a stack node** (below), never a PR off `$TRUNK`.
Declined → file the observation (a code issue if measurable, else a `Future enhancement` TODO) and
record it in the affected nodes' `## Decisions & Trade-offs`.

**Non-fluent suites the stack's tests will land in** (an open `non-fluent-tests` code issue, or a
quick score below 7 — `.agents/skills/testing/references/fluent-style.md`) are softening candidates
of their own kind. Every node writes its new tests fluent regardless; the proposal is to migrate the
suite first. An **oversized** one (≥ 500 lines, `**Priority:** 1`) is proposed before any other
softening node, recommended *do it*. Approved → a **Test-style migration** node placed immediately below the first node that
writes into the suite — never a Restructure Prerequisite, since it must not hold up any node's green.
It needs nothing from its neighbours, so it is **wave 1**; the nodes above are red-tested against the
suite as it is today and rebase over the migration when it greens. Declined → the record stands, and
the sweep (`/yolo-pr-stack`) or `/fix-pr-stack` takes it with the rest of the stack's code issues.

### Node kinds — settle one per node; the kind picks its `## Workflow` preset

Every node carries the **kind** settled in Step 1 question 2. This command does not re-specify the
per-kind workflows — it uses the procedure of the command that owns each one, states what that
node's two commits must contain, and gives the node's changeset the `## Workflow` preset for its
kind (`.agents/skills/pr-lifecycle/SKILL.md` § *Presets*). The preset's rows after the
guardrail say what implements the node; this command never does. Authority for the taxonomy, the
boundary cases and the verification ladder: the `pr-stack` skill § *Node kinds* and
§ *Verification*.

| Kind | Pass 1 writes (commit 1) | Pass-2 commit (this node's "red" step) | Procedure it uses | `## Workflow` preset |
|---|---|---|---|---|
| **Feature** | PRD + changeset + discovery | owned stubs + failing acceptance tests + failing unit/it tests | `/plan-red` Steps 7–9 (Step 6d–6f below) | **feature** |
| **Bug fix** | changeset + discovery; PRD only when user-visible | the **reproduction test**, red *for the defect*, + any stub it needs | `/reproduce` (Step 6c-ter) | **bugfix** |
| **Contract change** — behaviour-changing migration, deprecation, removal | changeset + discovery; PRD only when user-visible | tests asserting the **new** contract + preservation tests for what survives. **No reproduction**: an intentional change has no defect | `/plan-red`'s behaviour-changing path + `/plan-tdd-migration`'s preservation technique (Step 6c-ter, second branch) | **feature** (contract change) |
| **Refactor / restructure** | changeset (restructure template) + discovery, **no PRD** | `plan.jsonl` + recorded baseline; **no** acceptance tests | `/code-restructuring` Steps 1–6 (Step 6c-bis) | **restructure** |
| **Mechanical migration** | changeset (`Type: Migration` · `Behaviour: preserves`) + discovery, no PRD | recorded baseline + behaviour-preservation tests wherever the baseline does not cover what moves | `/plan-tdd-migration` (Step 6c-quater) | **migration** |
| **Infra / toolchain** | changeset (`Type: Infra`) + discovery, no PRD | the verification command + its recorded before-state | `/plan-ft-dev` for the changeset (Step 6c-quater in pass 2) | **infra** |
| **Test rebalance** | changeset (`Type: Test Rebalance`) + discovery, no PRD | the lower-tier tests that must exist **first** (V1-characterisation) + the **V3** equivalence measurement | `/plan-test-rebalance` (Step 6c-quinquies) | **rebalance** |
| **Test-style migration** | changeset (`Type: Test Style`) + discovery, no PRD | each suite's **V2** before-state — titles, count, coverage, fluent score with per-test rows | `/plan-ft-dev` for the changeset; `fluent-style.md` § *Migrating a suite* | **test-style** |

**Which rows the two planning commits close.** Commit 1 closes the preset's **Plan** row (row 1).
Commit 2 closes the row that owns the guardrail — **Red** for feature and bugfix, **Preservation
tests** for migration, **Red — replacement tests** for rebalance — and, for restructure, infra and
test-style, whose row 1 *is* the plan plus its baseline or before-output (for test-style, each
suite's recorded before-state), it is row 1 that closes in commit 2.
The draft is readied by the Wrap row (`/pr-wrap` step 9), so there is no PR row to write. A commit cannot name its own
SHA, so commit 2 back-fills commit 1's SHA into the Plan row's **Result**, and the guardrail row's
**Result** carries its evidence and `commit 2` (the PR's second commit is unambiguous by the
two-commit shape). Every row below those stays ⬜.

**The changeset is not one of the variables.** Every node of every kind writes its own changeset in
4b, because a stack node is picked up by an implementer — or an agent — with none of this planning
conversation in context, and the changeset is the only carrier of the background, State A, State B,
the boundary, the inherited dependencies and the verification method. What the kind varies is the
**PRD** (fiction for a behaviour-preserving node), the **template** the changeset follows, and the
**contents of commit 2**. A node without a changeset is not a node; it is a diff somebody will have
to reverse-engineer from a branch name.

**Mixed-kind stacks are the normal case, not an exception.** The commonest shape here is a
behaviour-preserving node at the bottom (softening the ground), a bug fix above it, then the feature
nodes — and each of those three is planned by a different command. Do not let the stack's purpose
decide a node's kind.

**A node whose kind cannot be settled has the wrong boundary.** Two families in one diff — a
refactor that also fixes a bug, a migration that changes an error type — is a split, and splitting
costs nothing before pass 1. It is not merely tidiness: the moment a behaviour-preserving diff alters
an output, its baseline stops being a guardrail and becomes something that has to be edited, which
leaves nothing proving the move was safe.

### The matrix is the default routing, not a gate — recommend, then follow the developer

The kinds matrix is what to do **when nobody said otherwise**. The developer is in charge of the
code, so a workflow they name wins — but they are entitled to the consequence *before* they choose
it, not at review. Two directions this arrives from:

1. **They name a workflow up front** — "plan every node with `/plan-red`", "skip the PRD on the
   feature node too", "no restructure changeset, just fix it in `/green`", "use
   `/plan-tdd-one-shot`", "no tests on n4, it is config".
2. **The request fits no listed kind** — a spike, a revert, a docs-only node, a proto / API-definition
   node, a dependency bump, a generated-code refresh. Resolve it with the family question first
   (*what does the diff do to observable behaviour?*); that answers most of them. If it still does
   not resolve, **propose** a workflow, say which kind's shape it borrows, and ask.

**The response shape** — the same one `/skip-tests` uses, because it is the same situation:

- **Both readings, one line each.** What the kind implies, what they asked for. No lecture.
- **The mechanical consequence, in terms of this stack** — which artifact goes missing, which gate
  disappears, what a later command will not find. Not "best practice": *"a Refactor node planned
  with acceptance tests has no `plan.jsonl`, so `/code-restructuring` has nothing to apply and its
  `/green` becomes hand-editing"*, or *"a Feature node with no PRD leaves `/wrap-context-docs` with
  no product doc to fold its State B into"*.
- **A recommendation, and the nearest option that keeps the guardrail.** Recommended first:

  ```
  A. <the kind's default> — recommended, because <the consequence avoided>
  B. <their ask, with the guardrail preserved some other way>
  C. <their ask as stated> — <what is lost>
  ```

- **Then do what they decide.** A reaffirmed request is a decision, not a disagreement to
  re-litigate; say so once and proceed with the full ask. Write it into that node's `[wf]`
  rows — the rows and commands their workflow needs, in place of the preset's — and record
  it in that node's `## Decisions & Trade-offs` — what was traded and why — so the next reader sees a **choice**
  rather than an omission, and so `/validate-changes` does not report the missing artifact as a
  defect.
- **Per node, never per stack.** An override on n3 says nothing about n4. Ask again if they meant all
  of them.

**Prefer a command that already implements what they asked for** over improvising a workflow:

| They ask for | Use |
|---|---|
| plan and red in one pass, no stack | `/plan-tdd-one-shot` |
| every line this node changed covered, not just the new tests | `/green-100` as the command of that node's Green row, instead of `/green` |
| work driven by a roadmap / story tracker | `/roadmap-red` |
| an epic with no page yet, to plan from a Roadmap page | `/plan-roadmap-epic` first — it publishes the page this command then plans from |
| work driven by a Roadmap tracker page | this command with the Roadmap URL as input (Step 1, `roadmap-driven-development` skill); one item, no stack: `/roadmap-red` |
| a fix for a reported defect | `/reproduce` |
| a migration with no feature change | `/plan-tdd-migration` |
| measure the test shape first, then rebalance | `/plan-test-rebalance` |
| something thrown away once it has taught us the shape | `/prototype` — **not a stack node.** Its files carry `HOLD: PROTOTYPE, DO NOT MERGE`, and every node this command opens is a mergeable PR in a registered stack. Run it *before* planning, on a throwaway branch, and let what it teaches shape the decomposition; never `gh stack add` a prototype |
| tests disabled with documented FIXMEs | `/skip-tests` — last resort, needs approval, and it is about *existing* tests, never a substitute for `## Verification` |

**One thing is not a preference: `## Verification` exists either way.** A workflow swap changes
*how* a node is proven, never *whether* it is. If the workflow they chose produces no automated
proof, that is the **V4** case — write the procedure, capture the evidence, and take the consent
line. "No verification at all" is the single answer to come back on, and not as the planner's
opinion: a code change with no way to tell whether it worked is not an acceptable PR outcome in this
repo, and the node does not get a branch until it has one.

### Verification — every node, whatever its kind, or its branch is not cut

Tests are the guardrail wherever they can reach, and in this repo they almost always can. But a
node's proof is not always a test — and a node with **no** proof is not an acceptable PR, however
small its diff. So every node's changeset carries a `## Verification` section
(`pr-lifecycle/references/changeset.md` §9.5) naming the highest rung it reaches:

| Rung | Method | Typical node |
|---|---|---|
| **V1** | an executable test — **fail→pass** (acceptance, reproduction, new-contract) or **characterisation**: green before and after, valuable because it *would have failed* had behaviour changed (preservation, baseline-gap, rebalance replacement). Name which shape; a characterisation test that claims to "fail first" is a section nobody can check | the default for every kind |
| **V2** | a recorded baseline that must still hold, **where it demonstrably covers the code that moves** | refactor · mechanical migration |
| **V3** | a deterministic command whose before- and after-output are recorded in the changeset | infra · toolchain · performance |
| **V4** | a scripted manual procedure with recorded evidence, plus the developer's recorded consent | rare |
| **V5** | nothing | **never — do not cut the branch** |

- **Pick the highest rung the node can reach, and name what blocks a higher one.** "This code has no
  tests" is not a blocker; it is the reason to write one. For a behaviour-preserving node that is the
  rhombus rule — coverage goes down a tier *before* the code above it moves.
- **V2 is a claim about coverage, so prove it in the changeset.** Name the suites and what they
  cover. A green baseline over an untested file is a coincidence, not a guardrail — a V2 node that
  finds a gap writes the missing test (V1) for that gap first, in its own commit 2.
- **V4 is settled with the user, in Step 1, not discovered at 6e.** It carries
  `**Approved:** <who>, <date>`. Choosing an unautomated guardrail is a judgment about what the repo
  is willing to carry, which is the developer's call.
- **A node at V5 is not planned.** Do not cut its branch, do not submit a draft for it: report it in
  the Step 1 approval as a node whose proof is unsettled, and settle it.

### A systemic restructure / ground-softening node — always in this stack

When the issue sits in the seam **every** node builds on, or in a file more than one node has to
edit, it is **its own node in this stack**, placed immediately before the first node that needs it
(PR₁ when it is the ground the whole stack builds on). There is no "prerequisite PR off `$TRUNK`"
shape here — that would be a PR this command created that is **not** in the stack.

| Shape | When | Cost |
|---|---|---|
| **Its own stack node**, placed immediately before the first node that needs it | always, when `/plan-pr-stack` is planning it | every node above it gets rewritten under them |

Landing it first is the stack's merge order, not a second stack. Present the placement and the
accepted breakage; the developer still approves whether to do the restructure at all (Step 1 / the
ground-softening ask) — they do not choose a PR outside the stack.

Its artifacts are the **Refactor / restructure** row of the kinds matrix above — `Type: Refactor`,
**no PRD**, the restructure changeset template
(`.agents/skills/pr-lifecycle/references/restructure.md`), a pass-2 commit that is
the `plan.jsonl` plus the recorded baseline rather than stubs and failing tests, and
`/code-restructuring` as its `/green`. It has **no acceptance tests**: a behaviour-preserving change
has nothing new to accept, so its verification is **V2** — the recorded baseline must still hold
after `restructure apply`. Where that baseline does not reach what moves, the missing test is
written **first** (V1), in this node's own commit 2; that gap is the commonest reason a restructure
lands broken.

What is specific to a stack is not the artifacts but the **blast radius**:

**Its planning does not block the nodes above it, and its execution is allowed to break them.**
This is the part to get right, and it is deliberate:

1. Nodes above it are planned, stubbed and red-tested against the structure **as it is today** — the
   pre-restructure structure. Planning cannot wait for an execution that happens in `/green`, and
   planning against a layout nobody has produced yet is guesswork.
2. **When the restructure node greens, the nodes above it break.** Their stubs move, their imports
   move, their red tests fail differently. That is expected, accepted up front, and **not** a
   planning defect. Refactoring them is later-stage work.
3. Every affected node's changeset carries an **`## Inherited Restructure — expect rewrite`** section
   (template in the `pr-stack` skill) naming the restructure node, what moves, and that the repair is
   that node's own follow-up commit.
4. Each successor's next `/pr-stack-rebase` surfaces the conflict, and **its repair is a new commit**
   in that node — never an amend of its planning or red commit, and never an edit to the restructure
   node from a successor branch.
5. A successor's red tests must still be red **for their own missing implementation** after the
   repair. One that went green in the repair was satisfied by the restructure, which means it was
   never testing that node's behaviour — raise it, do not pocket it.

Report the placement and the accepted breakage in the Step 1 decomposition approval.
Do not decide the restructure silently: it changes how much rework the stack costs.

### Step 3: Settle the plan — no stack document is written

**There is no `docs/<area>/1-WIP/STACK-*.md`.** Each PR's stack context is embedded in its own changeset
in Step 4b, so nothing shared is created here and nothing has to be handed between branches later.

What this step produces is agreement, not a file. Settle and write down for your own use:

- the **green waves**, in **node numbers** (`n1 … nN`, `n<k>` = branch `pr-k-<slug>` = title `K/N`;
  no PR exists yet, and nothing here waits on one) — which nodes are in wave 1 (startable the moment
  the stack is planned), which in wave 2, and so on, and for every node above wave 1 exactly which
  predecessor behaviour it waits on. This is the grouping each changeset and each PR description
  will carry, written the same way in both;
- the stack order — branch and base per PR — **derived from the waves**, not chosen separately: the
  waves concatenated, blockers leading each wave (Step 1 question 8). Write down the
  transitive-dependent count that justifies each wave-leading position; Step 9 reports it;
- **`TRUNK`** — `master` unless the user named another;
- the **stack slug** — one or two kebab-case words, associative, chosen once and never changed. It
  goes in every PR title as `(#<slug> K/N)` and in every changeset's `## Stack Context`. See
  **PR titles** in the `pr-stack` skill for what makes a good one;
- the **owned API surface** per PR (this becomes each changeset's `## Stack Context`);
- per node, its **kind** and the **verification rung** it reaches — settled in Step 1 question 2 and
  written down here, because they decide what 4b writes (PRD or no PRD, which changeset template) and
  what 6's routing does with that node. A node still at V5, or whose kind is unsettled, is **not
  ready for pass 1**: its branch is not cut until both are answered. Any node at V4 carries the
  user's recorded consent from Step 1;
- per PR, its **`Greenable independently?`** answer — and for each `no`, exactly which test drives
  which predecessor stub. This is the same fact as its wave: wave 1 ⇔ `yes`;
- any **restructure / ground-softening node** from Step 2b: its position **in this stack**, which
  nodes it rewrites under, and the accepted breakage. A restructure node has no acceptance tests and
  its pass-2 commit is a plan plus a baseline, not stubs and tests — so pass 2 treats it differently,
  and that has to be settled here rather than discovered in Step 6. Never a PR off `$TRUNK`.

Settle the waves even when every PR is independently greenable — a stack that is **all wave 1** is
information, not an empty answer, and each changeset still has to state its own row.

**Each PR carries its own wave; no whole-stack wave table is committed.** Step 4b writes
`### Green wave` into every changeset and Step 4d puts the same line in every PR description, so the
grouping is readable from any PR without opening a second document. What is *not* created is one
shared table of all the rows: it would live in PR₁ — the first to wrap — and so disappear while the
PRs above still wanted it. Step 9 reports the whole grouping to the user; after that it is
reconstructed by reading the open PRs.

## Pass 1 — plan every PR and open its draft (commit 1 of each)

### Step 4: For each PR in order (PR₁ → PRₙ) — branch, docs, push, and open the PR

Process PRs **in stack order** so each successor branches off its predecessor. Stay in **this
worktree**. After each layer is on GitHub, switch to the next branch — do not keep a checkout of a
branch that is already pushed. **Pass 1 writes docs only** — no stubs, no tests, no `src/` changes.
Those come in pass 2, as each PR's second commit.

**4a. Create the stacked branch in this worktree and check it out.**
- PR₁: cut from `$TRUNK` (`origin/master` unless the interview set another). Check out that tip
  **without pinning the local trunk branch** (the primary clone often already has `master` checked
  out):
  ```bash
  git fetch origin "$TRUNK"
  git checkout --detach "origin/$TRUNK"
  gh stack init --base "$TRUNK" pr-1-<slug>
  ```
  `gh stack init --base "$TRUNK"` creates (or adopts) the first stack branch, checks it out, and
  records `$TRUNK` as the stack trunk. Do not `git checkout "$TRUNK"` here if another worktree
  already has it. Do not omit `--base` when `$TRUNK` is not the repo default.
- PRₖ (k > 1): while still on PRₖ₋₁ (the current top of the stack):
  ```bash
  gh stack add "pr-${k}-${slug}"
  ```
  This creates the next branch at the current HEAD, adds it to the stack, and **checks it out**.
  PRₖ₋₁ is no longer checked out here. Its branch holds exactly its planning commit; pass 2 will
  return to it, add its red commit, and rebase this successor on top. `gh stack add` cannot insert
  below an existing successor — a late placement change (softening node that should sit under a
  layer already submitted) is reconstruction, not another `add`. See the placement warning in
  Step 2b.
- Do **not** `git checkout -b` as a substitute for `gh stack init` / `gh stack add` — those commands
  are what keep `.git/gh-stack` tracking honest.
- Do **not** create a worktree per PR here. Two reasons, both from the `pr-stack` skill:
  - **A worktree pins its branch**, and git refuses to update a branch checked out elsewhere —
    pass 2 must be able to check every stack branch out **here**.
  - A worktree in this monorepo costs **~7 GB** once `node_modules`, `src/protogen` and the Python
    venvs exist. Six is ~42 GB. The branch is on the remote as soon as 4d finishes; recreating a
    worktree later is cheap (`gh stack checkout <PR#>`).
- Per-PR worktrees belong to whoever runs `/green`, created only for the PRs actually being worked
  — see Step 10.
- This worktree already has its dependencies. If it does not: `uv sync --group dev` plus package-level
  builds (`uv run mypy`) for the packages in scope — never a full-repo build.

**4b. Create this PR's PRD + changeset + initial discovery.**
- **Write this node's artifacts for its kind**, per the matrix in *Node kinds — settle one per
  node*. Follow `.agents/skills/planning/references/planning-phase.md` **Step 4** (PRD) and **Step
  5** (changeset), scoped to **this PR only** — with the PRD step applying to a **behaviour-adding**
  node, and to a behaviour-changing node **only when the change is user-visible**. Each PRD's
  headline decisions go into Step 9's summary under **Decided without review**. A node that gets none writes `None — <kind>, no user-visible
  behaviour delta` in that slot rather than inventing one.
- **Start each changeset per the `pr-lifecycle` skill § *Start a changeset***
  (`.agents/skills/pr-lifecycle/SKILL.md`), with the preset for this node's kind (*Node kinds* above);
  a `Workflow override` from the interview is written into the rows themselves. In commit 1 the
  Plan row is ✅ with today's date and what it wrote; every other row is ⬜. These rows are the node's dispatch — `/next`, `/yolo` and `/yolo-pr-stack` read the
  stage from it, not from this command.
- **A Stash-planned stack: every node's changeset carries `## Stash Tracker`** for the page item(s)
  that node delivers, and the publish TODOs (`roadmap-driven-development` § *Write the changeset's
  `## Stash Tracker`*): under the guardrail row, `Stash: PR #<N> · draft listed by the pass-1
  publish` (ticked in commit 2, once the publish happened). The ready publish is not a TODO:
  `/pr-wrap` step 9 makes it once it readies the draft (`PR #<N> · ready for review`, the
  reconcile, the `--resolve` ids of the threads this node addresses). In manual mode each reads as advice to the developer.
- **Every node writes a changeset, whatever its kind** — that is not one of the variables. A stack
  node is picked up by an implementer or an agent holding none of this planning conversation, and the
  changeset is the only place its background, State A, State B, boundary, inherited dependencies and
  verification method exist.
- **`## Verification`** carries the rung settled in
  Step 1, the exact command a reviewer re-runs, the before-state and the required after-state. For a
  Feature node this points at the acceptance tests 6e will write; for a Refactor or a mechanical
  migration it is the recorded baseline **plus the evidence that baseline covers what moves**; for an
  infra node it is the deterministic command with its before-output. A V4 node carries
  `**Approved:** <who>, <date>` from Step 1. **A node with no verification method does not get a
  branch** — go back to Step 1 rather than cutting one and hoping pass 2 finds a proof.
- **The `**Complexity**` header line sizes the implementer:** `/yolo-pr-stack` reads it to size each implementer's model and effort; a node without one is sized by
  guesswork. Re-score it in commit 2 if
  the red step shows the node is bigger or smaller than planned.
- **Every changeset MUST carry a `## Stack Context` section** (template in the `pr-stack` skill):
  the stack name and **slug**, the **`Epic`** issue link (`#pending` in pass 1, filled in pass 2's
  Step 6g once Step 5's 3b has opened it — same back-fill as the PR number), this PR's position
  `k of n`, its **`Kind`** (the resolved
  `(Type, Behaviour)` pair) and its **`Workflow`** — the preset name and the pass-2 route — plus a
  **`Workflow override`** line whenever the developer chose something other than the kind's
  default. Step 6c-route reads those lines to pick this node's red step; every row after the
  guardrail is read from the `[wf]` rows, which is why an override must be written into the
  rows as well. An override that exists only as prose in `## Decisions & Trade-offs` is
  invisible to both. Then its branch and base, its successor **branch** from
  the settled plan (or `none — top of stack`; never a predecessor — that changeset wraps and
  disappears first), the seam its boundary follows, its **owned API surface**, its **`### Green
  wave`** (`**Wave:** k of m`, its own **node number**, the nodes of that wave it can be greened
  **concurrently with**, the nodes it **blocks** and what each needs from it, and the real
  dependency edges as opposed to the branch line — **all in node numbers**, because no PR number
  exists at this point and a slot left for one is a slot nobody back-fills), its
  **`### Trunk-merge safety`** (production + local dev workflows when this PR merges alone; local
  dev data may break; production data only with Step 1 consent), and its **Greenable independently?**
  answer.
  **The wave and the greenability answer may not disagree**: `**Wave:** 1 of m` means startable now,
  which forces `Greenable independently? yes`; any wave above 1 forces a `no` naming the PR whose
  behaviour is missing. The wave is also the same decision as the `K/N` in this PR's title — if they
  contradict each other, the line was not derived from the waves; go back to Step 1 question 8.
  **State this PR's own row only** — its wave, its concurrency, what it blocks. Never a sibling's
  status; that is the shared manifest returning. This replaces the shared manifest: it is created with the
  PR, wrapped with the PR, and deleted with the PR. The PR's own number and URL are not known
  yet — leave that slot as `#pending` and fill it in pass 2 (Step 6g), in the same commit as the
  red step, so the PR keeps exactly two planning commits.
- **`## Prerequisites` is per node**: only what Step 2b found relevant to **that node**, with a
  **Restructure Prerequisite** block only when the fix is a restructure inside this node's own
  files. A ⛔ blocking item also earns a TODO under the row that clears it.
- **Every node above a systemic restructure node MUST carry `## Inherited Restructure — expect
  rewrite`** (template in the `pr-stack` skill): which node restructures what, that **this node is
  planned against the pre-restructure structure on purpose**, and that repairing the fallout is a
  follow-up commit on this branch after its next `/pr-stack-rebase`. Without this section the
  implementer reads the breakage as a mistake and "fixes" it by editing the restructure node.
- **Every changeset except PR₁'s MUST carry an `## Inherited Dependencies — do not implement here`
  section** (template in the `pr-stack` skill): each predecessor-owned symbol this PR builds on, who
  owns it, that it is a stub during this PR's green, what this PR does instead, and a
  **Greenable independently? yes/no** line.
  Describing inherited state in *State A* is not a substitute — State A says what exists, this says
  what the implementer must **not** build. Whoever runs `/green` reads the changeset, and the
  changeset is the only place this is written.
- **Forward-only, own files only.** Name this PR's successor **branch** in this changeset (settled
  in Step 3). Do **not** edit the predecessor's changeset or PRD from this branch — those files are
  inherited; a commit here would put the predecessor's docs in this PR's diff and conflict when
  the predecessor wraps and deletes them. The predecessor already named this branch as its successor
  before `gh stack add`. Successor GitHub URLs are reported in Step 9, not stamped into predecessor
  docs.
- Tick the Plan row's first TODOs in this PR's changeset (`Record initial discovery`,
  `Cross-check <package-dir>/docs/todo/ and <package-dir>/docs/code-issues/`, `Create/update PRD documentation`,
  `Create changeset`). A node whose kind warrants no PRD — every behaviour-preserving node, and a
  bug fix or migration with no user-visible delta — writes `None — <kind>, no user-visible behaviour
  delta` in that slot rather than inventing one. Nest the plan-derived TODOs under their rows now
  (milestones under Green; under Wrap `Verification executed — result recorded` — the one TODO every
  node owes at wrap — plus the optional `/pr-wrap` steps this node needs, `/pr-wrap` § *Workflow row*). This PR's
  `{slug}-initial-discovery.md` must exist next to the changeset — copy the Step 2 whole-work
  file into it as Exploration 1 (full dump), then append any PR-specific follow-up. Do **not**
  delete the whole-work source until every planned PR has its companion.

**4c. Commit the planning docs — commit 1 of this PR.**
- Stage **only** this PR's PRD, changeset and discovery companion — never the whole-work discovery
  file, never anything under `src/`. Never use `--no-verify`.
- This commit is the PR's plan. Pass 2 adds the red step as a **separate, second** commit; do not
  amend this one later.

**4d. Push and create the GitHub PR immediately — do not wait for the rest of the stack.**

The new **branch** must be on the remote as soon as this step finishes. Do **not** wait until later
layers are planned.

- **Push this branch first** — this does not need other stack branches free:
  ```bash
  git push -u origin HEAD
  ```
- **Do not run bare `gh pr create`.** `gh stack submit` is what creates the PR *and* registers (or
  extends) the stack object. Creating PRs individually produces an unregistered chain.
- `gh stack submit` is stack-wide: it may try to push every stack branch. Before calling it:
  ```bash
  git fetch origin
  git worktree list    # if a predecessor appears in [brackets], it is pinned — skip fetch for it
  for pred in pr-1-<slug> … pr-<k-1>-<slug>; do
    git worktree list | grep -q "\[$pred\]" && continue
    git fetch origin "$pred":"$pred" 2>/dev/null || true
  done
  ```
  If a predecessor **is** pinned, do **not** `git fetch origin "$pred":"$pred"` (git will refuse).
  Try `gh stack submit` anyway — existing PRs are locked and should not be rewritten. If submit
  fails because that predecessor is pinned or a `--force-with-lease` is rejected: **halt** this node's Plan row ⛔.
  Do not `--force`. Do not `gh stack sync` / `gh stack rebase` from here. The pinned predecessor
  will also block pass 2 — ask for that worktree to be freed until this command's completion gate
  has run. The current branch is already on the remote from `git push -u origin HEAD`.
- Create this PR (and add it to the stack on GitHub):
  ```bash
  gh stack submit --auto        # non-interactive; NEW PRs are created as DRAFTS
  ```
  - `--auto` skips the editor, so `gh stack submit` leaves a title derived from the branch or the
    commit. **Replace it immediately** — a squash merge turns it into the commit message on
    `master`, permanently. Use the format from **PR titles** in the `pr-stack` skill:

    ```
    <type>(<package>): <what this PR delivers> (#<stack-slug> K/N)
    ```

    The subject states the delivery **as shipped**, never the planning phase — no `red`, `stubs`,
    `failing tests`, `WIP`, `phase N`, `plan`. Everything after `: ` must be ≤ 100 characters
    including the trailing group.

    **`<type>` follows this node's kind**, not the stack's purpose: `feat` (Feature) · `fix` (Bug
    fix) · `refactor` (Refactor / restructure, and a migration that moves code) · `chore` (infra,
    toolchain, configuration migration) · `test` (test rebalance, test-style migration). A squash merge turns this into a
    `master` commit message permanently, so a `feat` on a behaviour-preserving node lands a false
    changelog entry that nobody can correct afterwards.

    ```bash
    repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    gh api -X PATCH "repos/$repo/pulls/<N>" \
      -f title="<type>(<package>): <delivery> (#<slug> <K>/<N>)" \
      -F body=@<planned-body-file> --jq '"#\(.number) → \(.title)"'
    ```

    Use `gh api`, **not** `gh pr edit`: in some  orgs it fails with *"Projects (classic) is being
    deprecated"*. Pass the body from a file (`-F body=@…`) so newlines and backticks survive. The
    body may say the PR is at its planning stage — the **title** may not.
  - **The body MUST carry this PR's green wave and the stack graph**, so an implementer sees them
    without opening the changeset. A reader who has to open five documents to learn whether they can
    start is a reader who starts anyway and finds out the hard way. Put it near the top:

    ```markdown
    ## Stack

    `#<slug>` — node **n<k>**, PR **<K> of <N>** · base `pr-<k-1>-<slug>` · [stack on GitHub](<url>)

    **Kind:** <Feature | Bug fix | Refactor | Migration | Infra | Test rebalance | Test style> —
    behaviour-<adds|changes|preserves> · `/green` here is `<`/green`|`/code-restructuring`>`
    **Verification:** V<n> — <the method, in one line> · `<the command a reviewer re-runs>`

    **Wave <k> of <m>** — <`startable now` for wave 1, or `waits on n<j>` for the behaviour it needs>
    **Concurrent with:** n<x>, n<y> — the rest of this wave
    **Blocks:** n<z> (<what it needs from this node>) · or `nothing`

        n1 → n2, n4, n5      n2 → n3      n5 → n6
        real dependency edges; the branch line is the waves concatenated, blockers first
    ```

    **The `Kind` and `Verification` lines are why the block exists at all for a mixed stack.** An
    implementer who opens a Refactor node expecting stubs and failing tests, or runs `/green` on a
    node whose green is `/code-restructuring`, has been told the wrong thing by the stack's shape.
    Both lines mirror the changeset (header `**Type**` and `## Verification`); the changeset is the
    committed home, this is the GitHub view.

    **Node numbers, not PR numbers.** The grouping was settled in Step 1 before any PR existed, and
    it is written the same way here and in the changeset — so nothing in this block is a slot
    waiting to be back-filled after submit, and pass 2 has nothing to renumber. Each node maps to a
    branch (`n4` → `pr-4-<slug>`) and to a position (`n4` → `4/N`), both of which a reader can
    resolve from `gh stack view`. Use a PR number only to point at the **composition of an
    already-open PR**, and then write it alongside the node: `n3 (#2403)`.

    The `**Wave <k> of <m>**` line and the changeset's `### Green wave` say the same thing. When
    Step 6g refines the wave, **edit this body in the same step** — a PR description promising
    "startable now" that the changeset has since demoted is worse than no wave line at all.
  - **Never pass `--open`** — it marks new *and existing* PRs ready for review.
  - The first submit may create only PR₁ (no stack object yet; GitHub registers a stack at ≥2 PRs).
    That draft is still a real PR. Subsequent submits add the new PR to the existing stack
    (`✓ Stack created on GitHub with N PRs` / the stack grows).
- Verify this PR:
  ```bash
  gh pr view --json number,url,isDraft,baseRefName,changedFiles \
    --jq '"#\(.number) draft=\(.isDraft) base=\(.baseRefName) files=\(.changedFiles)"'
  ```
  It must be `draft=true`, based on its predecessor (PR₁ on `$TRUNK`), and show **only its own
  files** — in pass 1 that is its PRD, changeset and discovery companion, nothing else. A file
  count that includes a predecessor's docs means the base is wrong.
- **Note this PR's number and URL** for Step 6g — it is written into this PR's own changeset in
  pass 2, not committed now (a docs-only third commit would break the two-commit shape).
- **Do not keep a worktree for this branch.** This worktree will `gh stack add` the next layer.
  In pass 1, after this submit, this worktree does not come back to this branch; pass 2 returns to
  it **exactly once**, in stack order.

### Step 5: Pass 1 checkpoint — the whole stack is visible for the first time

Every planned PR is now a one-commit draft on GitHub. Before pass 2 touches any branch:

1. **Confirm a clean tree and that the top branch is pushed:**
   ```bash
   git status --porcelain | grep -v '^?? '        # must be empty
   git rev-list --count origin/$(git branch --show-current)..HEAD   # must be 0
   ```
2. **Confirm the stack (or the chain, if only PR₁ exists so far):**
   ```bash
   gh stack view
   ```
   For n ≥ 2, require the stack-created confirmation (quoted in Step 9) and **no `⚠` at all** — pass 1
   only ever appended a layer on top of the current tip, so nothing can be stale yet. A `⚠` here means
   somebody committed to a stack branch from elsewhere; halt that node's guardrail row ⛔ before pass 2 rewrites anything.
3. **Revise every PR title — MANDATORY.** Each was set in its own 4d, when the stack was still
   being planned: `N` was a projection, scope moved between layers, and `gh stack submit --auto` may
   have left a branch-derived title on any PR whose retitle failed. Read them all now, as one list:

   ```bash
   # `gh stack view` prints each branch's COMMIT SUBJECT, not the PR title — they differ, and the
   # commit subject is not what merges. Take the PR numbers from it and read titles from the PRs.
   for n in $(gh stack view 2>/dev/null | grep -oE 'pull/[0-9]+' | grep -oE '[0-9]+'); do
     gh pr view "$n" --json number,title,state --jq '"#\(.number) [\(.state)] \(.title)"'
   done
   ```

   Check every one against **PR titles** in the `pr-stack` skill:

   - format `<type>(<package>): <what it delivers> (#<stack-slug> K/N)`;
   - **`<type>` matches that node's kind** — `feat` / `fix` / `refactor` / `chore` / `test`. In a
     mixed stack this is the check most often wrong, because the stack's purpose pulls every title
     towards `feat`;
   - the **same slug** on all of them — a typo makes one PR look like a different stack;
   - `K` ascending from 1, `N` equal to the **final** count, not the count when that PR was created;
   - the subject states the delivery **as shipped** — no `red`, `stubs`, `failing tests`, `WIP`,
     `phase N`, `plan`, and never a branch slug like `pr 4 production wiring`;
   - subject ≤ 100 characters after `: `, including the trailing group.

   Fix every one that is wrong, in the same run:

   ```bash
   repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
   gh api -X PATCH "repos/$repo/pulls/<pr>" \
     -f title="<type>(<pkg>): <delivery> (#<slug> <K>/<N>)" --jq '"#\(.number) → \(.title)"'
   ```

   Use `gh api`, not `gh pr edit --title` (Projects-classic GraphQL fault in some  orgs). A title
   left wrong becomes a commit message on `master` that nobody can correct afterwards.

   **3b. Open the stack's epic issue — the DAG's home (MANDATORY).** Every PR
   now exists, so the settled plan can be emitted whole (see the `pr-stack`
   skill § *Epic issues — the DAG's home*). Build the CLI, then run
   `issue create` with the stack slug and trunk — **not** root `uv run pytest -q`
   (that launches the Tauri app):

   ```bash
   uv run mypy
   uv run pytest -q
   ```

   — which creates the GitHub epic issue (whole-scope prose + the canonical
   DAG block, `schema: overstack-dag/1`, node numbers, waves, line, edges —
   exactly the decomposition the user approved) and prints its URL. Then stamp
   that URL into every PR body's `## Stack` block with the same `gh api -X
   PATCH` from 4d, so every implementer sees the epic beside the wave lines.
   The same URL goes into every changeset's `## Stack Context → Epic` (pass 2, Step 6g — the
   changesets are already committed, so it rides in each PR's second commit).
   If the CLI cannot be built or `gh` is not authenticated, **stop** and ask
   the user — never hand-write the DAG block by hand into an issue (a
   hand-written block is the stale-copy problem the epic exists to prevent),
   and never continue planning without an epic URL stamped on every PR.
   `issue create` takes each node's title from its PR and its kind from the PR body's `**Kind:**`
   line (the `## Stack` block). When a PR is missing either, it refuses with exit 2 and names that
   PR. Fix the PR's title or body and run it again.

   **`issue create` emits line edges only — it cannot write a dependency edge.** A fresh epic is
   therefore a linear chain with no waves, whatever the plan says. Immediately after creating it,
   follow `pr-stack` skill § *The epic must be correct*: add one `kind: dependency` edge per plan
   edge that gates a wave (not stub-level ones — `level` is ignored by wave assignment) to the fenced block only, run `issue sync <slug>`,
   and verify that deriving the waves from the block reproduces the planned waves and line. Do not
   report pass 1 until it does. The prose and the PR-body wave lines are not a substitute: overstack
   reads only the block.
4. **Delete the Step 2 whole-work discovery source** — every planned PR now has its
   `{slug}-initial-discovery.md`. Path:
   `docs/<area>/1-WIP/{YYYY-MM-DD}-{stack-work-name}-whole-work-initial-discovery.md`. It was never
   staged, so this is dropping an untracked file — wrap of PR₁ must never be the thing that removes
   it. If any PR still lacks a companion (planning aborted), **keep** the file and stop here.
5. **Report pass 1 to the user** — the final title list with PR numbers and URLs, the branch/base of
   each, and the **green waves** — wave by wave, the PRs in it and which of them are startable the
   moment the gate passes. State plainly that **no node's Green row is eligible yet**: the drafts are
   plans, and pass 2 is about to rewrite every branch above PR₁. Report each PR's **kind** and
   **verification rung** alongside its title — that is what tells the reader which of these drafts
   will carry stubs and failing tests and which will carry a plan and a baseline. Then continue into
   pass 2.
6. **Stash-planned stack only — one publish for the whole stack.** Every draft PR now has its
   number: put `PR #<N> · draft` next to every planned item in a **single** deploy
   (`roadmap-driven-development` § *Publish*), or, in manual mode, put the complete list of marks in
   the pass-1 report under **Needs the developer**. Each node's commit 2 ticks its guardrail-row
   Stash TODO with the deployment id. A refused deploy halts nothing in the plan: switch to manual,
   say why in the report and in each `## Stash Tracker`.

## Pass 2 — red every PR, bottom-up (commit 2 of each)

### Step 6: For each PR in order (PR₁ → PRₙ) — rebase, then the red step **its kind** calls for

Each PR gets exactly one commit here, and **what that commit contains is decided by the node's
kind**, not by this command: for a Feature node it is the `/plan-red` red step (Steps 7–9); for the
other kinds it is the pass-2 column of the matrix in *Node kinds — settle one per node*, produced by
the command that owns that kind. **Step 6c-route is the switch** — read the node's kind off its
changeset header `**Type**` and follow the branch it names.

The **order** is not optional whatever the kinds are: PRₖ's stubs and tests compile against PRₖ₋₁'s
stubs, which only exist on PRₖ₋₁ after **its** pass-2 commit. So each layer first rebases onto the
predecessor's new tip, then does its own red work on top. Every commit here makes the layers above
`⚠`; the loop clears each of them when it reaches it, and Step 8 proves nothing was missed.

What is common to every kind, and where the shared steps live:

| Every node, every kind | Step |
|---|---|
| check the branch out here, unpinned | 6a |
| `/pr-stack-rebase` single mode, before writing anything | 6b |
| build + recorded baseline | 6c |
| **route by kind** to the red step that node needs | 6c-route |
| **verify the guardrail** and record it for the summary | 6e |
| one commit, changeset check-offs, `## Workflow` rows closed, own PR URL, push, PATCH the body | 6g |

Everything between 6c-route and 6e is kind-specific — 6c-bis … 6c-quinquies for the non-feature
kinds, 6d and 6f for the ones that own a new surface. 6e's *subject* changes with the kind; the
verification itself never does.

**6a. Check the branch out here.** The branch exists locally from pass 1. Nothing may pin it
elsewhere:

```bash
git worktree list | grep -q "\[pr-<k>-<slug>\]" && echo PINNED   # must print nothing
git checkout pr-<k>-<slug>
git status --porcelain | grep -v '^?? '                            # must be empty
```

If it is pinned, **halt** this node's guardrail row ⛔, naming the worktree to free — `/green` on this
stack has started too early. Do not `git worktree add` a second copy and do not rebase from the other worktree.

**6b. `/pr-stack-rebase` — single mode, this branch only.** Run it exactly as the hard-gate callers
do, and read the result:

- **PR₁** rebases onto `origin/$TRUNK`. Usually *already current, leak-free, no rewrite*; if trunk
  moved since pass 1 it is rebased and pushed with `--force-with-lease`, which is fine.
- **PRₖ (k > 1)** rebases onto `pr-<k-1>-<slug>`, which just received its second commit, so it is
  **expected to be STALE**. The rebase replays this PR's single planning commit on top of the
  predecessor's plan + red commits and force-pushes with lease. Afterwards:
  ```bash
  git log --oneline origin/pr-<k-1>-<slug>..HEAD    # exactly ONE commit — this PR's planning commit
  ```
  Anything else is a leak; fix it per `/pr-stack-rebase` before continuing. The predecessor's
  stubs are now in this working tree, which is what 6d and 6f compile against.

**6c. Verify build and baseline — MANDATORY** (`/plan-red` Step 7). For each package this PR
touches:

```bash
uv run mypy
uv run pytest -q
```

The branch carries only planning docs plus inherited stubs, so the build **must** pass. If it does
not, **stop** and report the exact failing command per `/plan-red` Step 7 — do not proceed to write
tests on a broken baseline, and do not "fix" a predecessor's stub from here. Record pre-existing
test failures so `/green` does not mistake them for this PR's red tests.

**6c-route. Route by this node's kind — read it from `## Stack Context → Workflow`, falling back to
the header's `(Type, Behaviour)` pair.** Read the **pair**, never `Type` alone: `Type: Migration` is
a contract change when `Behaviour: changes` and a mechanical migration when it `preserves`, and the
two get opposite red steps. If that node carries a **`Workflow override`** (the developer chose
something other than its kind's default — see *The matrix is the default routing, not a gate*),
**the override is the route**; the kind's default row is not. An override recorded only as prose in
`## Decisions & Trade-offs` is one this step will drive straight past — if that is all there is, fix
the Stack Context before routing.

Every branch below ends at **6e** (the guardrail verified) and **6g** (the single commit). Do not run a
kind's steps from memory — follow the command that owns it.

| This node's kind | Its red step | Skip |
|---|---|---|
| **Feature** | 6d → 6e → 6f, as written below (`/plan-red` Steps 7–9) | — |
| **Bug fix** | **6c-ter**, first branch (`/reproduce`) | 6d unless the fix needs a stub this node owns |
| **Contract change** (`Type: Migration` · `Behaviour: changes`, deprecation, removal) | **6c-ter**, second branch, then 6f for the new contract | — |
| **Refactor / restructure** | **6c-bis** below (`/code-restructuring` Steps 1–6) | 6d, 6f |
| **Mechanical migration** (`Type: Migration` · `Behaviour: preserves`) | **6c-quater** below | 6d unless it owns a new adapter surface |
| **Infra / toolchain** | **6c-quater** below | 6d, and 6f where no test can reach the change |
| **Test rebalance** | **6c-quinquies** below (`/plan-test-rebalance`) | 6d |
| **Test-style migration** (`Type: Test Style` · `Behaviour: preserves`) | **6c-quater** below — the baseline is each suite's V2 before-state (titles, count, coverage, fluent score with per-test rows; `testing/references/fluent-style.md`) | 6d, 6f |

**Whatever the route, this node's commit must contain the guardrail its `## Verification` section
promised**, and 6e presents exactly that. A pass-2 commit that contains a plan but not the baseline
it claims, or a stub but not the reproduction that justifies it, is a node that will reach `/green`
with nothing to check it.

**6c-bis. A Refactor node's pass 2 is a plan, not stubs.** Follow `code-restructuring` steps 1–6:
record the baseline (green except any known-red tests it inherits), run `/analyze-code-issues` on the
target, analyse the seams, and write the `plan.jsonl` plus the restructure changeset's State B and
Callers. **Do not `restructure apply` here** — that is this node's `/green`. Its commit 2 is the
plan, the baseline and the changeset updates. It has **no acceptance tests and no failing unit
tests**; say so in the report rather than inventing some. **Before it moves on: does the recorded
baseline actually execute the code the plan moves?** Where it does not, write the missing test (V1)
now, in this same commit — an untested file's green baseline verifies nothing, and this is the last
point at which that is cheap to fix. Then 6e (the baseline and any gap-filling test are what it
verifies and records) and 6g.

**6c-ter. A behaviour-changing node's pass 2 — two branches, and they are not the same.**

- **A Bug fix reproduces the defect.** Follow `/reproduce`: find the existing suite that covers the
  affected code (a new suite only when nothing does), and write a test that fails **because of the
  defect** — not because a symbol is missing. Verify the failure mode is the reported one, at the
  tier the rhombus rule picks rather than the tier that is easiest to reach. If the fix needs a
  symbol this node owns that does not exist yet, add that stub per 6d; otherwise skip 6d.
- **A Contract change has no defect to reproduce.** Nothing is wrong today — the contract is being
  *changed on purpose*, so demanding a reproduction is asking for a test of a bug that does not
  exist. Its red step is instead: tests asserting the **new** contract (failing, because the new
  behaviour is not implemented), plus **preservation tests for every part of the old contract that
  must survive** — the technique from `/plan-tdd-migration`, used for the surviving half only.
  `/plan-tdd-migration` alone is **not** the whole owner here: that command requires features to
  remain unchanged, which is exactly what this node does not do. Take the new-contract half from
  `/plan-red`'s behaviour-changing path and continue into 6f for it. A deprecation or removal is
  this branch too: the new contract is that the symbol is gone, the callers moved, or the warning
  fires.

Then 6e and 6g.

**6c-quater. A mechanical-migration, infra or test-style node's pass 2 is the recorded proof.** There is no new
behaviour to accept and nothing red to write against a missing implementation, so the commit records
the guardrail instead:

- **the baseline** — the suites this node's `## Verification` names, run now, with their pass/fail
  counts written into the changeset as the before-state;
- **the gap-filling tests** — wherever the baseline does not cover what the migration moves, the
  behaviour-preservation test that makes it cover it (V1 before V2, per `/plan-tdd-migration`). This
  is the substance of the commit for most migration nodes;
- **the deterministic command** — for an infra or toolchain node, the V3 command with its full
  before-output recorded (a build, a type-check, a generated-artifact diff, an analyzer count). A
  reviewer must be able to re-run it and compare.

An infra node that can reach **no** executable guardrail at all is the V4 case, and it was approved
in Step 1 — write the numbered procedure and the evidence to be captured, and do not discover the
need for consent here. Then 6e and 6g.

**6c-quinquies. A test-rebalance node's pass 2 is the replacement tests, never a deletion.** Follow
`/plan-test-rebalance`: the lower-tier tests that must exist **first** are written and green in this
commit, with the equivalence proof that they cover the same code as the tests above them. Those
replacements are **V1-characterisation**, not fail→pass — they are green the moment they are written,
because the behaviour they pin already exists — so the equivalence claim needs its own **V3**
measurement: record `cov-acc unique --tier e2e` before, and the same command after, with the gate
being that every line the plan promised to move down is gone from the after-list. **Nothing is
deleted in pass 2** — the deletion is this node's `/green`, and only after the replacements are
proven. A commit that deletes an e2e test here is a coverage cut with a tidy name. Then 6e and 6g.

**6d. Write the compile-only stub API this PR owns** — for a node that owns new public symbols
(every Feature node; a bug fix or migration node only where the fix introduces a surface this node
owns). A Refactor or test-rebalance node owns no new surface and skips this step.
- Create the public symbols this PR owns with correct signatures/types; body throws
  `NotImplementedError` (or returns a typed placeholder) and is annotated `// TODO(pr-<k>): implement`.
- Ensure the branch **type-checks and builds** (`uv run mypy`) with only stubs —
  this is what lets successors compile against it and every `/green` run concurrently.
- **Never touch a predecessor-owned stub**, however small the change looks. If this PR needs a
  different signature from a predecessor, that is a plan change: stop and raise it.

**6e. The guardrail, verified and recorded — every kind, no exception** (`/plan-red` Step 8 for a
Feature node).

The verification never changes; what it covers changes with the kind. This is what will catch this
node being wrong, and it is **per PR** — one layer's guardrail says nothing about the next. There is
no review gate here: pass 2 carries on to 6f / 6g, and what each bullet below lists goes into
Step 9's summary under **Decided without review**, one block per node, so the developer sees every
guardrail at the end of the turn rather than one at a time in the middle of it. A guardrail that
cannot be made to hold (a test that will not fail for the right reason, a baseline that does not
execute what moves) is a **halt**: write the node's guardrail row ⛔ with the evidence and the
options (the `pr-lifecycle` skill § *Halts*), stop pass 2 at this layer, and end the turn with the summary.

- **Feature** — for each acceptance test in this PR's changeset, write a fully implemented test (not
  a placeholder) that fails because **this PR's** implementation is missing. Verify each fails for
  that reason. Record the test titles, file paths with line numbers, what each validates, and
  confirmation all are failing.
- **Bug fix / behaviour-changing migration** — record the reproduction test and **the failure
  message it produces**, which is the evidence it reproduces the reported defect rather than a
  missing symbol. For a migration, record the new-contract tests beside the preservation tests.
- **Refactor / mechanical migration** — record the **baseline**: the suites, their pass/fail counts,
  and the evidence they execute the code that will move. Name any gap found and the test written to
  close it. There are no acceptance tests here; say that plainly rather than presenting the baseline
  as though it were one.
- **Infra / toolchain** — record the V3 command and its before-output, or the V4 procedure and the
  evidence it captures (with the Step 1 consent line quoted).
- **Test rebalance** — record the replacement tests, green, and the equivalence proof. State
  explicitly that nothing was deleted.
- **Test-style migration** — record each suite's before-state (titles, count, coverage, fluent score
  with per-test rows). There is nothing to be red about; say so.
- **Every kind** — any test this commit writes is fluent (`fluent-tests` skill, ≥ 8 on
  `.agents/skills/testing/references/fluent-style.md`), whatever style the suite it lands in has.

Tick the Red row's `Create failing acceptance tests` and `Run acceptance tests (verify they fail)`
TODOs in this PR's changeset — or, for a node with no acceptance tests, the equivalent items its own template
carries (`Baseline recorded`, `Reproduction verified`, `Verification method executed`).

**6f. Failing unit/integration tests** (`/plan-red` Step 9) — for a node whose commit has an
implementation to be red against: every Feature node, and the new-contract half of a
behaviour-changing migration. A behaviour-preserving node has nothing to be red about; its
equivalent work was 6c-bis / 6c-quater / 6c-quinquies.
- Write comprehensive failing tests for **this PR's own API surface** — main functionality, edge
  cases, error scenarios, API boundaries. Define the public API through test usage. Tests must fail
  for the right reason (missing implementation, not bugs) and must **not** depend on any successor PR
  being green.
- **Check each test against the predecessors' stubs.** A test that drives a predecessor-owned symbol
  still marked `TODO(pr-<earlier>)` cannot pass until that PR is green. For each such test, either:
  - **inject a double** at the seam, when the predecessor is incidental to what the test asserts; or
  - **keep the real object** when the integration *is* the point — and record the sequencing in this
    changeset's `## Stack Context` → `Greenable independently?` answer **and its `### Green wave`**.
    Keeping the real object is what moves this PR out of wave 1: it is now in the wave above the PR
    whose behaviour the test needs. The waves were planned from intended edges; this step is where
    the *actual* edges are decided, so this is the moment the grouping becomes true.

  **A wave change here does not re-cut the branches.** The line was derived from the waves in Step 1
  question 8 and the branches exist; re-deriving it now would mean rebuilding the stack. Record the
  corrected wave, fix the PRs this one now blocks or no longer blocks (own changeset only — a
  sibling's row is theirs to fix), and **report the drift in Step 9**: say which PR moved wave, and
  whether the line still leads each wave with its blockers, under **Decided without review**.
  Reordering is the developer's to do, by editing the stack, before any node's Green row runs.

  Do not silently leave it: a test blocked on a predecessor looks identical to a broken test.
- A quick way to find them — every `TODO(pr-N)` for an **earlier** N that this PR's tests reach:
  ```bash
  grep -rn "TODO(pr-" <pkg>/src | grep -v "TODO(pr-<this-k>)"
  ```
- Verify: build passes (stubs), tests fail correctly, **and each failure is attributable to this PR's
  own missing implementation** rather than a predecessor's. Tick the Red row's `TDD Red — write failing
  unit/integration tests` TODO.
- If this step needed more exploration, append it to this PR's `{slug}-initial-discovery.md` as a
  new `## Exploration N` section.

**6g. Commit 2 — the red step — and push.**
- Close this node's planning rows in its `## Workflow` (*Node kinds* § *Which rows the two planning
  commits close*): back-fill commit 1's SHA into the Plan row, close the guardrail row ✅ with
  today's date and its evidence (`14 failing — commit 2`, `baseline 84/84 — commit 2`). Every row
  below stays ⬜ — it is not this command's.
- Update this PR's changeset: the TODO check-offs from 6e/6f, the PR number and URL noted in 4d into
  `## Stack Context` (replacing `#pending`), and any `Greenable independently?` **and `### Green
  wave`** refinement from 6f. The wave rows need **no renumbering**: they were written in node
  numbers, which have not changed. The `#pending` being replaced here is this PR's **own** GitHub
  identity, not a sibling reference. **Also replace `## Stack Context → Epic`'s `#pending`** with
  the epic URL Step 5's 3b stamped into the PR body — the second and last `#pending` in the
  changeset; leaving it makes the changeset incomplete. Own files only — never a predecessor's changeset or PRD.
- **Update this PR's description to match**, in this same step, with the `gh api -X PATCH` from 4d:
  the `## Stack` block's wave line, `Concurrent with:`, `Blocks:` — and the `Verification:` line if
  6c-route's work changed the rung (a V2 node that found a baseline gap and wrote a test for it is
  now V1 for that part, and the changeset says so). The description is not a
  committed file, so it does not affect the two-commit shape — but it is what an implementer reads
  first, and a stale "startable now" on GitHub sends somebody into a PR that cannot go green.
- Commit this node's red step — stubs and tests, or the plan and baseline, or the recorded command,
  whatever 6c-route produced — plus these doc updates as **one commit**, the PR's second. Never amend commit 1.
  If something must change after this commit is pushed, add a third commit — never amend, never
  `--no-verify`.
- Push **this branch only** — a plain push; the rebase in 6b already force-pushed with lease:
  ```bash
  git push origin HEAD
  ```
  Do **not** re-run `gh stack submit` — the PR exists and submit is stack-wide.
- Verify the two-commit shape and the diff scope:
  ```bash
  git log --oneline origin/<base>..HEAD                         # exactly TWO commits: plan, red
  gh pr view --json number,isDraft,baseRefName,changedFiles \
    --jq '"#\(.number) draft=\(.isDraft) base=\(.baseRefName) files=\(.changedFiles)"'
  ```
  Still `draft=true`, still based on its predecessor, and `changedFiles` covers only this PR's docs,
  stubs and tests. An inherited stub or a predecessor's doc in that list means 6b did not finish
  cleanly — go back to it before moving up.
- Move to PRₖ₊₁. Its `gh stack view` row is now `⚠` — expected; its own 6b clears it.

## Completion gate

### Step 6h: Revise the epic — MANDATORY

Pass 2 can change what the epic recorded at pass 1: a PR moved between waves (6f), a node added or
split, a title corrected, a dependency found or dropped. Re-read the epic body and reconcile it with
the final state **before** the gate reports: nodes (number, title, kind), line edges against the PR
bases (`gh stack view`), **dependency edges against every changeset's `### Green wave` and each PR
body's `Wave k of m`**, and the derived waves and line. Correct the fenced block only
(`pr-stack` skill § *The epic must be correct*), run `issue sync <slug>`, and re-verify. Report in
Step 9 either "epic matches the plan" or each edge changed and why.

### Step 7: Restore the original branch — MANDATORY

Every PR now carries its plan and its red step. This worktree's job as planner is done; do not
leave it sitting on the top stack branch (that would pin it).

1. Confirm a clean tree and that the top branch is pushed:
   ```bash
   git status --porcelain | grep -v '^?? '        # must be empty
   git rev-list --count origin/$(git branch --show-current)..HEAD   # must be 0
   ```
2. Capture the topology while a stack branch is still checked out (it is quoted in Step 9;
   `gh stack view` errors on a non-stack branch):
   ```bash
   gh stack view
   ```
3. **Restore the starting branch — including `master`.** This worktree must end on the same named
   branch it started on, not detached and not on a stack branch:
   ```bash
   git checkout "$ORIGINAL_BRANCH"
   git branch --show-current   # must equal ORIGINAL_BRANCH
   ```
   If this worktree started on `master`, that command is `git checkout master` and
   `git branch --show-current` **must print `master`**. Leaving it on `origin/master` (detached),
   on `pr-n-<slug>`, or on any other stack branch is a defect — it pins that branch and is not a
   restore. The Step 4a detached `origin/$TRUNK` checkout is only for cutting PR₁; it is not the
   restored state.
   **Do not delete this worktree.** **Never delete the stack branches** — each is a successor's
   base, and deleting one closes that PR.

### Step 8: Cascade `/pr-stack-rebase` over the whole stack — MANDATORY

With this worktree on `$ORIGINAL_BRANCH` and every stack branch free, run the cascade from here:

```
/pr-stack-rebase from #1 to #<n>     # stack positions, bottom-up
```

Say explicitly that `#1..#n` are **stack positions**, not PR numbers. Cascade mode borrows this
worktree for each layer (nothing pins the branches), rebases bottom-up, and **restores
`$ORIGINAL_BRANCH` itself** when it finishes or stops.

**Expected result: every layer reports *already current, leak-free, no rewrite*.** Pass 2 rebased
each layer immediately before its second commit, so the cascade is the proof, not the fix. Read its
report per layer:

- **all current** → the stack is coherent; continue to Step 9.
- **a layer was STALE and got rebased** → something moved after its 6b (trunk, or a concurrent
  commit from elsewhere). The cascade brought it and everything above it current; note in Step 9
  which layer and why. Its build/test verdict per layer must be reported, never assumed.
- **the cascade stopped** (conflict, pinned worktree with unpushed work, unverifiable build) → the
  stack is **not** complete. Report which layers were done, which stopped, and which were not
  attempted, and halt the stopped layer's guardrail row ⛔.

Then confirm the restore held:

```bash
git branch --show-current   # must equal ORIGINAL_BRANCH — the cascade restores it, verify anyway
```

### Step 9: Present the Stack — the end-of-turn summary

The skill's summary (`.agents/skills/pr-lifecycle/SKILL.md` § *Summary*) for a whole stack:
one **Row** line and one **Next row** per node; under **Decided without review** every node's
guardrail as 6e recorded it, each PRD's headline decisions, wave drift from 6f, any
`Workflow override` written into a node's rows. Present a complete summary:
- **The final title of every PR**, as one list, showing the shared slug and ascending `K/N`. This is
  what Step 5's revision pass produced; re-read them now — if pass 2 shifted scope between layers,
  fix the affected title with the same `gh api -X PATCH` and report the corrected list.
- **Confirmation the stack is registered on GitHub** (quote the
  `✓ Stack created on GitHub with N PRs` line; for a single PR, quote that draft URL and note the
  stack object appears at ≥2 PRs). There is no manifest path to report — each PR's context is in
  its own changeset.
- **The Step 8 cascade verdict per layer** — already current or rebased, and each layer's build/test
  state. This is the line that says the stack is coherent.
- **This worktree is back on `$ORIGINAL_BRANCH`** (if that was `master`, it is on `master` — confirm
  `git branch --show-current`). `/green` on those PRs is unblocked now that the completion gate has
  run.
- Per PR: number + URL, branch, base (`$TRUNK` for PR₁), its **kind**, the **two commits** (plan,
  red), PRD (or `none — <kind>`), changeset, discovery companion, owned API/stubs, and **the
  guardrail its kind produced** — failing acceptance + unit/integration test titles and paths for a
  Feature node; the reproduction test and its failure message for a bug fix; the `plan.jsonl` and the
  recorded baseline for a Refactor; the preservation tests and baseline counts for a migration; the
  recorded command output for an infra node; the replacement tests and equivalence proof for a
  rebalance. Confirm the build passes and that each failure is attributable to *this* PR.
- **The kinds and the verification rungs, as one table** — the answer to "what kind of stack is
  this", which a reader cannot get from `gh stack view`:

  ```
  n1 refactor   V2 baseline (session-replay suite, 84 cases, covers all 3 moved seams)
  n2 fix        V1 reproduction — test_slam.py:212, fails on wrong map-frame position
  n3 feature    V1 4 acceptance + 19 unit/integration
  n4 chore      V3 `uv run pytest -q` — 70 errors before, 70 after
  ```

  Flag every node that is **not V1** and say what blocked V1 there; flag any **V4** with its consent
  line. A stack whose nodes are mostly V2/V3 is a legitimate stack, but the developer should see that
  shape before any Green row runs rather than at review.
- Successor **branches** named in each changeset's Stack Context, plus each PR URL (do not expect
  predecessor docs to have been edited from a successor branch).
- **The green waves** — the headline of this report, because it is what decides who does what next:

  ```
  Wave 1 (startable now)   n1 token store (3 dependents)   n2 proto   n3 config
  Wave 2                   n4 issuer  — needs n1 to really persist a token
                           n5 metrics — needs n1 to really persist a token
  Wave 3                   n6 login   — needs n4 to really issue one
  line  n1, n2, n3 · n4, n5 · n6      (· = wave boundary; bottom of the stack on the left)
        n1 → #2401   n2 → #2404   n3 → #2405   n4 → #2402   n5 → #2406   n6 → #2403
  ```

  **Report in node numbers, with the node → PR/branch mapping printed once**, as above. The waves
  were settled before any PR existed and every committed document states them that way; a report
  that silently switches to PR numbers is a second vocabulary the reader has to hold, and it will
  not match the changesets they open next.

  Give, per wave: the nodes in it, and for every node above wave 1 the predecessor **behaviour** it
  waits on — **each one named**. A node with no such reason is wave 1, however high it sits in the
  line; the commonest error in this report is padding the later waves with nodes that were merely
  described later. Above, n5 is wave 2 rather than wave 3 precisely because it waits on n1, not on
  n4 — so it runs concurrently with n4, even though it sits above it in the line.

  Then name the transitive-dependent count that put each wave-leading PR where it is in
  the line, and say what flattening cost — which same-wave PRs could have been worked in parallel
  and now sit one above the other. If pass 2 moved any PR between waves (Step 6f), say which and
  whether the line still leads each wave with its blockers; reordering is the developer's to do
  before any node's Green row runs.
- **The deferred-work verdicts**, per node: which `<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/` items each
  node runs into, which **stack node** owns each fix (including any ground-softening node this
  command added to the stack).
- **Any systemic restructure node**: its position, which nodes it will rewrite under, and — stated
  plainly, because it looks like a defect otherwise — that those nodes are planned against the
  pre-restructure structure on purpose and will need a repair commit after it greens.
- **Each node's `## Workflow` preset and its next row** — `/green` for most kinds,
  `/code-restructuring` for a Refactor node, whatever an override wrote in. The rows in the
  changeset are what runs; an implementer who runs the wrong command on a mixed stack will look for
  stubs that were never planned.
- `gh stack view` output from Step 7 (captured before restoring the original branch).
- Anything the local validator cannot prove (server-side checks, org policy), stated as a risk.

### Step 10: Where each node goes from here — its own `## Workflow`

**Do not create per-PR worktrees from this command, and do not `gh stack checkout` in this
worktree after restore** — that would pin a stack branch here again. Each branch is already on the
remote with an open draft PR; this worktree stays on `$ORIGINAL_BRANCH`. Whoever picks up a PR
creates a **different** checkout:

```bash
git worktree add <path> pr-<k>-<slug>
# or, in a worktree that is free to move:
#   gh stack checkout <PR#>
cd <path> && uv sync --group dev && uv run mypy
```

**What runs on a node is its changeset's `[wf]` rows, not this command.** Its next row (the
skill's next-row grep) is the next step, with that row's command (`/green`, `/code-restructuring`,
`/green-100`, `/plan-tdd-migration`, or whatever an override wrote in). Whoever advances it — the
developer by hand, `/next` for one row, `/yolo` for all of them, `/yolo-pr-stack` for every node of
the stack at once — reads it from there (`.agents/skills/pr-lifecycle/SKILL.md`
§ *Runners*). **Running `/green` on a Refactor node is the wrong command** and will look for stubs
nobody planned — which is why the node's rows name its own implementer instead of leaving each
reader to derive it from `Type`.

Start only the nodes in the **current green wave** — wave 1 at first, then wave 2 once wave 1's
Green rows are ✅, and so on; the rest wait for their predecessor. Each PR's wave is on its own
description and in its changeset's `### Green wave`, so an implementer reads it without a
whole-stack document.

**A wave is a throughput knob, not an instruction to start everything in it.** Every Green row adds
commits, so finishing one PR leaves every PR above it stale: a wave of six concurrent greens is six
cascades of `/pr-stack-rebase`, and in this monorepo each concurrent PR also needs its own ~7 GB
worktree. Two batches of three is a legitimate choice — make it deliberately rather than discovering
the cost.
Each changeset's `Inherited Dependencies` section tells its implementer which symbols to leave
alone. `/green` and `/green-attack` rebase first and **halt** if required ancestor functionality is
still a stub.

**Every row's command on a stack branch runs `/pr-stack-rebase` first** — `/green` (then its
ancestor-functionality gate), `/validate-changes` inside `/pr-wrap`, `/pr-wrap` itself — and a row
that commits on a stack branch also pushes, because a stack branch is a successor's base and a row
in a registered stack: unpushed work is invisible to both. Those are procedures the row's command
uses, not steps of their own.

**To pick up a moved base, each worktree rebases itself with `/pr-stack-rebase`** — it rebases only
the branch checked out there and force-pushes only that branch. Do **not** run `gh stack sync` or
`gh stack rebase` from a per-PR worktree: they cascade over the whole stack, and git refuses to
update a branch pinned by another worktree. Rebase bottom-up — a predecessor's worktree first, then
its successors (whose `gh stack view` rows go `⚠` until they do).

**Each implementer worktree is temporary.** Remove it once every row of that node's `## Workflow`
is ✅ or ➖ — immediately, unless the user asked to keep it:

```bash
git worktree remove --force <path> && git worktree prune
```

Two reasons, and both bite in practice: a worktree costs **~7 GB** here once dependencies are
installed, and while it exists it **pins that branch**, so any stack-wide `gh stack sync` / `rebase`
fails until it is gone. Verify nothing is unpushed first (see the `pr-stack` skill); if there is,
push, or use `/abandon-worktree`. Never delete the branch — that closes the dependent PR.

Recreating later is cheap: `gh stack checkout <PR#>` plus a fresh install.

Landing a finished stack is stack tooling, not a `## Workflow` row: **`/fix-pr-stack`** prepares it
(waits for CI/review bot on the current SHA, sweeps comments, rebases, local-gated fixes) and
**`/merge-pr-stack`** lands it (CI-gated `merge-async`, GitHub restacks) — see the `pr-stack` skill. `/merge` and `/repoint` remain the fallback for an unregistered stack.

## Out-of-Scope Ideas

During planning and code analysis, ideas outside the stack's scope go into **a new file** in
`<package-dir>/docs/todo/` — `YYYY-MM-DD-<slug>.md`, `**Category:** Future enhancement`, `**Source:**` the
stack slug. Never add a second item to an existing file (updating an item's own file is a
different thing, and is required).

`<package-dir>/docs/todo/` is read as well as written: Step 2b scans it for items this stack runs into and
Step 4b records them per node. The two directions are complementary — what this stack defers is what
somebody's Step 2b finds next, so write entries stating **why** the work was deferred, not only what
remains. That reason is what tells the next planner whether it blocks them.

`/fix-pr-stack` reads them again before any merge: every TODO whose `**Source:**` names this stack
is reckoned with while the PRs are still open, so the *when it becomes possible* line is worth writing
carefully — for a stack-internal deferral it is usually "when PR #NNNN lands". `/merge-pr-stack`
Wave 4 executes the disposition chosen there.

## Rules

- **`gh stack` is required.** If it is not installed, stop and ask the user to install it. Never
  substitute plain `gh pr create` for a stack.
- **Every stack this command plans carries an epic issue — the DAG's home** (Step 5's 3b): created
  here from the settled plan, kept current by `overstack issue sync` at landing wave boundaries.
  GitHub stays the source of truth: the stack object + PR bases for topology, the epic for the
  DAG/waves.
- **Refuse a detached start.** `ORIGINAL_BRANCH` must be a named branch; if
  `git branch --show-current` is empty, stop.
- **Cross-check `<package-dir>/docs/todo/`, every in-scope `<package-dir>/docs/code-issues/` and the open
  deferred answers (`<package-dir>/docs/deferred-answers/`, `docs/<area>/deferred-answers/`) (Step 2b) before
  decomposing.** An open deferred answer the stack would build on is a question for the interview. Record every relevant item in the affected node's `## Prerequisites` with a verdict;
  give a blocking one a TODO under the row that clears it; give a large or shared-code one its own **stack node** or
  its own Restructure Prerequisite. Never a PR off `$TRUNK`. Never absorb a large restructure into a
  feature node.
- **Every PR this command opens is a stack member.** Ground-softening and code-improvement PRs the
  user approved are nodes — `gh stack init` / `gh stack add` — not sibling PRs off `$TRUNK`.
- **The kinds matrix is the default, not a gate.** When the developer names a different workflow for
  a node, or the slice fits no listed kind, give them the mechanical consequence and a recommendation
  (recommended option first), then **follow their decision** and record it in that node's
  `## Decisions & Trade-offs` so the missing artifact reads as a choice. Per node, not per stack.
  Prefer a command that already implements what they asked for over improvising one. The single
  thing not up for preference is that the node has a `## Verification`
- **Settle every node's kind in the interview (Step 1 question 2), per slice, before the edges.**
  The family — behaviour-adding / changing / preserving — decides that node's artifacts and the shape
  of its proof; the kind decides which command plans it. Never infer a node's kind from the stack's
  purpose: a feature stack routinely carries a fix under it and a migration beside it. A node whose
  kind cannot be settled has two families in one diff — split it, which is free before pass 1
- **Every node writes its own changeset, whatever its kind.** A stack node is picked up with none of
  the planning conversation in context, and the changeset is the only carrier of its background,
  State A/B, boundary, inherited dependencies and verification. What the kind varies is the **PRD**
  (none for a behaviour-preserving node, and for a fix or migration with no user-visible delta), the
  changeset **template**, and the contents of **commit 2**
- **No node without verification, and no branch for a node that has none.** Every changeset carries
  `## Verification` naming the highest rung it reaches — V1 an executable test, V2 a recorded
  baseline that demonstrably covers what moves, V3 a deterministic command with its before-output,
  V4 a scripted manual procedure with the developer's recorded consent. Tests are the default, not
  the fallback; where a lower rung is chosen, name what blocks the higher one. "This code has no
  tests" is the reason to write one, not a blocker. V5 is never acceptable
- **A V2 node that finds a baseline gap writes the missing test first**, in its own commit 2. A green
  baseline over an untested file is a coincidence, not a guardrail
- **Pass 2 routes by kind (Step 6c-route)** — a Feature node's red step is stubs and failing tests; a
  bug fix's is a reproduction red *for the defect*; a Refactor's is a `plan.jsonl` plus a baseline; a
  migration's or infra node's is the recorded proof; a rebalance's is the replacement tests, and it
  **deletes nothing in pass 2**. Follow the command that owns the kind rather than working from
  memory
- **6e verifies every kind, and gates nothing.** What it verifies changes — tests, a reproduction
  failure message, a baseline with its coverage evidence, a recorded command output — and every
  node's guardrail is listed in Step 9's summary under **Decided without review**. One layer's
  guardrail never stands in for the next. A guardrail that cannot be made to hold halts that node's
  row ⛔ and stops pass 2 there
- **Every changeset carries `## Workflow`, from its kind's preset** (the `pr-lifecycle` skill § *Presets*:
  Feature and contract change → feature, Bug fix → bugfix, Refactor → restructure, mechanical
  migration → migration, Test rebalance → rebalance, Infra → infra). Commit 1 closes the Plan row,
  commit 2 the guardrail row; the rows below are the node's to run, and this command names none of
  them
- **`<type>` in each PR title follows that node's kind** (`feat` / `fix` / `refactor` / `chore` /
  `test`). A squash merge makes it a permanent `master` commit message, so a `feat` on a
  behaviour-preserving node is a false changelog entry nobody can correct
- **Suggest a ground-softening restructure, never impose one**, and do it once for the whole body of
  work rather than per node. A decomposition that can only be cut by layer, or two nodes that keep
  wanting the same file, is the structure fighting the plan — propose the restructure that makes a
  vertical slice possible.
- **A systemic restructure node does not block the planning of the nodes above it**, and its
  execution is *allowed* to break their stubs, contracts and red tests. Plan them against the
  pre-restructure structure, declare it in each one's `## Inherited Restructure — expect rewrite`,
  and repair the fallout as a follow-up commit on the affected branch after its `/pr-stack-rebase` —
  never by amending a planning or red commit, and never by editing the restructure node from a
  successor branch.
- **A restructure node has no PRD and no acceptance tests**, and its pass-2 commit is a
  `plan.jsonl` plus a recorded baseline, not stubs and failing tests. `restructure apply` is its
  `/green`, not its pass 2 — and that `/green` deletes the plan once applied; it never goes up for
  review.
- **The line is derived from the green waves, never volunteered.** Waves concatenated; inside each
  wave, most transitive dependents first, PRs nothing waits on last. A PR that depends on nothing
  belongs in wave 1 and at the back of it.
- **Every changeset carries `### Green wave` and every PR description carries the same wave line**,
  and the two stay in sync — including when pass 2 moves a PR between waves.
- **The epic's block is the third copy of the waves, and the only one overstack reads.** Created at
  Step 5's 3b with its dependency edges added, revised in Step 6h. A stack whose epic has only
  `line` edges shows as a linear chain, whatever the PR bodies say.
- **Waves, concurrency, blocks and edges are written in node numbers** (`n1 … nN`), which exist from
  the moment the decomposition is settled. Never leave a PR-number slot to back-fill after submit. A
  PR number appears only where the dependency is on the **composition of an already-open PR**, and
  then alongside its node: `n3 (#2403)`.
- **A PR states its own wave and nothing else.** No committed whole-stack wave table.
- **Two passes, two commits per PR.** Pass 1 commits docs only (PRD, changeset, discovery) and opens
  the draft; pass 2 adds exactly one red commit (stubs + failing tests + changeset check-offs).
  Never amend commit 1; a correction after commit 2 is pushed is a third commit.
- **Pass 1 writes no `src/`.** No stubs and no tests until pass 2 — the stack must exist on GitHub in
  full before any branch is rewritten.
- **Pass 2 runs bottom-up and rebases before it writes.** Each layer's Step 6b `/pr-stack-rebase`
  (single mode) comes before its build, stubs and tests; skipping it means compiling against a
  predecessor that has no stubs yet. Verify `origin/<base>..HEAD` is one commit after the rebase and
  two after the red commit.
- **Submit each PR as soon as its branch is planned.** `git push -u origin HEAD` first (this branch
  only), then `gh stack submit --auto`. Submit once per PR, in pass 1; pass 2 pushes plainly and
  never re-submits. If submit fails because a predecessor is pinned, halt the node's Plan row ⛔ — do not
  `--force`, do not `gh stack sync`.
- **Nobody pins a stack branch until Step 8 has run.** Pass 2 must check every branch out here, and
  the cascade must be free to borrow each one. If a branch is pinned, halt its guardrail row ⛔; do not work
  around it with a second worktree.
- **`gh stack init --base "$TRUNK"`** — never assume `master` when the user named another trunk.
- **Use this worktree.** Create and check out each next stack branch in place (`gh stack init`, then
  `gh stack add`). After a layer is pushed in pass 1, do not return to it until pass 2 reaches it.
- **Restore `$ORIGINAL_BRANCH` when pass 2 is done**, including when that branch is `master`, and
  **then run the cascade `/pr-stack-rebase from #1 to #n`** as the completion gate. Confirm
  `git branch --show-current` matches afterwards. Do not leave this worktree detached or on a stack
  branch. Do not delete this worktree. Never delete the stack branches.
- **The cascade is expected to be verify-and-return on every layer.** A rebased layer is a finding to
  report, a stopped cascade means the stack is not complete and `/green` is not unblocked.
- **Never edit a predecessor's changeset or PRD from a successor branch.** Name the successor
  **branch** in this PR's own Stack Context before `gh stack add`. The PR's own number and URL go
  into its own changeset in pass 2 (Step 6g).
- **Title every PR at 4d, then revise all of them in Step 5.** The per-PR title is a projection;
  the revision pass is where `N`, the shared slug, and any `--auto` leftovers are corrected. A title
  is not planning output — it is the commit message that lands on `master`. Re-read them in Step 9.
- **Never pass `--open` to `gh stack submit`** in this command; it would publish drafts for review.
- **Never run `gh stack unstack`** (it deletes the stack on GitHub) without explicit user consent.
- **Per-PR `/green` worktrees rebase themselves with `/pr-stack-rebase`**, bottom-up. `gh stack sync`
  / `gh stack rebase` are stack-wide and belong to a worktree where every stack branch is free.
- **Delete a temporary implementer worktree** once every row of that node's `## Workflow` is ✅ or
  ➖, unless the user asked to keep it. Verify nothing is unpushed or uncommitted first, and never delete the branch
  itself. Do not create those worktrees during planning.
- Never skip the interview, the per-slice kind question, or the decomposition question — they
  gather input before anything is written. Never skip the per-PR guardrail verification in Step 6e
  — whatever that node's kind makes it (tests, a reproduction failure, a baseline, a recorded command
  output) — and never present it as a gate: it goes into the summary.
- **Build must pass before writing any tests** (Step 6c) — on planning docs plus inherited stubs
  alone. If it does not, stop and report the exact failing command; never patch a predecessor's stub
  to get past it.
- Each PR is **independently mergeable**: self-contained tests, no dependency on a successor's green,
  and **safe to merge to trunk alone** — production and local dev workflows keep working; local dev
  data may break; production data impact only with explicit Step 1 consent, recorded in the
  changeset.
- **Every changeset but PR₁'s declares its inherited dependencies** and answers
  *Greenable independently?*. A PR that needs a predecessor green first is acceptable; an undeclared
  one is not.
- **Never implement a symbol another PR owns**, however small the stub looks.
- Every cross-PR forward dependency is a **stub owned by the implementing PR**; the branch must build
  on stubs alone.
- Draft PR bases form the stack (predecessor branch), not `$TRUNK` (except PR₁, whose base is
  `$TRUNK`).
- Never link a successor's docs back to a predecessor. Do not patch predecessor docs from a
  successor branch to satisfy that rule.
- Tests fully implemented, no conditional logic, no fallbacks, no try/catch to swallow errors.
- Never put "red phase"/"green phase" in code or test descriptions.
- Never use `--no-verify`.

## Flow

```
/plan-pr-stack
  record ORIGINAL_BRANCH (stop if detached) and TRUNK
  interview → KIND per slice + verification rung + trunk-merge safety per slice (prod + local dev;
              local dev data may break; prod data only with explicit consent)
  → whole-work discovery → cross-check the deferred-work records
  → propose any ground-softening restructure (ask; once for the whole work)
  → size each fix: in-node, Restructure Prerequisite, or its own stack node (never a PR off trunk)
  → group the PRs into GREEN WAVES (wave 1 = startable now; wave k = unblocked by the waves below)
  → derive the line from the waves: waves concatenated, blockers leading each wave
  → settle slug, owned surfaces, per-PR wave, per-node kind + verification method
  → PASS 1 (per PR, in this worktree, in order)
        gh stack init --base "$TRUNK" | gh stack add
        changeset (ALWAYS — incl. ## Workflow from the kind's preset, Plan row ✅,
          ### Trunk-merge safety, ### Green wave, ## Verification) + discovery
          + PRD only when the kind warrants one → commit 1 (docs only)
        git push -u origin HEAD → gh stack submit --auto → retitle (<type> = the kind)
        → body: ## Stack block with Kind, Verification, **Wave k of m**, concurrent-with, blocks
  → checkpoint: gh stack view (no ⚠), revise every title, open the epic issue (the DAG's home) + stamp its URL into every PR body, delete whole-work discovery, report
  → PASS 2 (per PR, in this worktree, in order PR₁ → PRₙ)
        git checkout pr-k → /pr-stack-rebase (single; picks up the predecessor's stubs)
        build + baseline → ROUTE BY KIND:
          feature   → stubs → failing acceptance tests → failing unit/it tests
          fix       → reproduction test, red for the defect (+ stub only if it owns one)
          refactor  → plan.jsonl + recorded baseline (+ the test the baseline is missing)
          migration → baseline + behaviour-preservation tests (+ new-contract tests)
          infra     → the deterministic command with its before-output recorded
          rebalance → the replacement tests, green, + equivalence proof (delete nothing)
        → verify that guardrail (every kind; recorded for the summary, no gate) →
        commit 2 (the guardrail + changeset check-offs + ## Workflow Plan/guardrail rows ✅ + own PR URL + refined wave)
        → git push origin HEAD → PATCH the PR body's wave line to match
  → git checkout ORIGINAL_BRANCH   # if that was master, this worktree is on master again
  → /pr-stack-rebase from #1 to #n   # completion gate: every layer already current, leak-free
  → Step 9 summary: per node its rows, Decided without review (guardrails, PRDs, wave drift), next row
  → (per PR, in the implementer's own worktree, when its GREEN WAVE is clear — wave 1 first)
        the node's [wf] rows, in order, each with its command — by hand, /next, /yolo,
        or /yolo-pr-stack; every row's command runs /pr-stack-rebase first on a stack branch
        /pr-stack-rebase  → also whenever this branch's base has moved (this branch only)
  → gh stack sync (restack / retarget between merges, from a stack-wide worktree)
```

Unregistered-stack fallback only: `/merge` (stay current with base) → `/repoint` (onto master after
the predecessor lands).

## Related

**Commands**: `/plan-red` (its Steps 7–9 are what pass 2 runs for a **Feature** node),
`/reproduce` (a **Bug fix** node's red step), `/plan-tdd-migration` (a **Migration** node),
`/code-restructuring` (a **Refactor** node's pass 2 and its `/green`), `/plan-test-rebalance` (a
**Test rebalance** node), `/add-to-pr-stack` (ad-hoc
draft PR on an **existing** stack tail), `/split-pr-to-stack` (carve an **existing** PR into stacked
slices; this command plans a stack from requirements), `/green`, `/green-attack`,
`/validate-changes`, `/pr-stack-rebase` (single mode in pass 2, cascade mode as the completion
gate), `/fix-pr-stack` (rebase, comments, local-gated fixes), `/merge-pr-stack` (land the finished
stack bottom-up), `/merge`, `/repoint`, `/pr-wrap`,
`/wrap-context-docs`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`)
**Skills**: `roadmap-driven-development` — a Roadmap page as the input (Step 1, 4b, Step 5 item 6), `pr-stack`, `deferred-work` (`.agents/skills/deferred-work/SKILL.md`) — the TODO and
code-issue records Step 2b reads, `code-restructuring` — a restructure node's `/green`
**References**: `.agents/skills/pr-lifecycle/SKILL.md` (the `[wf]` rows, presets,
halts and the summary), `.agents/skills/planning/references/planning-phase.md`,
`.agents/skills/pr-lifecycle/references/initial-discovery.md`,
`.agents/skills/pr-lifecycle/references/changeset.md` §2.5,
`.agents/skills/pr-lifecycle/references/restructure.md`
**GitHub docs**: <https://gh.io/stacks> · stacked pull requests + the `gh stack` extension
