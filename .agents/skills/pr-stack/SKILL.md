---
name: pr-stack
description: >-
  Principles for planning, tracking, and landing a STACK of dependent PRs — each PR based on the
  previous one's branch, not master. REQUIRES the `gh stack` extension: a stack must be registered
  as a real GitHub stack object, not merely a chain of base branches. Defines the stack model, the
  TWO independence properties (independently mergeable vs independently greenable — a stacked branch
  inherits its predecessors' stubs, not their behaviour), the REQUIRED per-changeset "Inherited
  Dependencies — do not implement here" declaration, NODE KINDS (every node's family —
  behaviour-adding / behaviour-changing / behaviour-preserving — decides its artifacts and the shape
  of its proof, and its kind decides its changeset's `## Workflow` preset: feature, bug fix, refactor,
  migration, infra, test rebalance, test style; the changeset is mandatory for every kind because a stacked PR is picked up
  context-free, and only the PRD varies) and the REQUIRED per-changeset "## Verification" method
  (the V1–V4 ladder: an executable test by default, a recorded baseline, a deterministic recorded
  command, a scripted manual procedure with consent — a code change with no way to tell whether it
  worked is not a reviewable PR), GREEN WAVES (wave 1 is every PR that can be
  started immediately; wave k is every PR whose unmet needs are all met by earlier waves) and the
  ordering rule they impose — the branch line is the waves concatenated, blockers leading each wave
  — NODE NUMBERS (n1..nN: the planning identity that exists before any PR does; PR numbers only for
  a dependency on the composition of an already-open PR), base tracking, per-changeset stack
  context (there is NO shared stack manifest — each changeset carries its own row, including its
  own green wave),
  forward-only doc linking, the golden rules for bottom-up landing (a deleted base branch CLOSES its
  dependent PR), the worktree rules (plan in the current worktree, switching branches one-by-one, in two passes —
  submit each PR with its planning docs as soon as its branch is planned, then revisit each bottom-up for its
  rebase + red commit; restore the original branch when done, including `master`, and cascade
  `/pr-stack-rebase` the whole stack as the completion gate; delete a temporary `/green`
  worktree as soon as that PR's loop finishes), per-worktree rebase (`/pr-stack-rebase` — one branch
  at a time, in a worktree that owns it; its cascade mode walks a named range bottom-up and is not
  `gh stack sync`), the in-stack obligations of every `## Workflow` row (`/green` and `/green-attack`
  always `/pr-stack-rebase` first then an ancestor-functionality gate, `/green` commits and pushes,
  `/validate-changes` and `/pr-wrap` always `/pr-stack-rebase` before any code diff and validate the
  implementation against the plan), milestone pushes
  (successors only get behaviour that has been pushed), the ⚠ needs-rebase trap, recurring union conflicts, approval re-trigger, and recovery. Load this whenever working a
  stack. The `/plan-pr-stack`, `/add-to-pr-stack`, `/split-pr-to-stack`, `/pr-stack-rebase`, `/fix-pr-stack`, `/merge-pr-stack`, `/green`,
  `/green-attack`, `/validate-changes`, `/pr-wrap`, `/merge`, `/repoint`, `/squash-pr`, and
  `/follow-up-branch` commands are the operational entrypoints; this skill is the shared model they
  all follow. Triggers: stacked PRs, PR stack, "PR based on another branch", add a PR to a stack,
  ad-hoc stacked PR, split a PR into a stack, A→B→C split B, green wave, node number, which PRs can
  be started first, node kind, bugfix / migration / refactor node in a stack, how is this PR
  verified, a PR with no tests, base branch deleted / PR auto-closed,
  retarget a PR base, follow-up branch off an open PR, gh stack.
allowed-tools:
  - Bash(git *)
  - Bash(gh *)
  - Read
  - Grep
  - Glob
  - Edit
  - Write
---

# pr-stack — the stacked-PR model

Canonical mechanics for planning, tracking, and landing a **stack** of dependent PRs. The commands
`/plan-pr-stack`, `/add-to-pr-stack`, `/split-pr-to-stack`, `/pr-stack-rebase`, `/fix-pr-stack`, `/merge-pr-stack`, `/green`,
`/green-attack`, `/validate-changes`, `/pr-wrap`, `/merge`, `/repoint`, `/squash-pr`, and
`/follow-up-branch` are the operational entrypoints; they all follow the definitions below, so follow
them exactly and keep the commands and this skill in agreement. What runs on a node, and in which
order, is that node's changeset `## Workflow` table (`.agents/skills/pr-lifecycle/SKILL.md`);
this skill says what each row's command owes the stack, never which command comes next.

## Required tooling — the `gh stack` extension

GitHub supports stacked PRs officially through the **`gh stack`** CLI extension
([docs](https://gh.io/stacks)). It is **required** for every stack workflow here, because it is what
turns a chain of branches into a stack GitHub actually knows about.

**Preflight — run this before any stack operation:**

```bash
gh extension list | grep -q 'github/gh-stack' && gh stack --version
```

If it is **absent, do not proceed and do not fall back to `gh pr create`.** Stop and ask the user to
install it:

```bash
gh extension install github/gh-stack
```

Ask rather than installing unprompted — installing a CLI extension changes the user's tooling, and
adding external dependencies is theirs to approve. Once they confirm, re-run the preflight and
continue.

### The commands that matter

| Command | What it does |
|---|---|
| `gh stack init [branches...]` | Create a stack. Existing branches are **adopted** bottom-to-top; missing ones are created. `--base` sets the trunk (default: the repo default branch). |
| `gh stack submit` | Push all branches, **create PRs** for branches without one, update bases for existing PRs, and create/update the **stack object on GitHub**. Interactive by default; `--auto` skips the editor. |
| `gh stack sync` | Fetch, fast-forward trunk, **cascade-rebase** each branch onto its parent, push atomically (`--force-with-lease --atomic`), sync PR state, and **link open PRs into a stack on GitHub** (≥2 PRs). Never opens PRs. |
| `gh stack view` | Show the stack and each PR's status. `--short`, `--json`. |
| `gh stack rebase [branch]` | Cascading rebase only. `--no-trunk` skips fetching/rebasing trunk — the escape hatch when trunk is pinned by another worktree. |
| `gh stack checkout <PR#\|URL\|branch>` | Check out a stack. Given a PR number it will **discover the stack from the GitHub API** and set it up locally — the way to resume after worktrees are deleted. |
| `gh stack switch` / `up` / `down` | Move between branches in the stack. |
| `gh stack modify` | Interactive restructure (drop / fold / insert / reorder / rename). **Cannot split a branch into two.** Run `gh stack submit` afterwards. Agents: do not drive this TUI; use `/split-pr-to-stack` to split, or `unstack` + `init` (with consent) to rebuild order. |
| `gh stack add <branch>` | Add a new branch on **top** of the stack. Wrong for inserting a layer under an existing successor. |
| `gh stack unstack` | **Destructive** — removes the stack locally *and on GitHub*. `--local` keeps the remote stack. Never run without explicit user consent. |

**`submit` vs `sync` — pick deliberately.** Both register the stack object. `submit` is the
create-PRs path and can change draft state: `--open` marks **new *and existing*** PRs ready for
review. `sync` documents that it "never opens pull requests — it only links PRs that already exist".
So:

- PRs do **not** exist yet → `gh stack submit` (`--auto` for non-interactive; new PRs are created as
  drafts unless `--open` is passed).
- PRs **already** exist and you only want them registered/restacked → `gh stack sync`. Safer: it
  cannot flip a draft to ready for review.

`submit` / `link` are **additive**: a new PR is appended on **top** of the existing GitHub stack.
That will not insert a layer between B and C. Splitting B in `A → B → C` needs `/split-pr-to-stack`
(recreate the stack object with an explicit bottom-to-top `init` list after consent to `unstack`).

### `gh stack view` status icons

```
✓  PR merged      ◎  PR queued      ○  PR open      ⚠  Needs rebase
```

`gh stack view` is the cheapest correctness check on a stack. Read it before and after every stack
operation, and treat any `⚠` as a defect to fix before landing anything.

## What a stack is

A stack is an ordered list of PRs `PR₁ → PR₂ → … → PRₙ` where each PR is branched on top of its
**predecessor**, not on `master`:

```
origin/master
   └── pr-1-<slug>      (base: origin/master)      ← PR₁
        └── pr-2-<slug> (base: pr-1-<slug>)         ← PR₂
             └── pr-3-<slug> (base: pr-2-<slug>)    ← PR₃
```

- **Predecessor** of PRₖ = PRₖ₋₁ (the branch it is based on). PR₁'s predecessor is `origin/master`.
- **Successor** of PRₖ = PRₖ₊₁ (the branch based on it).
- PRs **merge in order**: PR₁ first, then PR₂, and so on. Merging PRₖ is only allowed once PR₁…PRₖ₋₁
  are merged.
- The order must be a valid **topological sort of the real dependencies**: if PR₄ consumes something
  PR₂ delivers, PR₂ sits below it. Beyond that constraint the order is **underdetermined**, so it is
  a choice — and it must be *made*, per *Order inside a green wave* below: the green waves
  concatenated, blockers leading each wave.
- **A PR that depends on nothing still occupies a position.** It belongs to **wave 1** — nothing
  gates it — so it is in the lowest wave; but inside that wave it sorts to the **back**, behind the
  wave-1 PRs that other waves are waiting on.

### Node numbers — the identity that exists before any PR does

A **node** is a planned position in the stack, written **`n1 … nN`**. `n<k>` is the `k` in the branch
name `pr-k-<slug>` and the `K` in the title's `(#<slug> K/N)`. A node exists the moment the
decomposition is settled — *before* anything is on GitHub. A **PR number** (`#2401`) exists only
after `gh stack submit` has opened that PR.

**The green waves, `Concurrent with:`, `Blocks:` and the dependency edges are written in node
numbers.** The grouping is decided during planning, when no PR number exists. A record keyed on PR
numbers would have to be written with empty slots for somebody to back-fill later, and a wave line
nobody back-filled is worse than no wave line at all.

**A PR number is for one thing: pointing at the composition of a specific PR** — a dependency on
what that PR actually *contains*, as opposed to what a planned node is *for*. That happens when the
thing depended on is already open: a layer added to a live stack, a slice of a PR being split, a
dependency reaching outside this stack. Write both there — **`n3 (#2403)`** — the node number for
the position, the PR number for the composition you are pointing at.

Node numbers **move when the stack is renumbered** (`/add-to-pr-stack`, `/split-pr-to-stack`), and
that is their one cost: the rows that need new `K/N` titles need their wave rows re-checked in the
same pass. PR numbers never move — but they cannot be written down at the moment the decision is
made, which is the moment that matters here.

### Order inside a green wave — blockers to the front

> **"Wave" means a group of PRs — nothing else in `/plan-pr-stack`.** Its two sweeps over the stack
> are **Pass 1** (plan and open every PR) and **Pass 2** (red every PR), renamed precisely so that
> `Wave 1` can only ever mean *the PRs that can be started immediately*. `/fix-pr-stack` and
> `/merge-pr-stack` still call their own landing sweeps waves; those are passes over an existing
> stack, never a grouping, and green waves barely arise there. Where either reading is possible,
> this skill spells the grouping **green wave**.

Topological order fixes only part of the line. For most positions several PRs are eligible, and
leaving that to the order the PRs happened to be named in during the interview is the default
mistake — it costs the stack throughput for nothing. Resolve it in three steps:

1. **Group into green waves.** Wave 1 is every PR that needs no predecessor *behaviour* — the ones
   an implementer could start this minute. Wave *k* is every PR whose unmet needs are all met by the
   waves below it. This grouping is **wider than the branch line**: several PRs share a wave, and a
   PR sitting sixth in the line can still be wave 1.
2. **Concatenate the waves** — all of wave 1, then all of wave 2, and so on. That much is forced by
   the real dependency edges.
3. **Sort inside each wave by what waits on the PR**: most transitive dependents first, PRs nothing
   depends on last. Break a remaining tie with the reading order you would have chosen anyway —
   usually the most foundational PR first.

Step 3 is free. Every PR's predecessors sit in a **strictly earlier** wave, so *any* permutation
inside a wave is still a valid topological sort — which is exactly why nothing forces the order and
why it has to be chosen.

```
edges    n1 → n2, n3, n4, n5      n2 → n4      n5 → n6, n7, n8

waves    1: n1     2: n2, n3, n5     3: n4, n6, n7, n8
                      (n4 waits on n2; n6–n8 wait on n5)

                        · marks a wave boundary; bottom of the stack is on the left

✓ line   n1 · n5, n2, n3 · n4, n6, n7, n8
         wave 2 led by its blockers — n5 (three dependents), then n2 (one), then n3 (none)

✗ line   n1 · n3, n2, n5 · n4, n6, n7, n8
         n3 blocks nothing, yet six PRs now land behind it
```

Three reasons, all consequences of the stack landing bottom-up:

- **A blocker's position is how long everything above it waits.** n5 at the foot of its wave holds
  n6–n8 behind two unrelated merges; at the head of it, it clears first and its subtree follows.
- **A dependent's ancestor set stays honest.** Every PR below a dependent is in its history, so a
  leaf sorted low puts its commits in the history of PRs that consume nothing from it.
- **The PR that can merge first should be the one most work is queued behind** — not the one that
  happens to be smallest or was described first in the interview.

The `K/N` group in the PR titles *is* this order, and each changeset's `**Wave:** k of m` is the
same decision seen from the other side. Settling both at planning time is what avoids renumbering
the whole stack later.

### A stack is a GitHub object, not just a chain of bases

Setting each PR's base to its predecessor gets you one thing — GitHub computes each PR's diff against
its base, so **reviewers see only that PR's own delta**. That alone is most of the review benefit,
and it is why stacking beats one giant branch.

But base branches alone are *not* a stack as far as GitHub is concerned. There is no grouping, no
ordering, and no stack-aware handling of merges. **A stack is only registered once `gh stack submit`
or `gh stack sync` has created the stack object** — the confirmation reads:

```
✓ Stack created on GitHub with N PRs
```

**A stack is not considered planned or delivered until that line has appeared.** PRs opened with a
bare `gh pr create` are an unregistered chain and must be adopted (`gh stack init` → `gh stack sync`)
before the stack is complete.

What GitHub still does **not** do for you, registered or not:

- Enforce merge order — nothing stops merging PR₃ before PR₁.
- Make a successor's CI meaningful for `master`. Checks build the head merged into **its own base**,
  so green CI on PRₖ says nothing about `master` until PRₖ is retargeted onto it.

### Epic issues — the DAG's home

Each planned stack gets one **epic GitHub issue** — the stack's whole-scope
prose plus the **DAG block**: a fenced ```yaml block carrying the sentinel
`schema: overstack-dag/1` and the stack's nodes, line edges, dependency
edges, waves, and positions — all in node numbers. Three writers, one
discipline:

- **The planning flow creates it** — `/plan-pr-stack` opens the epic at the
  pass-1 checkpoint (every PR submitted), via the `surmap`
  binary's `issue create` command, and stamps the epic's URL into every PR
  body's `## Stack` block.
- **overstack keeps it current** — `overstack issue sync` at wave boundaries
  during `/fix-pr-stack` and `/merge-pr-stack`, so the block reflects reality
  during landing.
- **The overstack frontends read it** — the graph view, detail panel, CLI,
  and MCP discover a stack's DAG from the epic (plus `gh stack`/PR bases for
  topology).

Rules:

- **GitHub stays the source of truth** — the stack object + PR bases for
  topology, the epic for the DAG/waves; overstack's model is a projection,
  never a second registry that can drift.
- **The DAG block is machine-managed** — updates replace only the fenced
  block and preserve the surrounding human prose byte-for-byte.
- **The epic is born current** — emitted from the settled plan (waves, line,
  edges), not reconstructed after the fact.

#### The epic must be correct, and every command that changes the stack revises it

An epic with only `kind: line` edges **renders as a linear chain with no waves**: overstack derives
waves from `kind: dependency` edges alone (`assign_waves` — a node with no incoming dependency edge
is wave 1), and the line edges only record the branch bases. Wave and dependency text in the epic
prose or in PR bodies is not read by overstack. So "the epic is correct" is a checkable property:

- **Every dependency edge in the plan is a `kind: dependency` edge in the block**, one per
  `n_a → n_b` that the plan says gates a wave. A stub-level dependency (compile only) is **not**
  written as a dependency edge: `assign_waves` ignores `level` and would push the node a wave up. A stack with more than one wave and **zero** dependency edges is wrong.
- **Deriving the waves from the block reproduces the plan**: the same wave count, the same members,
  the same line, matching every PR body's `Wave k of m`.
- **Nodes carry the PR's current number, title and kind**; line edges match the PR bases.

**Known tooling gap:** `overstack issue create` and `issue sync` build the graph from the open PRs
(line edges only) and `sync` merely carries over dependency edges already in the block. Neither can
*originate* a dependency edge. Until the CLI accepts them, add them by editing **only the fenced
block** of the epic body (prose untouched), then run `issue sync <slug>` (`uv run pytest -q
surmap run-cli issue sync <slug>` — no `--` before `issue`: the script is `cargo run --` already, and a second `--` makes clap reject the subcommand) so the serializer
normalises the block, then check the three properties above — `run-cli view <slug>` prints the waves overstack derives. State in the report that this was done
by hand and why.

**Commands that change the stack must revise the epic in the same run, and verify it before they
report done** — not leave it to the next wave-boundary sync:

| Command | What changes in the epic |
|---|---|
| `/plan-pr-stack` | Created at the pass-1 checkpoint; **revised at the completion gate** — pass 2 can move PRs between waves, retitle, or add ground-softening nodes |
| `/add-to-pr-stack` | A new node, its line edge from the tail, its dependency edges, every title's `N` |
| `/split-pr-to-stack` | A new node B2, B1/B2's line edges, dependency edges of B moved to the right slice, every title's `N` |
| `/repoint`, `/squash-pr` (successor repoint) | Line edges (new base) |
| `/fix-pr-stack`, `/merge-pr-stack` | Merged nodes dropped / marked, at each wave boundary (`issue sync`) |

`/pr-stack-rebase` and `/follow-up-branch` change no topology and leave the epic alone.

### Adding a layer — `/add-to-pr-stack`

`/add-to-pr-stack` appends a new **draft PR** on the **tail** of a registered stack (or a user-named
parent, only if that parent *is* the tail) so new work can start without waiting for predecessors to
merge. It is `gh stack top` → `gh stack add` → commit → `gh stack submit --auto`. `gh stack add`
refuses to run unless HEAD is already the top and **cannot insert** under a successor.

`/follow-up-branch` is the branch-only counterpart: it creates and switches to a branch, never opens
a PR, and never silently defaults the base to current/`master`. A named parent that is **not** the
tail would fork the stack (two open PRs with the same base). Stop; inserting in the middle is
`/split-pr-to-stack`.

### Splitting a layer — `/split-pr-to-stack`

`/plan-pr-stack` plans a stack from requirements. `/add-to-pr-stack` (draft PR) and
`/follow-up-branch` (branch only) add a layer **on top**. `/split-branch` produces sibling branches,
typically both off `master`. None of those carve an **existing** PR into stacked slices.

**Splitting B in `A → B → C` produces `A → B1 → B2 → C`:**

- **B1** is B's existing PR when B already has one (same number, same head branch, same predecessor
  A). Its diff shrinks to the bottom slice. Do not close B and open two new PRs.
- **B2** is a new PR whose base is B1. After the git split, **B2's tree equals original B**, so C
  rebases onto it without picking up a second copy of B1.
- **C**, the unique stack successor of B, is retargeted onto **B2**. Further descendants (D, …)
  keep their parent and are rebased onto that parent's new tip. Two open PRs that both base on B
  are **siblings** — stop; a stack is linear.

Each invocation produces **exactly two layers** (B1, B2). A third slice is another
`/split-pr-to-stack` on B1 or B2.

If B has **no PR yet**, open a 2-PR stack: B1 based on the resolved predecessor A (never silently
`master`), B2 based on B1, then `gh stack submit`.

`gh stack modify` **cannot split a branch** (insert creates an empty layer). `gh stack add` only
appends on top — with C already above B that yields `A → B → C → B2`. Recreate the stack object:
consent to `gh stack unstack`, then `gh stack init` with the explicit bottom-to-top list including
B2, then `submit` / `sync`. Free trunk, A, B1, B2, and the whole successor chain **before**
unstacking — `init`/`sync` cannot move a pinned branch, and discovering that after unstack leaves
the GitHub stack object gone. Fetch remote-only heads before `checkout`. The procedure lives in
`/split-pr-to-stack`.

### Two independence properties — do not conflate them

A stack has **two** different independence properties, and they fail in opposite directions. Most
stack bugs come from claiming one and meaning the other.

**1. Independently mergeable (backwards / successors).** PR₁ can merge to `master` with green CI
regardless of whether PR₂…PRₙ are green — and **must not break production or local dev** when it is
the only stack slice that lands. Achieve this by:

- **Self-contained tests.** A PR's tests exercise only the API that PR owns. They never assert
  behaviour implemented by a **successor**.
- **Stub APIs for forward dependencies.** If PRₖ needs to reference something a successor will
  implement, the successor exposes that symbol as a **compile-only stub** (correct signature/types,
  body throws `NotImplementedError` / returns a typed placeholder, marked `TODO`). The stub is
  **owned by the PR that will implement it**, and lives in that PR's branch first so successors
  inherit a compilable symbol.
- **Trunk-merge safety for runtime, not just compile.** Register servicers and routes the product
  already calls; prefer safe empty or stubbed behaviour over missing endpoints. Incomplete wiring in a
  later node is fine only when this PR still leaves production and local dev **workflows** working
  (`uv run pytest -q`, package dev scripts, deploy smoke paths). **Local dev data** may be invalidated
  (reset DB, re-migrate) without a separate planning ask. **Production data** changes require
  explicit developer consent during `/plan-pr-stack` Step 1 and a record in the changeset — never
  assumed OK.

**2. Independently greenable (forwards / predecessors).** PRₖ's `/green` can complete *while* PR₁…PRₖ₋₁
are still red. This is what makes concurrent `/green` real, and it is the property that is easy to
lose without noticing.

A stacked branch **inherits its predecessors' code — including their stubs.** So during concurrent
`/green`, PRₖ sees PR₁'s *signatures*, not PR₁'s *behaviour*. A test on PRₖ that drives a predecessor's
still-stubbed surface cannot pass until that predecessor's `/green` lands, no matter how correct PRₖ is.

For each inherited symbol PRₖ needs, choose **one** and write it down:

| Choice | When | Consequence |
|---|---|---|
| **Code against the stub's signature; don't implement it** | Always, for production code | PRₖ compiles and builds; the behaviour arrives with the predecessor |
| **Inject a test double at the seam** | The test is about PRₖ's own logic and the predecessor is incidental | PRₖ stays independently greenable |
| **Use the real predecessor object and declare the sequencing** | The test's value *is* the real integration | PRₖ is **not** greenable until that predecessor is green — must be recorded as green order |

**Never implement a symbol another PR owns**, even when its stub is in front of you and the fix looks
like one line. Two PRs implementing the same symbol is a guaranteed conflict, and the owning PR's
tests are the ones specifying it.

### Declaring inherited dependencies — REQUIRED in every changeset

Every changeset except the bottom one carries this section, so whoever runs `/green` learns the
boundary from the document they are already reading rather than from anywhere else:

```markdown
## Inherited Dependencies — do not implement here

Symbols this PR builds on that a **predecessor owns**. They arrive as stubs; implementing them here
would collide with the PR that owns them.

| Symbol / module | Owned by | State during this PR's green | What this PR does |
|---|---|---|---|
| `DatasetOperations.queue_download` | PR 1 | stub, `TODO(pr-1)` | calls it; does not implement it |
| `ServerConfig` provider parsing | PR 3 | stub, `TODO(pr-3)` | tests construct `ServerConfig(...)` directly instead of going through `from_env` |

**Greenable independently?** yes | no — needs PR N green first (why).
```

A `no` is a legitimate answer, not a defect — but it must be **explicit**, and it must appear in that
PR's own `## Stack Context` so nobody schedules the work in an order that cannot finish.

## Node kinds — the family decides the shape, the kind picks the workflow

Not every node in a stack adds behaviour. A stack that softens a seam, migrates a call site, fixes a
bug and then builds a feature on top has four nodes from **three different families** — and planning
all four as features gives three of them a PRD nobody needs and acceptance tests that accept nothing
new. The kind is settled per node **at planning time**, before any branch is cut, because it decides
which artifacts that node's pass 1 writes and what its pass-2 commit contains.

**The changeset is never what varies.** Every node of every kind carries its own changeset, because
a stacked PR is picked up by whoever — or whatever — has none of this conversation's context: the
changeset is the only place the background, State A, State B, the boundary, the inherited
dependencies and the verification method are written down. What the kind changes is whether a **PRD**
is warranted (a product-requirements document for a behaviour-preserving move is fiction), which
changeset **template** the node fills, and what its pass-2 commit contains. A node with no changeset
is not a node — it is a diff somebody will have to reverse-engineer.

**Layer 1 — the family.** One question about the node's diff: *what does it do to observable
behaviour?*

| Family | The diff | Kinds in it |
|---|---|---|
| **behaviour-adding** | behaviour that does not exist yet | Feature |
| **behaviour-changing** | behaviour that exists and is wrong, or exists and must become something else | Bug fix · **contract change** (behaviour-changing migration, deprecation, removal) |
| **behaviour-preserving** | nothing observable changes; only the code that produces it moves | Refactor / restructure · mechanical migration · infra & toolchain · test rebalance · test-style migration |

The **family** decides the artifacts and the verification shape. The **kind** decides which
procedure plans it and which `## Workflow` preset its changeset gets
(`.agents/skills/pr-lifecycle/SKILL.md` § *Presets*). `/plan-pr-stack` does not
re-specify those procedures — it uses the one that owns each kind, states what that node's commit
must contain, and copies the preset; the preset's rows after the guardrail say what implements the
node.

| Kind | Family | PRD | Changeset template | Pass-2 commit — the node's "red" step | Planned by | `## Workflow` preset |
|---|---|---|---|---|---|---|
| **Feature** | adding | required | `pr-lifecycle/references/changeset.md` | owned stubs + failing acceptance tests + failing unit/it tests | `/plan-red` (Steps 7–9) | feature |
| **Bug fix** | changing | only when user-visible | `pr-lifecycle/references/changeset.md`, `Type: Bug Fix` | the **reproduction test** — red *for the bug*, not for a missing symbol — plus any stub it needs | `/reproduce` | bugfix |
| **Contract change** (behaviour-changing migration, deprecation, removal) | changing | only when user-visible | `pr-lifecycle/references/changeset.md`, `Type: Migration` · `Behaviour: changes` | tests asserting the **new** contract, plus preservation tests for the parts that must survive. **No reproduction** — an intentional change has no defect to reproduce | `/plan-red`'s behaviour-changing path for the new contract, borrowing `/plan-tdd-migration`'s preservation-test technique for what survives | feature (contract change) |
| **Refactor / restructure** | preserving | none | `pr-lifecycle/references/restructure.md` | the `plan.jsonl` + the recorded baseline; **no** acceptance tests | `/code-restructuring` (Steps 1–6) | restructure |
| **Mechanical migration** | preserving | none | `pr-lifecycle/references/changeset.md`, `Type: Migration` · `Behaviour: preserves` | the recorded baseline + behaviour-preservation tests wherever the baseline does not already cover what moves | `/plan-tdd-migration` | migration |
| **Infra / toolchain** | preserving | none | `pr-lifecycle/references/changeset.md`, `Type: Infra` | the verification command and its recorded before-state | `/plan-ft-dev` (changeset, no PRD) over the planning phase's Steps 1–3 | infra |
| **Test rebalance** | preserving | none | `pr-lifecycle/references/changeset.md`, `Type: Test Rebalance` | the lower-tier tests that must exist **first** (V1-characterisation), plus the **V3** equivalence measurement — `cov-acc unique --tier e2e`, before and after | `/plan-test-rebalance` | rebalance |
| **Test-style migration** — suites rewritten to fluent; test files only | preserving | none | `pr-lifecycle/references/changeset.md`, `Type: Test Style` | the **V2** before-state per suite — test titles, count, coverage of what they exercise, fluent score with per-test rows (`testing/references/fluent-style.md` § *Migrating a suite*) | `/plan-ft-dev` (changeset, no PRD) | test-style |

**Classify by the family question, never by the label.** The boundary cases are where stacks go
wrong:

- **A refactor that also fixes a bug is two nodes.** The moment a behaviour-preserving diff changes
  an output, its baseline stops being a guardrail — it becomes the thing that has to be edited, and
  nothing is left proving the move was safe.
- **A migration is behaviour-preserving only where it is proven to be.** If the target API's
  semantics differ anywhere — error type, ordering, null handling, timezone — that part is
  behaviour-changing and needs a test asserting the new contract, whatever the rest of the node is.
- **A dependency or toolchain upgrade is preserving until it is not.** Verify it against the
  behaviour the repo actually depends on, not against the changelog.
- **Performance work preserves the contract and changes the measurement.** Its verification is the
  measurement (rung V3), with the before-state recorded; a test that only asserts correctness proves
  nothing about why the node exists.
- **A node whose kind you cannot settle is a node whose boundary is wrong.** Two families in one diff
  is the signal to split it, and splitting is free at planning time.

A **deprecation or removal** is a contract change like any other, and its red step has the same
shape: a test asserting the new contract (the symbol is gone, the callers moved, the deprecation
warning fires) plus preservation tests for the behaviour that stays. It is not a refactor —
something observable changed for a caller.

The kind is the header's **`(Type, Behaviour)` pair** (`pr-lifecycle/references/changeset.md` §1), never `Type` alone:
`Type: Migration` is a contract change when `Behaviour: changes` and a mechanical migration when it
`preserves`, and those two get opposite red steps. A stack node mirrors the resolved kind and its
preset into `## Stack Context → Kind` / `Workflow` — the lines the pass-2 router reads — and into
the PR description's `## Stack` block, which is a GitHub view rather than a committed file. What
implements the node is its `[wf]` rows. The kind also drives the conventional-commit `<type>` in the PR title
(`feat` · `fix` · `refactor` · `chore` · `test` — see **PR titles**).

### The matrix is a default, not a gate

The kinds matrix is what applies **when nobody said otherwise**. The developer is in charge of the
code, so a workflow they name for a node wins — and a node the taxonomy does not cover (a spike, a
revert, a docs-only node, a proto definition, a dependency bump, a generated-code refresh) resolves
by the family question, or by a workflow the planner **proposes** and they approve.

What the planner owes them before they choose is the **mechanical consequence** — which artifact
goes missing, which gate disappears, what a later command will not find — plus a recommendation with
the recommended option first, the shape `/skip-tests` uses. Then their decision stands, and it is
recorded in that node's `## Decisions & Trade-offs` so the absent artifact reads as a choice rather
than an omission (and so `/validate-changes` does not report it as a defect). Overrides are **per
node**: one on n3 says nothing about n4.

**A recorded override is not enough on its own — it has to reach the dispatch.** Write it into that
node's `## Stack Context → Workflow override` (the line the pass-2 router reads) **and** into its
`[wf]` rows (what every later row's runner reads). An override living only in
`## Decisions & Trade-offs` leaves the node getting its kind's default red step and its preset's
default implementer — precisely the workflow the developer declined.

The exception is the section below. A workflow swap changes **how** a node is proven, never
**whether** — a node with no proof at all does not get a branch, which is this repo's rule rather
than the planner's preference.

### Verification — required in every node, whatever its kind

A code change with no way to tell whether it worked is not a reviewable PR. Every node's changeset
carries a **`## Verification`** section (`pr-lifecycle/references/changeset.md` §9.5) naming the method, and the method
is the highest rung of this ladder the node can actually reach:

| Rung | Method | Typical kind |
|---|---|---|
| **V1** | **An executable test** — either **fail→pass** (an acceptance test, a reproduction, a new-contract test) or **characterisation**: green before and after, its value being that it *would have failed* had behaviour changed (a preservation test, a baseline-gap test, a rebalance replacement). Name which shape | every kind, by default |
| **V2** | **A recorded baseline that must still hold** — the existing suites, named and counted before the change and re-run after, *where they demonstrably cover the code that moves* | refactor · mechanical migration |
| **V3** | **A deterministic command whose before- and after-output are recorded in the changeset** — a build, a type-check, a generated-artifact diff, an analyzer or coverage count, a benchmark. A reviewer must be able to re-run it | infra · toolchain · performance |
| **V4** | **A scripted manual procedure with recorded evidence** — numbered steps anyone can repeat, plus what was observed (log line, request id, dashboard panel, screenshot). For behaviour no harness in this repo can reach | rare, and it needs consent |
| **V5** | nothing | **never acceptable** |

**Tests are the default, not the fallback.** Pick the highest rung the node can reach, and where a
lower rung is chosen, name in the changeset **what blocks the higher one**. "This code had no tests"
is not a blocker — it is the reason to write one, and for a behaviour-preserving node it is the
rhombus rule in the `testing` guide: coverage goes down a tier *before* the code above it moves.

**V2 is a claim about coverage, so prove it.** A baseline only guards the change if it executes the
code that moves; name the suites and what they cover. An untested file's green baseline is not a
guardrail, it is a coincidence — so a V2 node that finds a gap writes the missing test (V1) for that
gap first, in its own pass-2 commit.

**V4 needs the developer's recorded consent** — `**Approved:** <who>, <date>` in the section — because
choosing an unautomated guardrail is a judgment call about what this repo is willing to carry, and
that is the developer's to make, not the planner's. Present what blocks V1–V3 and ask.

**V5 stops planning.** A node whose changeset has no `## Verification`, or whose method is "the
reviewer reads it", is not planned yet — do not cut its branch. Reviewing a diff is how a method is
checked; it is not a method.

The section is **executed, not just declared**: the node's Wrap row carries a
`Verification executed — result recorded` TODO, and the recorded result is what `/pr-wrap` reads
before the PR leaves draft. A `## Verification` nobody ran is the same as V5.

### A restructure node — and declaring the rewrite it inflicts

The behaviour-preserving family has one member with stack-specific consequences, so it gets its own
rules. Occasionally planning's Step 2b (see the
[`deferred-work`](../deferred-work/SKILL.md) skill) finds a code issue that sits in the **seam every
node builds on**, or in a file more than one node has to edit. Absorbing that into a feature node is
forbidden by the boundary contract — it buries a reviewable change under a mechanical one — so it
becomes **its own node in this stack**, placed immediately before the first node that needs it
(PR₁ when it is the ground the whole stack builds on). `/plan-pr-stack` never opens a PR outside
the stack: a ground-softening or code-improvement change the user approved is `gh stack init` /
`gh stack add` like any other layer, not a sibling PR off the trunk. Landing it first is merge
order, not a second stack.

Its artifacts are the **Refactor / restructure** row of the kinds matrix above — no PRD, the
restructure changeset template, a pass-2 commit that is the `plan.jsonl` plus the recorded baseline
rather than stubs and failing tests, and `/code-restructuring` as its `/green` — which **deletes the
plan in the commit that applies it**, so successors inherit the applied tree, not a spent plan
(`code-restructuring` step 8). Its verification is
normally **V2**: the recorded baseline must still hold, `restructure apply` having changed no
behaviour. Where the baseline does not cover what moves, the missing test is written **first** (V1) —
that gap is the commonest reason a restructure lands broken.

What is specific to a stack is not the artifacts but the **blast radius**, and that is the rest of
this section.

**The rule that makes this work: a restructure node never blocks the planning of the nodes above
it.** They are planned, stubbed and red-tested against the structure **as it is today** — the
pre-restructure structure. Planning cannot wait for an execution that happens in `/green`, and
planning against a layout nobody has produced yet is guesswork.

The price is accepted up front rather than discovered: **when the restructure node greens, the nodes
above it break.** Stubs move, imports move, red tests fail differently. That is expected, and
repairing them is later-stage work — not a planning defect and not a reason to reorder the stack.

What keeps it orderly is the declaration. **Every node above a restructure node carries this
section**, next to its `## Inherited Dependencies`:

```markdown
## Inherited Restructure — expect rewrite

PR 2 (`pr-2-fill-flow-split`) restructures code this PR's surface and tests sit inside. This PR is
planned against the **pre-restructure** structure on purpose — planning could not wait for an apply
that happens in that PR's `/green`.

| What moves | From → To | Owned by | Effect here |
|---|---|---|---|
| `fillSessionFlow` | `fill-session-flow-service.ts` → `flow/fill-orchestrator.ts` | PR 2 | this PR's stubs and 6 red tests import the old path |
| `AnalyzerFallback` | deleted; callers move to `analyzer-port.ts` | PR 2 | 2 red tests construct it directly |

**Repair**: after PR 2's `/green` lands, run `/pr-stack-rebase` here, then fix the fallout in **a new
commit on this branch** — never an amend of the planning or red commit, and never an edit to PR 2
from here. Each red test must still fail **for this PR's own missing implementation** afterwards; one
that went green was satisfied by the restructure, which means it was never testing this PR — raise it.
```

Without that section the implementer reads the breakage as somebody's mistake and "fixes" it by
editing the restructure node, which is exactly the two-PRs-one-symbol collision the whole ownership
model exists to prevent.

## In-stack obligations — what every `## Workflow` row owes the stack

Implementing a PR **inside a stack** is not the same as implementing a standalone branch, because
other people (and other worktrees) are building on top of what you push. The order of the rows is
the node's `[wf]` lines; extra obligations apply to every row's command on a stack branch:

0. **Rebase, then check ancestors, before writing code.** `/green` and `/green-attack` **always**
   run `/pr-stack-rebase` (this branch only) first, so this PR is fully in sync with the latest
   pushed predecessor. Then they **MUST** check that functionality this PR depends on from ancestor
   PRs is actually implemented (see the changeset's `Inherited Dependencies` table and
   **Greenable independently?**). If a required ancestor is still a stub, **halt the Green row ⛔**
   with the stub and the options (wait for the ancestor, a double at the seam, re-plan) —
   the `pr-lifecycle` skill § *Halts*. Do not implement the predecessor-owned symbol, and do not green against a lie.
   Independently greenable PRs (signature-only use, or a test double at the seam) pass this gate
   while the ancestor is still a stub. Follow `.agents/commands/green.md` step 0 (same gate in
   `/green-attack`).
1. **Push at the end of `/green`.** A stack branch's successors are cut from it, and reviewers read it
   as part of a registered stack. Work that only exists in one worktree is invisible to both. So when
   the green phase of a **stacked** PR finishes, `/green` commits and pushes that branch — it does not
   stop at "tests pass locally". (For a standalone branch `/green` still leaves committing to the
   user; this obligation is stack-specific.)
2. **Validate implementation against the plan before wrapping.** Each stacked PR was planned with its
   own changeset + owned API surface + `Inherited Dependencies` declaration, plus a PRD where its
   kind warranted one. `/validate-changes`
   is the checkpoint that the branch matches *that* plan — and, just as important, that it has not
   quietly grown into a **predecessor's or successor's** territory.
3. **Rebase before any code diff.** `/validate-changes` and `/pr-wrap` **always** run
   `/pr-stack-rebase` (this branch only) before they execute a code diff. A ⚠-free `gh stack view` is
   not a skip: leaked ancestor commits can still sit in `HEAD` relative to a stale merge-base, and
   treating that as this PR's work — or deleting the "extra" files to shrink the diff — is how
   predecessor code gets destroyed. If the branch already contains the latest base tip and
   `origin/<base>..HEAD` is this PR's commits only, the rebase is verify-and-publish (no rewrite; the branch is pushed if the remote lacks this
   state — the rebased state is on the remote before the command's own work starts).
   **No `git diff` until that leak check passes.** Unplanned deletions of predecessor-owned files or
   inherited stubs are defects, same as implementing an inherited symbol.

What each row's command does first on a stack branch:

```
/green            → ALWAYS /pr-stack-rebase first; ancestor-functionality gate (⛔ halt
                    if a required ancestor is still a stub); then implement, commit, push
/validate-changes → (inside /pr-wrap) ALWAYS /pr-stack-rebase first; then implementation vs
                    plan; commit + push the updated status. Gaps against the plan halt the
                    Wrap row ⛔, naming the Green row in its Result
/pr-wrap          → ALWAYS /pr-stack-rebase first (again); then validate/refactor cycle,
                    docs, mark PR ready
```

`/validate-changes` in a stack checks, beyond its normal analysis:

- **Every changeset item, and every PRD acceptance criterion where the node has a PRD**, is
  implemented or explicitly deferred with a reason. A node whose kind warrants no PRD is checked
  against its changeset and its `## Verification` instead — an absent PRD is not a gap when
  `## Stack Context → Workflow` says the kind has none.
- **This node's `## Verification` has been executed and its result recorded.** For a
  behaviour-preserving node this is the check that matters most: there are no new acceptance criteria
  to tick, so the recorded baseline is the whole of the evidence.
- **The owned API surface is fully implemented** — no `TODO(pr-<this-k>)` stub bodies left behind.
  Stubs the *planning* phase created for this PR are exactly the work `/green` was supposed to
  finish. A node that owns no new surface (a Refactor, a test rebalance) has no stubs to check; its
  equivalent is that the `plan.jsonl` applied in full, the baseline is green again, and the spent
  plan is deleted (`git ls-files '*/restructure/*/plan.jsonl'` prints nothing).
- **No inherited symbol was implemented here.** Cross-check the changeset's
  `Inherited Dependencies — do not implement here` table: each listed symbol must still be a
  predecessor-owned stub in this branch's diff. Implementing one is a defect, not a bonus — it
  guarantees a conflict with the PR that owns it.
- **No successor behaviour crept in**, and no test asserts something a successor will implement.
- **The diff contains only this PR's files** (`gh pr view <N> --json changedFiles`), against the right
  base, **after** `/pr-stack-rebase` has made `origin/<base>..HEAD` this PR's commits only. Do not
  execute that diff until the rebase/leak gate passes.
- **No unplanned deletions.** Predecessor-owned files and inherited stubs still exist at `HEAD`.
  Extra files in the diff are leaked ancestor work — rebase, never `git rm` them to "clean" the PR.

Because the branch is pushed, the state a reviewer or a successor sees is always the state
`/validate-changes` reported on — that is why it commits and pushes before its row closes.

### Push at every milestone — successors are waiting on your commits

The end of `/green` is the **latest** a stack branch may be pushed, not the cadence. A successor
inherits its predecessors' branch, so **behaviour that is not pushed does not exist for the PRs above
you**. Hold a day's work locally and every successor keeps building against a stub it could already
have been building against for real.

**A milestone is production code that already passes its tests** — a finished slice of this PR's
owned surface, not a checkpoint of work in progress. That is the whole point: a successor inherits
whatever you push, so what you hand them must be behaviour they can build on and trust, verified by
the tests that specify it.

**Commit and push each such milestone as it lands**, rather than batching:

| Milestone | Why a successor cares |
|---|---|
| An owned symbol goes stub → real, **its tests green** | a successor blocked on it in the green order can start against real behaviour |
| A **signature** of an owned symbol changes | successors compile against it — a late signature change breaks them long after the decision, in someone else's worktree |
| A test group goes green | the behaviour it pins is now safe to depend on |
| A Post-Green TODO / wiring task completes and is verified | integration points become real |
| A fix that clears a declared `Greenable independently? no — needs PR N` | that PR's implementer can be told to go |

A signature change is the urgent one. Push it on its own, immediately, ahead of the implementation
behind it — the compile-level contract is what the whole stack is built on.

**Two preconditions, both hard:**

1. **The slice's own tests pass.** Run them; do not push production code you have not seen go green.
   Other tests in this PR may still be red — the ones covering parts you have not implemented yet —
   but never the ones covering what you just pushed.
2. **The branch builds.** The affected package's `type-check` / `build` before every push. Successors inherit
   the tree; a broken compile stops every worktree above you.

**Never push half-finished implementation to "share progress."** Scaffolding, commented-out branches,
a function that works for one case, code whose tests you have not run — all of it is worse for a
successor than the stub it replaces. A stub is honestly unimplemented and the green order accounts for
it; half-working behaviour silently misleads every PR above you and shows up as *their* bug. If a
slice is not finished and green, leave the stub in place and push when it is.

**Tell the people above you.** When a milestone unblocks a successor whose changeset says it is
blocked, say so in the push report — that PR's own `## Stack Context` is theirs to update, not yours
to edit from here. That worktree then runs
`/pr-stack-rebase` to pick the behaviour up; without the message it waits on a stub that is no longer
a stub.

**Yes, this creates `⚠` rows.** Every commit you push leaves your successors on a stale parent. That
is the intended trade: frequent small rebases in each worktree (`/pr-stack-rebase`, bottom-up) beat
one enormous one at the end, and it is exactly what the per-worktree rebase path exists to make cheap.

**During planning, submit each layer immediately — without rewriting pinned predecessors.**
`/plan-pr-stack` runs in the **current worktree**, in **two passes**. Pass 1: `gh stack init --base
<trunk>` / `gh stack add` to cut the next branch, commit that PR's changeset + discovery — plus a
PRD where its kind warrants one (docs only, commit 1), `git push origin HEAD` of that layer, then
`gh stack submit --auto`. `submit` is
stack-wide and can fail if a predecessor is pinned in a `/green` worktree. On failure, stop and ask;
do not `sync` / `rebase` / `--force`. Pass 2, once every PR is on GitHub: revisit PR₁ → PRₙ **in
stack order**, and for each run single-mode `/pr-stack-rebase` (so it picks up the predecessor's
just-committed stubs), then **the red step that node's kind calls for** — the `/plan-red` step (stub
API it owns, failing tests) for a Feature node, a reproduction for a bug fix, a `plan.jsonl` plus a
recorded baseline for a Refactor, the recorded proof for a migration or infra node (see *Node
kinds*) — as **commit 2**, and push. Pass 2 is the one sanctioned case of **the planner committing to a
predecessor after `gh stack add`**: every commit 2 makes the layers above `⚠`, the loop clears each
when it reaches it, and a **cascade `/pr-stack-rebase from #1 to #n`** after the original branch is
restored is the completion gate — expected to report every layer already current. Outside pass 2 the
planner must not commit to a predecessor, and it **must never edit a predecessor's changeset from a
successor branch** (own-files / wrap modify-delete). Start `/green` only after that cascade has run:
pass 2 needs to check every stack branch out in the planning worktree, and a pinned branch blocks
it. Commits to a predecessor from its own `/green` worktree are normal once the gate has passed;
they make successors `⚠` until those worktrees run `/pr-stack-rebase`.

## PR titles — the delivered state, the stack slug, and the position

A PR's title is not a label on a work-in-progress branch. On squash merge it **becomes the commit
message on `master`**, permanently, and that is the only form most people will ever read. Two
consequences follow, and both have already bitten this repo:

```
4c428f7bc feat(surmap-server): proto-derived tool schemas — machinery and red tests (1/6) (#2134)
177658c04 feat(surmap-training): M1c stubs + red tests — LoRA + SFT backends (#2062)
1c8a87d95 feat(surmap-training): M1b stubs + red tests — embedding + linear probe (#2061)
```

Those PRs shipped working features. `master`'s history says they shipped stubs, because nobody
retitled between planning and merge. **A merged PR's title cannot be fixed** — retitling the PR
afterwards changes the PR page and leaves the commit untouched.

### The format

```
<type>(<package>): <what this PR delivers> (#<stack-slug> K/N)
```

Example, for a six-PR stack whose slug is `tool-surface`:

```
feat(surmap-server): capability-aware operation and shape catalogue (#tool-surface 3/6)
fix(surmap-server): wire file access and report detections from prepare_file (#tool-surface 4/6)
```

**Type and scope stay exactly the repo's existing conventional-commit form.** The scope is the
package and nothing else, so anything that parses it — CI standards, changelog tooling, release notes —
sees what it has always seen. All stack metadata lives in one trailing group instead.

**`<type>` follows the node's kind**, so the stack reads as the mix of work it actually is:
`feat` (Feature) · `fix` (Bug fix) · `refactor` (Refactor / restructure) · `chore` (infra,
toolchain, mechanical migration — `refactor` when the migration moves code rather than
configuration) · `test` (test rebalance, test-style migration). A `feat` on a behaviour-preserving node lands a false
changelog entry on `master`, permanently.

**`#<stack-slug>`** identifies which stack a PR belongs to. Several stacks are usually open at once
in this repo, all touching the same packages; without it, `feat(surmap-server): …` on two open
PRs says nothing about whether they are related, sequenced, or independent. The slug is:

- **short** — one or two words, kebab-case, no date and no ticket number;
- **associative** — it should mean something to somebody skimming a PR list six weeks later.
  `tool-surface`, `connect-transport`, `model-acquisition` are good; `stack-3`, `mh-refactor`,
  `phase-two` are not;
- **chosen once, at planning**, and **never changed** — it is how the stack is recognised, so
  renaming it mid-flight loses the association it exists to create;
- **recorded in every changeset's `## Stack Context`**, which is where a later command reads it from.
  There is no shared manifest, so the slug lives in each PR's own row like everything else.

**`K/N` closes the group**, always last **in the PR title**. It is what tells a reviewer that #2139
is the fourth of six and cannot merge before three others — which a base-branch name does not say,
and a GitHub stack widget does not say in a notification e-mail.

**On `master` it is not last, and that is expected.** GitHub's squash merge appends ` (#<pr>)` to the
subject, so the commit lands as:

```
feat(surmap-server): capability-aware operation and shape catalogue (#tool-surface 3/6) (#2138)
```

Two groups, and they say different things: `(#tool-surface 3/6)` is the stack and the position,
`(#2138)` is the pull request GitHub merged. Do not try to pre-empt the second by leaving it out of
the first, and do not treat its presence as the format having been broken.

### The subject states what the PR delivers, in its finished state

Write the title for the reader of `git log` on `master`, who will never know a planning phase
happened. It names the capability as shipped:

| Instead of | Write |
|---|---|
| `…: machinery and red tests (1/6)` | `…: derive tool argument schemas from proto descriptors (#tool-surface 1/6)` |
| `…: stubs + red tests — LoRA backends` | `…: LoRA and SFT training backends (#training-backends 3/5)` |
| `pr 4 production wiring` | `…: wire file access and report detections from prepare_file (#tool-surface 4/6)` |
| `…: catalogue honesty (3/6)` | `…: capability-aware operation and shape catalogue (#tool-surface 3/6)` |

**Never** put a TDD phase or process artifact in a title: `red`, `green`, `stubs`, `failing tests`,
`WIP`, `phase 1`, `M1c`. Those describe where the work was when the branch was cut, not what the
branch delivers. **Never** let a title be a branch slug (`pr 4 production wiring`) — that happens
when a tool derives one and nobody replaces it.

The changeset's own Summary section is usually the best source: it already says what changes, in one
or two sentences, in delivered terms.

### The subject cap is real, and squash merge spends part of it

`.husky/commit-msg` enforces `^(feat|fix|…)(\(.+\))?: .{1,100}$`. Everything after `: ` must be
**≤ 100 characters, including the trailing `(#slug K/N)`** — and GitHub then appends ` (#<pr>)` on
squash merge, so the commit that lands is roughly **8 characters longer** than the title you set.
Budget for it. Check before setting a title, not after a rejected merge:

```bash
title="feat(pkg): what it delivers (#slug 2/5)"
subject="${title#*: }"
if [ ${#subject} -gt 100 ]; then
  echo "too long: ${#subject} (plus ~8 for the appended ' (#PR)')" >&2
  exit 1          # must abort — `|| echo …` succeeds and would let a caller carry on and apply it
fi
echo "ok ${#subject}"
```

### Who sets and who fixes a title

| Moment | Command | Obligation |
|---|---|---|
| PR created during planning | `/plan-pr-stack`, `/add-to-pr-stack` | Set the full format immediately. The subject states the *planned* delivery — write it as shipped, not as "stubs for". |
| A layer is added or split | `/add-to-pr-stack`, `/split-pr-to-stack` | **Renumber every PR in the stack** (see below). |
| Before ready for review | `/pr-wrap` | **Re-read the title and correct it** to what the branch actually delivered. Scope drifts during green; the title written at planning is a guess, and this is the last moment it can be fixed. |

`/pr-wrap`'s check is the load-bearing one. Everything else is a default that a green phase may have
invalidated.

### Renumbering when the stack changes shape

`K/N` is only true for one stack shape. Adding a layer changes `N` for **every** PR; splitting one
changes `K` for everything above it. A stale `2/6` on a seven-PR stack is worse than no number,
because it is read as fact.

So the commands that change the shape own the renumber, and must do it in the same run:

```bash
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
# For each PR in the stack, bottom-up, with its new K and the new N. Subject unchanged —
# only the trailing group moves.
gh api -X PATCH "repos/$repo/pulls/<pr>" \
  -f title="feat(<pkg>): <unchanged subject> (#<slug> <K>/<N>)" --jq '"#\(.number) → \(.title)"'
```

Use `gh api`, **not** `gh pr edit --title`: in some  orgs the latter fails with
*"Projects (classic) is being deprecated"* — the same GraphQL fault that affects `gh pr edit --base`
(see **Golden rules for landing**, rule 5).

**Do not renumber a merged PR.** Its title is already on `master` and the PR page no longer matters;
editing it creates the false impression that history was corrected. Leave it, and let `N` refer to
the stack as planned.

## Base tracking — source of truth

The authoritative base of a branch is its **GitHub PR base** (`baseRefName`):

```bash
gh pr view <branch> --json baseRefName,number,url --jq '.baseRefName'
```

Commands MUST resolve a branch's base in this order:

1. Explicit argument passed by the user (e.g. `/merge some-branch`).
2. The **registered stack** — `gh stack view --json` from a branch in the stack. This is the most
   authoritative source when the stack is registered. Note it errors with
   `current branch "X" is not part of a stack` when run from outside one, which is itself a useful
   signal that the stack was never registered.
3. This PR's changeset — `## Stack Context` → **Base** (see below).
4. `gh pr view <branch> --json baseRefName` — the open PR's base.
5. If none resolve, **ask the user** — never silently fall back to `master`.

> `/merge` merges from the **resolved base**, not from `master`. Only `/repoint` changes a base to
> `origin/master`.

### Remote base drift — the live PR base outranks the local record

The five-step order above finds the base the *local* view believes in. The PR base on GitHub can
change underneath it — a predecessor merged and GitHub retargeted the PR to `master`, or somebody
repointed it by hand. Every command that **rebases or merges a stack branch onto its base**
(`/pr-stack-rebase`, `/merge`, `/fix-pr-stack`, and the hard-gate callers through them) MUST also read
the live `gh pr view <branch> --json baseRefName` and compare it with the resolved base:

- **Differs, base came from stack object / changeset / local state** → the remote wins: restack
  onto `origin/<remote-base>` with `git rebase --onto origin/<remote-base> <old-base-tip> <branch>`
  (never a plain rebase — it replays the old base's commits), and update this PR's changeset
  `## Stack Context` **Base** to match.
- **Differs, base came from an explicit argument** → stop and ask.
- Only `/repoint` ever *changes* the PR base on GitHub; these commands follow it, never write it.

Details and the `<old-base-tip>` lookup order: `/pr-stack-rebase` § Step 2b.

## Stack context lives in each changeset

There is **no shared stack document**. Every PR's changeset carries its own stack context, in a
`## Stack Context` section sitting beside the `## Inherited Dependencies — do not implement here`
table it already has. The section describes **this PR only**: where it sits, what it owns, and
whether it can go green yet.

This is a companion to the registered stack, never a substitute. The **stack object on GitHub is the
source of truth for topology** — branch, base, order, what has landed. The changeset carries only
what GitHub cannot hold: the owned API surface, the seam the split follows, and greenability.

Location: nothing new. It is part of `docs/<area>/1-WIP/YYYY-MM-DD-<changeset-slug>.md`.

Structure:

```markdown
## Stack Context

**Stack**: <stack name> · slug **`#<stack-slug>`** — this PR is **k of n** ·
[#<pr>](https://github.com/<org>/<repo>/pull/<pr>)
**Branch**: `pr-k-<slug>` · **Base**: `pr-<k-1>-<slug>` (or `origin/master` for the bottom PR)
**Epic**: [#<epic>](https://github.com/<org>/<repo>/issues/<epic>) — the stack's DAG home; this node is
`n<k>` in its block. `#pending` until `/plan-pr-stack` opens the epic (Step 5's 3b), back-filled in
pass 2 (Step 6g). A changeset without it is incomplete: a later command that changes the stack
finds the epic here.
**Successor**: `pr-<k+1>-<slug>` — or `none — top of stack`. This PR's own GitHub URL is recorded
here after submit. Do **not** stamp a successor URL by editing a predecessor's changeset.
**Kind**: <kind> · behaviour-<adds|changes|preserves> — the `(Type, Behaviour)` pair from the header
**Workflow**: preset `<feature|bugfix|restructure|migration|rebalance|infra>` · planned by `<command>` · pass-2 = <the red step> — the rows themselves are this changeset's `## Workflow`
<and, when the developer chose something other than the kind's default:>
**Workflow override**: `<what they chose>` instead of `<the default>` — <what it trades>,
approved <who>, <date>. See `## Decisions & Trade-offs`.

Why the boundary falls here: <one or two sentences on the seam this PR's surface follows>

### Owned API surface

<the modules and symbols this PR owns. No other PR in the stack may implement these; this PR must
finish all of them.>

### Green wave

**Wave:** <k> of <m>
**Node:** n<k> — this PR's position in the stack, the identity the rest of this section uses
**Concurrent with:** <the other nodes of this wave — `n4, n5` — or `none — this node is alone in its wave`>
**Blocks:** <the nodes that wait on this one, with what each needs — `n6 (its add-key test needs
this node's agent client to actually perform the add)` — or `nothing`>

Real dependency edges, as opposed to the branch line:

    n1 → n2, n4, n5      n2 → n3      n5 → n6

### Greenable independently?

**yes** — it owns everything its tests drive.

<or>

**no — blocked by n<j>** (`pr-<j>-<slug>`): <which of this PR's tests drive which of n<j>'s stubs>.
A test still red for that reason is blocked-on-n<j>, not a failure.

### Trunk-merge safety

**When this PR merges alone:** production deploy/runtime and local dev workflows stay working
(name the commands or surfaces checked — e.g. `uv run pytest -q`, CI smoke). **Local dev data:** may
break / require reset — <yes, what to reset | no>. **Production data:** <none | requires explicit
approval — link to `## Decisions & Trade-offs` or the Step 1 note>.
```

**`Kind` and `Workflow` are the dispatch, and they are written down rather than derived.** The
pass-2 router picks this node's red step from them, and the `[wf]` rows they name say
whether the node is implemented by `/green` or `/code-restructuring`. Deriving either from `Type`
alone is wrong twice over — `Type: Migration` is two different kinds, and a workflow the developer chose over the
kind's default would be invisible.

Everything in `### Green wave` is written in **node numbers** (`n1 … nN`), which exist from the
moment the decomposition is settled — see *Node numbers* above. Do **not** leave PR-number slots here
to be back-filled after submit; the grouping is decided before any PR exists and must be readable
then. A PR number belongs in this section only when the dependency is on the **composition of an
already-open PR**, and then it rides along with the node: `n3 (#2403)`.

The one place a PR number is unavoidable is the header's own `[#<pr>](…)` link — that is this PR's
identity on GitHub, filled in after its submit, not a reference to a sibling.

`### Green wave` and `### Greenable independently?` are **two views of one fact, and they may not
disagree**: `**Wave:** 1 of m` means *greenable now*, so it forces `Greenable independently? yes`;
any wave above 1 forces a `no` naming the PR whose behaviour is missing. Whichever of the two you
correct, correct the other in the same commit.

The wave is also the **same decision as the `K/N` in the title** — the line is the green waves
concatenated, blockers leading each wave (*Order inside a green wave*). A changeset whose wave and
whose position contradict each other means the line was never derived from the waves; fix the line,
not the number.

The **slug** is recorded here because there is no shared manifest and PR titles are built from it
(see **PR titles**). A command adding or splitting a layer reads it from any changeset in the stack
rather than inventing a second one.

Only the **base** and **successor** are named, never the predecessor: a predecessor wraps and deletes
its changeset first, so a back-reference would dangle (see the forward-only linking rule below). The
base is a branch name, which stays valid after that branch's docs are gone.

### Why per-changeset rather than one manifest

A shared `STACK-*.md` had to outlive every individual PR, and that single fact caused all of its
problems:

- It could not be wrapped, because it had no State B and its lifetime was the whole stack — so it had
  to be **handed from each wrapping PR up to the next open one**, a cross-branch push during what
  should be a self-contained wrap.
- Every PR edited the same file to update its own row, so every rebase produced a **union conflict**
  on it, and each wrap produced a **modify/delete** conflict on top.
- Its status column was a hand-maintained copy of what `gh pr list` already knew, and went stale
  between the moment a PR landed and the moment somebody remembered to edit the table.

Embedding removes all three. Each changeset is **created with its PR, wrapped with its PR, deleted
with its PR**. Nothing outlives one PR, so nothing has to move between branches, and no two PRs ever
edit the same planning file.

### What replaced the manifest's global views

| The manifest used to hold | Where to get it now |
|---|---|
| stack order, branches, bases | `gh stack view`, or `gh pr view <N> --json baseRefName` |
| which PRs have landed | `gh pr list`, `gh stack view` |
| per-PR owned API surface | that PR's changeset, `## Stack Context → Owned API surface` |
| per-PR greenability | that PR's changeset, `## Stack Context → Greenable independently?` |
| per-PR green wave, and who it runs alongside | that PR's changeset, `## Stack Context → Green wave`, and the PR description — **each PR states its own row only** |
| per-PR trunk-merge safety | that PR's changeset, `## Stack Context → Trunk-merge safety` — prod + local dev workflows when merged alone; local dev data may break; prod data only with Step 1 consent |
| the whole-stack wave grouping | reconstructed by reading the `**Wave:**` line of the open PRs (`gh stack view` for the line, each PR body for its wave). `/plan-pr-stack` also reports the grouping to the user at planning time |
| why the work was split this way | each changeset states its own seam; the durable whole-stack rationale lands in the package docs when the bottom PR wraps |

**The wave grouping is committed per PR, never as one table.** A PR states its own wave, who it can
be greened alongside, and what it blocks — that is its own row, and it wraps and disappears with it.
A committed whole-stack wave *table* is the manifest under another name: it would live in the bottom
PR, which wraps **first**, so it would vanish exactly when the PRs above still wanted it. If the
grouping is needed as a whole, read it off the open PR bodies.

### Rules that follow

- **No `docs/<area>/1-WIP/STACK-*.md`.** If you find one, it predates this model; fold each row into the
  matching changeset's `## Stack Context` and delete it.
- **A changeset states its own row and nothing else.** Never record a sibling's status — that is the
  stale-copy problem returning, and it puts two PRs back in one file.
- **Nothing hands off at wrap.** `/wrap-context-docs` transfers this PR's changeset and PRD and
  deletes them. There is no third document, no cross-branch push, and no "action required" notice.
- **When `gh stack view` disagrees with a changeset, the stack object is right.** Fix the changeset.
- **A node's `## Prerequisites` is its own too.** The deferred-work items
  (`<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/`)
  *that node* runs into, with a verdict each — never a sibling's list.
- **A node above a restructure node declares the rewrite it will inherit**, and repairs it in a new
  commit after its own `/pr-stack-rebase`.
- **Every node carries its own changeset, whatever its kind.** The PRD is what varies; the changeset
  is how a context-free implementer learns the background at all.
- **Every node's changeset states its kind** as the header's `(Type, Behaviour)` pair — never
  `Type` alone, which cannot tell a contract change from a mechanical migration — mirrors it in
  `## Stack Context → Kind`, names the commands in `Workflow`, and states its proof in
  `## Verification`. A node planned as a feature because nobody asked what kind it was is the
  commonest defect this model has: it spends a PRD on a move and accepts nothing.
- **No node without verification.** The method is the highest rung of the V1–V4 ladder the node can
  reach; V4 carries the developer's recorded consent; V5 means the node is not planned.


## Document linking rule (forward-only)

Each PR carries its **own** PRD + changeset. Because a stacked branch inherits its predecessors'
docs, a successor's tree contains its predecessors' docs — but the reverse is not true, and PRs are
**wrapped when they are set ready for review**, bottom-up, so a predecessor's docs leave
`docs/<area>/1-WIP/` before its successors'.

To avoid dangling links in `1-WIP` as PRs land, references flow **predecessor → successor only**:

- ✅ A predecessor's PRD/changeset MAY link forward to its successor's PRD/changeset
  (add a `## Successor PRs` section listing the next PR's docs).
- ❌ A successor's PRD/changeset MUST NOT link back to a predecessor's docs.

Rationale: the predecessor is wrapped and removed from `1-WIP` first. A backward link from a
still-open successor would immediately dangle. A forward link lives only in the doc that is itself
about to be wrapped, so nothing left in `1-WIP` ever points at a removed file.

**This is why readying a stack bottom-up matters.** Wrapping is triggered by setting a PR ready for
review (see `/wrap-context-docs`), so the ready order *is* the wrap order. Ready a successor before
its predecessor and the successor's docs leave `1-WIP` first, which is exactly the case the
forward-only rule cannot survive — the predecessor's forward link would then point at a removed file.

## Golden rules for landing (read before merging anything)

The dependency is encoded in **branches**, so branch lifetime and merge order matter — get them
wrong and GitHub silently **closes** PRs. Registering the stack does not repeal these rules; it
automates some of the bookkeeping.

1. **Merge bottom-up.** Land PR₁ (closest to `master`) first, then PR₂, then PR₃. Never merge a
   higher PR before the one it is based on. Nothing in GitHub enforces this, registered or not.
2. **A branch must stay intact until no open PR bases on it.** PR₁'s branch is PR₂'s base — deleting
   it while PR₂ is open **closes PR₂**, and a PR whose base branch no longer exists **cannot be
   reopened or re-based via the API**. This is the #1 way stacks break.
3. **A registered stack merges only through `merge-async`.** `gh pr merge`, the ordinary REST
   merge and the `#automerge` bot's regular merge are all off the table — the first two are
   **refused**:
   ```
   $ gh pr merge <N> --squash
   GraphQL: This pull request is part of a stack and must be merged using the
   asynchronous merge REST API. (mergePullRequest)

   $ gh api -X PUT repos/{owner}/{repo}/pulls/<N>/merge -f merge_method=squash
   403  Merging stacked PRs via this endpoint is not supported.
   ```
   Use `PUT /repos/{owner}/{repo}/pulls/<N>/merge-async`, which returns
   `{"status":"pending","details":{"uuid":…}}`, and poll
   `GET /repos/{owner}/{repo}/pulls/<N>/merge-async/{uuid}` until `status` is `merged`.
   **`pending` means enqueued, not merged** — poll before touching the next PR. `/merge-pr-stack`
   drives this loop.
4. **Do not retarget a registered stack's PR — GitHub owns it.** `PATCH .../pulls/<N> -f base=…`
   answers `422 Cannot change the base branch because the pull request is part of a stack.` After a
   merge GitHub **restacks** the successor — retargets *and* rebases it — so it comes out based on the
   trunk carrying only its own files, with nothing to do locally. `delete_branch_on_merge` is safe on
   a registered stack for the same reason: the cascade in rule 2 is GitHub's to manage.
5. **The auto-restack only happens when the rebase is clean.** On a conflict GitHub leaves the
   successor on a **stale base**, `CONFLICTING`, with a diff that includes every already-merged
   predecessor — an inflated `changedFiles` is the tell. Repair it by hand, and **check
   `changedFiles` after every merge** rather than assuming. See **Repairing a failed restack** below.
6. **Each PR owns only its own diff.** Don't cherry-pick earlier commits forward, and never
   implement a symbol another PR owns.
7. **Never `gh stack unstack` without explicit consent** — it deletes the stack on GitHub, not just
   locally. `--local` is the safe variant.

## Landing sequence

### Registered stack — the default path

Two commands, in order. **Do not merge without the fix pass** — predecessor-comment windows close
when a PR lands.

1. **`/fix-pr-stack`** — wait for CI and review bot-review on each PR's **current SHA before any
   rebase**, sweep every review **thread** (the full discussion, including human replies and
   reactions to bot comments), **assess TODOs and code issues this stack added** and plan with the
   user to **rescope an existing PR** or **add PR(s) at the tail**, then bottom-up rebase, conflict
   resolution, and local-gated fixes. After each push it **does not wait for CI**; it trusts the
   local build. Records progress in `tmp/pr-stack-<slug>.md` (gitignored). Adopt
   `tmp/merge-stack-<slug>.md` if a previous run left that name.
2. **`/merge-pr-stack`** — the merge wave only: re-sweep comments that arrived during CI, wait for
   `mergeStateStatus` `CLEAN`, `#skipreview`, `merge-async`, restack repair, then the TODO
   reckoning. It refuses to start if `/fix-pr-stack` has not finished.

**Sweep the open review threads across the whole stack first** (`/fix-pr-stack` Wave 1), before any
PR merges. Reviewers comment on whichever PR's diff showed them the code, so a thread raised on PR X
often has to be fixed in a **different** PR — the one that owns that symbol, by the same ownership
rule that governed planning. The direction is asymmetric and only one case is recoverable later:

| Comment left on | Fix belongs to | Consequence |
|---|---|---|
| PR X | a **successor** of X | fine — X merges, the fix rides in the later PR |
| PR X | a **predecessor** of X | **blocking** — that PR merges first, so the fix must land in it *before* it does |

A merged PR's threads are archived in practice, so a defect raised there and not triaged is lost.
Validate each **thread** against the code **at HEAD**, never against the diff hunk quoted in it —
every `/pr-stack-rebase` moves lines under comments — and against the **latest substantive human
ask**, including replies to bots and human reactions (the same rule `/fix-pr` uses). Signal each
verdict on the comment itself (👍 actionable, 🚀 fix pushed). A claim that does not hold gets an
**evidence reply and no reaction**: there is no negative reaction in this protocol, because a
thumbs-down leaves the reviewer a verdict with nothing to check, and the author of the code is the
last person who should be closing an argument without showing their work. Those replies are posted
without an approval gate, behind the agent prefix (`pr` skill, **Comments posted on the user's
behalf**), and reported back to the user afterwards.

**Wait for CI and review bot on the pre-rebase SHA first** (`/fix-pr-stack` Wave 0). Rebasing
before those runs finish drops or outdateds comments that have not been posted yet, and hides
whether a failure already belonged to this SHA.

**Then apply the fixes in their own bottom-up pass, before any merge, gated locally only** —
lint/type-check/package tests per layer, push, next layer, **without waiting for CI after the push**
(`/fix-pr-stack` Wave 2). Each push starts that PR's CI in the background, so `/merge-pr-stack`
consumes runs that are already warm; each layer rebases onto its just-pushed parent first, with the
recorded-tip `--onto` mechanics from `/pr-stack-rebase` cascade mode.

Then `/merge-pr-stack`: bottom-up, one PR at a time — never start the next before the current one
reports `merged`:

1. `gh stack view` — confirm the order and that the bottom PR's base is the trunk. Re-sweep this
   PR's threads (reviewers comment while CI runs) and apply any comment fixes the plan still
   assigns to this PR, including ones raised on another PR's thread.
2. Clear the review gate on the tip. At  that is `gh pr comment <N> --body '#skipreview'`; poll
   `reviewDecision` until `APPROVED`.
3. Wait for CI. **Poll `mergeStateStatus` until `CLEAN`, not a count of pending checks** — a check is
   registered on the rollup a moment *after* a push, so "zero pending" is true before CI has started.
   That false positive is worst right after a force-push, which is exactly when a stack is being
   repaired.
4. Merge with `merge-async` (golden rule 3), passing `commit_title` **explicitly**. The repo's
   `squash_merge_commit_title` is typically `COMMIT_OR_PR_TITLE`, which uses the *commit* subject when
   a PR has exactly one commit — so a one-commit PR silently lands under a commit message instead of
   the title the stack was careful about. See **PR titles**.
5. Verify the restack: the successor should now be `base=<trunk>`, `MERGEABLE`, and show **only its
   own file count**. If it does not, repair it (below).
6. Repeat from 2 with the new tip.

A red check is work, not a stop: pull the failure (`get_failures_from_log`), fix it **in the PR that
broke it**, push, wait again. Never force-merge past it and never patch it in a successor.

**`/merge-pr-stack` does not pause for the user while CI runs.** `#skipreview` registering, a
`merge-async` `pending`, GitHub restacking, and `mergeStateStatus` still `BLOCKED` are the command's
job — stay in the loop until the requested PRs report `MERGED`. Yield only for a human decision
(first-merge confirmation, unstack consent, an unresolvable conflict, a product/scope choice). See
**Stay until merged** in `/merge-pr-stack`. `/fix-pr-stack` is the opposite after a push: it never
waits on the new SHA's CI.

#### Repairing a failed restack

```bash
# The successor may NOT descend from the predecessor's final tip — its implementer
# may have rebased or amended after it was cut. Find the real fork point: the
# parent of the successor's first OWN commit. Do not assume.
git log --oneline origin/<trunk>..origin/<succ>     # where its own work starts
git log --format='%h parent=%p' -1 <first-own-commit>

git checkout -B <succ> origin/<succ>
git rebase --onto origin/<trunk> <that-parent> <succ>
# resolve, then
git push --force-with-lease origin <succ>
```

`--onto` is **required**. A plain `git rebase <trunk>` replays the predecessors' commits too, because
a squash merge lands their content under a commit unrelated to theirs.

When a conflict is two branches bumping the same literal — a count, an enumeration — **neither side is
right**. Compute the value from the source of truth, and ask whether an assertion that merely
restates its own computed input is worth keeping at all.

Docs are **not** wrapped here — each PR's changeset and PRD were already wrapped when that PR was set
ready for review, bottom-up. By the time a PR merges its docs have left `1-WIP` already.

Between steps, re-read `gh stack view`. If it disagrees with a changeset's `## Stack Context`, **the
stack object is right** and the changeset needs updating.

### Unregistered stack — manual fallback

Only when `gh stack` is unavailable or the stack was never registered. `/merge` keeps a branch current
with its **still-open** base mid-flight; `/repoint` **changes** the base to `master` (and restacks)
after the predecessor lands. Two consistent strategies:

- **Strategy A — retarget the whole stack to `master` up front.** Before merging anything, `/repoint`
  every PR except PR₁ onto `master`. Now each PR is independent, branch deletes can't cascade, and you
  merge bottom-up resolving conflicts per PR. This exists to defend against the base-deletion cascade;
  on a registered stack `gh stack sync` covers that, so prefer the path above.
- **Strategy B — just-in-time.** Merge PR₁ without deleting its branch, `/repoint` PR₂ onto master,
  verify PR₂ is open + mergeable, then delete PR₁'s branch and merge PR₂. More steps, easier to get
  wrong.

Per-PR, bottom-up: `/repoint` onto master (if not already) → `git merge origin/master` → resolve →
push → `gh pr merge <N> --squash --delete-branch` (safe only once no open PR still bases on it).

Wrapping is not part of this sequence: each PR's docs were wrapped when it was set ready for review.

## Worktrees pin branches — plan around it

**Git refuses to update a branch that is checked out in another worktree.** This is a git invariant,
not a `gh stack` quirk, and it constrains every stack-wide operation:

```
⚠ Failed to fast-forward master: cannot force update the branch 'master'
  used by worktree at '/path/to/repo'
```

Consequences:

- `gh stack sync` / `gh stack rebase` **cannot rebase a branch pinned by a worktree**, and cannot
  fast-forward trunk if trunk is checked out somewhere (typically the primary clone). `--no-trunk`
  skips the trunk half; for the rest, free the branch first.
- `gh stack init` and `gh stack checkout` **check a branch out**, so they fail if that branch is
  already checked out elsewhere.

So: **use one working tree for stack-wide operations** (`init`, `sync`, `rebase`, `modify`),
with the stack's branches free. Per-branch worktrees are fine for *editing* a branch — `/green` never
needs `gh stack` to move a branch — but remove or park them before a stack-wide `sync` / `rebase`.

`/plan-pr-stack`'s per-layer `gh stack submit` is the exception that runs while planning: push the
**current** branch first (`git push origin HEAD`), then submit to open that PR. If a predecessor is
already pinned, submit may fail — stop; do not treat submit as a cascade rebase. `/green` checkouts
wait until planning has run its completion gate and restored the original branch — the planner's
second pass checks every stack branch out again, bottom-up, and a pinned one stops it.

**Plan in the current worktree**, not one worktree per PR. `/plan-pr-stack` records the starting
**named** branch (refuse detached HEAD), cuts each next layer with `gh stack init --base <trunk>` /
`gh stack add`, submits that PR immediately with its planning docs (pass 1), then revisits each
branch once in stack order for its rebase + red commit (pass 2), and **restores the original
branch** before the final cascade `/pr-stack-rebase` — if that branch was `master`, this worktree
is on `master` again (`git checkout master`, not detached `origin/master`). Do not keep a checkout
of a layer between visits — it pins the branch and blocks the agent who should be greening it. A worktree
in this monorepo costs **~7 GB** once `node_modules`, `src/protogen` and the per-package Python venvs
exist; six of them is ~42 GB. Create per-PR worktrees only when `/green` actually runs, and only for
the PRs being worked. `gh stack checkout <PR#>` reconstructs a stack branch later without needing
the old path.

### Delete a temporary worktree as soon as its branch is pushed

**Default: once a branch is pushed and the work in that worktree is finished, remove it immediately**
— unless the user has asked to keep it. "Finished" means the in-stack loop has run its course:
`/green` pushed, `/validate-changes` found no gaps, and `/pr-wrap` is done. A push at the end of
`/green` is not by itself the signal to delete — the same worktree still runs `/validate-changes` and
`/pr-wrap`. Do not leave worktrees lying around waiting for a cleanup pass. At ~7 GB
each they exhaust a disk quickly, and a pinned branch also blocks the stack-wide operations above.

Nothing is at risk once the branch is on the remote: the worktree holds no unique state, and
everything untracked in it (`node_modules`, `src/protogen`, venvs, `dist`) is regenerable.

**Verify before removing** — cheap, and the only thing standing between "reclaim disk" and "lose
work":

```bash
W=<worktree-path>; B=<branch>
git -C "$W" status --porcelain | grep -v '^?? '        # must be empty: no tracked-file changes
git -C "$W" rev-list --count "origin/$B..HEAD"          # must be 0: nothing unpushed
git rev-parse "$B" && git rev-parse "origin/$B"         # must match
```

If anything is unpushed or uncommitted, **push first** (or use `/abandon-worktree`, which commits a
`wip:` change, pushes, then clears artifacts). Never discard tracked work to reclaim space.

Then:

```bash
git worktree remove --force <worktree-path>   # --force: untracked build artifacts are expected
git worktree prune
```

Removal can take minutes while `node_modules` is deleted — reasonable to run in the background.

**Never delete the branch.** `git worktree remove` does not, and must not: a stack branch is a
successor's base, and deleting it closes that PR (golden rule 2).

**Keep the worktree when:**

- The in-stack loop is still running in it — `/green` has pushed but `/validate-changes` or
  `/pr-wrap` has not finished. Remove it after `/pr-wrap`.
- The user asked to keep it, or is still working in it.
- It was handed to a human to continue in — e.g. opened in an editor by
  `scripts/worktree-handoff.sh`. Removing that destroys their session; leave it.
- The branch has unpushed commits or uncommitted tracked changes. Push, then remove.

To come back later: `git worktree add <path> <branch>`, or `gh stack checkout <PR#>` for a stack
branch, then reinstall dependencies. Recreating is cheap; losing unpushed work is not.

## Keeping a branch current — per-worktree rebase vs stack-wide sync

There are two ways to bring stack branches back onto their parents, and picking the wrong one is how
concurrent `/green` work gets clobbered.

| | `/pr-stack-rebase` (single) | `/pr-stack-rebase` (cascade) | `gh stack sync` / `gh stack rebase` |
|---|---|---|---|
| Scope | **the current worktree's branch only** | **the layers you named**, bottom-up | **the whole stack** |
| Where the rewrite runs | here | **in a worktree that owns each branch** — delegated via `git -C`, or borrowed here when nothing pins it | one worktree, for all branches |
| Pushes | that one branch, `--force-with-lease` | each branch individually, stopping at the first failure | every branch, atomically |
| Needs branches free | no — only the current one | no — pinned branches are delegated to, not fought | **yes, all of them** |
| Use from | a per-PR `/green` worktree | any clean worktree, including a planning one | a dedicated stack-wide worktree |

**During concurrent implementation, each worktree rebases itself with single-mode
`/pr-stack-rebase`.** That is the shape that works when every stack branch is checked out somewhere,
and it is the mode every hard-gate caller uses.

**Cascade mode covers the case single mode cannot**: several layers went stale at once — typically
because a predecessor was greened and force-pushed — and nobody is sitting in each of those worktrees.
It is **not** `gh stack sync` in disguise. `sync` rewrites every branch and force-pushes them
atomically from one worktree, which git refuses when a branch is checked out elsewhere and which
would clobber whoever is mid-`/green` where it succeeds. Cascade instead rebases **only the named
layers**, runs each **inside a worktree that owns that branch**, refuses outright when such a worktree
has uncommitted or unpushed work, and pushes **one branch at a time**, stopping at the first conflict.

Its load-bearing mechanic is `--onto` with each layer's **recorded pre-rebase tip**: once layer K has
been rewritten, layer K+1's merge-base no longer exists on K, and a plain `git rebase origin/<base>`
there would replay **K's old commits** as K+1's own — silently duplicating a predecessor's work into
its successor's diff. That is exactly what running single mode N times by hand gets wrong.

`/green`, `/green-attack`, `/validate-changes`, and `/pr-wrap` **always** invoke `/pr-stack-rebase` on a stack branch before they
run implementation or a code diff — not only when `gh stack view` shows ⚠. Already-current is verify-and-publish (leak
check, no rewrite, push if the remote lacks this state). The rebased state is always on the remote
before the calling command starts its own work. A leaked `origin/<base>..HEAD` is a stop: do not analyze those files as this
PR's work and do not delete them.

Rules for the per-worktree path:

- **Bottom-up.** PRₖ is only worth rebasing once PRₖ₋₁'s worktree has rebased and pushed. Otherwise you
  rebase onto a tip that is about to move and pay for it twice.
- **Rebasing your branch makes your successors stale** — `gh stack view` will show them `⚠`. Expected,
  not a defect: each successor clears it by running `/pr-stack-rebase` in its own worktree. Say so in
  the output so the next worktree knows it is their turn.
- **Never `git rebase --update-refs`** from a per-PR worktree — it rewrites sibling stack branches
  all at once, which is the atomic, all-branches behaviour this path deliberately does not have.
- **A branch is only ever rewritten from a worktree that owns it.** Cascade mode delegates to the
  worktree that pins a branch (`git -C`) and borrows the current one only when nothing pins it —
  restoring the original branch afterwards, including after a failure.
- **Cascade stops at the first conflict or failure**, and never continues onto a half-resolved or
  stale parent. Report which layers completed, which stopped, and which were not attempted.
- **Never implement a predecessor-owned symbol while resolving conflicts.** If the base's stub
  conflicts with your code, keep the stub.

Reach for `gh stack sync` only when the stack's branches are free — typically the planning worktree
before submit, or the landing worktree between merges (see the landing sequence above).

## ⚠ Needs rebase — the commit-after-branching trap

`gh stack view` marks a branch `⚠` when it does not contain the tip of its parent. The usual cause:
**a commit was added to a predecessor after its successor was already cut from it.**

It is easy to miss because GitHub's PR diff still looks correct — the diff is computed from the
merge-base, so each PR keeps showing only its own delta. Nothing is visibly broken; the stack is just
built on a stale parent.

Detect and fix:

```bash
gh stack view                 # look for ⚠
gh stack sync                 # cascade-rebase onto the correct parents, then push
# or, when trunk is pinned by another worktree:
gh stack rebase --no-trunk
```

Both of those are **stack-wide** and need every stack branch free. While branches are checked out in
per-PR worktrees, clear the `⚠` the per-worktree way instead: run `/pr-stack-rebase` in each affected
worktree, bottom-up (see the comparison above).

A plain git check for the same thing, parent by parent:

```bash
git merge-base --is-ancestor <parent> <child> && echo OK || echo "BROKEN <parent> -> <child>"
```

On conflict, `gh stack sync` restores every branch to its original state and tells you to run
`gh stack rebase` interactively. Rebasing rewrites successor SHAs and force-pushes — harmless on
drafts with no reviews, but on a reviewed PR it can dismiss approvals (see below), so say so before
doing it.

## Recurring shared-file conflicts

When every PR edits the **same file** (a catalog/index table, a changelog, a shared descriptor),
merging each onto the growing `master` conflicts on that file every time. Resolve by **union** — keep
every PR's contribution — not `ours`/`theirs`.

Planning documents no longer belong to this category: each PR's stack context lives in its own
changeset, so the stack itself contributes no shared file to conflict on.

## Approval dismissal after resolution commits

If branch protection dismisses stale approvals, the conflict-resolution commit drops a prior
approval. Re-trigger it **after** that commit — at , re-post `#skipreview` (`gh pr comment <N>
--body '#skipreview'`) and poll `gh pr view <N> --json reviewDecision,mergeStateStatus` until `CLEAN`.

## Recovery — a PR closed because its base branch was deleted

The **head branch is usually still intact** (only the base was deleted). You cannot reopen/re-base
the closed PR — recreate it against `master` from the surviving head branch:

```bash
git push -q origin <head-branch>
gh pr create --base master --head <head-branch> --title "<same title>" \
  --body "Recreated after #<N> auto-closed when its stacked base branch was deleted."
```

Then **re-register the stack** — a recreated PR is not part of the old stack object:
`gh stack init <branches bottom-to-top>` → `gh stack view` → `gh stack sync`.

## Recovery — the stack exists on GitHub but not locally

After deleting worktrees or on another machine, do not rebuild the stack by hand. `gh stack checkout`
discovers it from the GitHub API and sets it up locally:

```bash
gh stack checkout <PR-number-or-URL>   # any PR in the stack
gh stack view                          # confirm topology and status
```
