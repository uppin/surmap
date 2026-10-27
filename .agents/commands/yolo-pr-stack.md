---
description: /plan-pr-stack with an implementation pipeline bolted onto pass 2 - as soon as a node's planning rows are closed and its green-wave needs are met, give it an ephemeral worktree and run that node's changeset [wf] rows in order (what /yolo does for one branch), each stage in its own subagent sized to the node, then #skipreview, and remove the worktree when the PR is green. A final **sweep node** is planned at the tail once the pipelines drain: it solves every code issue the stack added and every TODO it can, and the TODOs still open halt the stack for the developer's decision. Planning opens with one interview (requirements, kinds, decomposition, and every later question it can foresee); once the developer accepts its answers the run is under #yolo - no further question, each one recorded as a deferred answer, a stage's question relayed to the orchestrator, which answers or refines it. Pointed at a stack that is already partly done, it **resumes**: each node's stage is its next [wf] row, checked against git, GitHub and CI. Never lands a node: automerge in the request is not merge intent here, and the stack lands through /merge-pr-stack. Every subagent is started with an explicit model **and** effort taken from the changeset's complexity score, and the orchestrator tells the user which and why before each one starts
---
## YOLO PR Stack — `/plan-pr-stack`, and every ready node implemented while pass 2 keeps going

`/yolo-pr-stack` is `/plan-pr-stack` with one extra mode in **pass 2**. Run
`.agents/commands/plan-pr-stack.md` end to end — interview, decomposition question, pass 1, pass 2
with its per-PR guardrail verification, the completion gate — and add the **pipeline** below at the
two points named in *Hooks into pass 2*. Nothing in `/plan-pr-stack` is skipped, shortened or
relaxed. The pipeline only runs the rows each node's changeset already lists after its planning
rows.

**A Roadmap page as the input** works as it does for `/plan-pr-stack` (its Step 1, the
`roadmap-driven-development` skill): the planning reads and verifies the page, and the Plan publish is
a TODO in each node's changeset. The ready publish is not a TODO: each node's `[W]` stage makes it,
`/pr-wrap` step 9 right after it readies the draft, so the page shows each node ready for review
once GitHub does, and reconciles the merged ones. `[F]` publishes nothing.

**Each node's changeset decides what runs on it.** Its `[wf]` rows
(`.agents/skills/pr-lifecycle/SKILL.md`) list the node's rows; `/plan-pr-stack` closes
the planning ones, and the pipeline runs every row after them, in order, exactly as `/yolo`
(`.agents/commands/yolo.md`) would on that branch — re-grepping the rows before every row, then
the post-wrap `/fix-pr` and `/yolo`'s **Approve** (`#skipreview`). It never runs **Land**: the stack lands through
`/merge-pr-stack` and `merge-async`, and `#automerge` in this request is not merge intent here. It
is run **row by row, one subagent per stage**, rather than as one
`/yolo` subagent per node, because the sizing rubric below gives the green row and the wrap row
different models and lets the post-wrap `/fix-pr` inherit the wrap agent's context — one `/yolo` agent would
run every row on a single model.

```
pass 2 closes PRₖ's planning rows (commit 2 pushed) → moves on to PRₖ₊₁
        └─ PRₖ ready? ──► ephemeral worktree ──► [G] Green row ──► [W] Wrap row ──► [F] post-wrap: /fix-pr · Approve ──► worktree removed
                                                   [G] and [W]+[F] = background subagents; [F] continues [W]'s agent, model sized to the node
```

```
pipelines drain → cascade → collect the stack's open TODOs + code issues → plan the SWEEP node (tail) → its pipeline
                                                                              └─ TODOs still open ──► ⛔ halt: continue the stack | defer, per TODO
                                          → stack reported ready; landing is /merge-pr-stack (merge-async)
```

The orchestrator is the session running pass 2. It owns the worktrees, picks each subagent's model,
starts the next stage when the previous one reports, runs the planning interview, and is the
**supervisor** of every stage. Subagents cannot ask the user anything, and under the step contract
no row's command asks. A row that needs the developer's word **halts** ⛔ (the `pr-lifecycle` skill
§ *Halts*), the subagent reports 🔴, and that node stops. A row with a question ends its stage with
`❓ question`, and the orchestrator answers it (*Questions from a stage*).

## Resume mode — a stack that is already partly done

Run this command at a stack that already exists — the user gives a PR in the
stack, the stack slug, or says "resume" while a stack branch is checked out — and it does **not**
re-plan. It reads where every node actually stands and starts each node at the first stage it has not
finished. Nothing that is already done is redone, and nothing is trusted that cannot be seen.

**Evidence, not memory.** A ledger file in the scratchpad is a *hint* at what happened; git, GitHub and
CI are the truth. If they disagree, the evidence wins and the final report names the disagreement.

### Step R1 — locate the stack and its edges

`gh stack view` for topology; each node's changeset
`### Green wave` and PR body's `## Stack` block for dependencies (the same source Dispatch uses); the changeset at each branch head
(`git show origin/pr-<k>-<slug>:<path>`, or the wrapped docs if it is already gone from `1-WIP/`),
and its `[wf]` rows. A branch with no registered stack is not a stack: stop and say so.

### Step R2 — derive each node's status

Read-only, from the orchestrator, one node at a time. **The node's `[wf]` rows name its stage**:
the next row, by the `pr-lifecycle` skill's next-row grep — **after setting aside any row after
Wrap** (PR, Checks and threads, Approve, Land) that a node planned under the old workflow still
carries, open or not. Those are not stages; a node whose rows up to Wrap are done is post-wrap and
the table below reads it from GitHub. Being read-only, R2 only sets them aside, and a node whose PR body still
carries one is **never `done`**: it is `F`, so its `[F]` runs `/fix-pr`, whose Step 0 makes an open
legacy Stash publish and then deletes the rows (step contract, step 2 *Rows after Wrap*). The evidence then confirms it, and
where the two disagree the evidence wins. **First row that matches wins:**

| Evidence on the node | Status | Starts at |
|---|---|---|
| PR merged | `landed` | nothing — counts as delivered. If a successor is still based on its branch, say `/repoint` or `/fix-pr-stack` is needed; this command does not do it |
| A row is ⛔ | `halted:<row>` | nothing, unless this invocation carries the developer's answer to that halt — then that row's stage |
| Every `[wf]` row ✅ / ➖ (changeset wrapped from `1-WIP/`), no legacy row after Wrap left in the PR body, PR ready, every check terminal-green and every thread addressed **on the current head SHA**, `#skipreview` approval standing | `done` | nothing |
| Every row is done (Wrap ✅, PR ready) but a legacy row after Wrap is still in the PR body, a check is red or running, a thread is open, or no `#skipreview` approval stands on the head — post-wrap state, read from GitHub | `F` | `[F]` |
| First open row is the Wrap row; the Green row is ✅ and its commits are pushed | `W` | `[W]` |
| First open row is the Green row; commits exist after the red commit, tests **still red** | `G:resume` | `[G]`, told what exists |
| First open row is the Green row; nothing after the red commit | `G` | `[G]` |
| First open row is a planning row (Plan, Red, Preservation tests), its PR exists | `plan:pass2` | pass 2 for this node (6a–6g) |
| No branch or PR yet | `plan:pass1` | `/plan-pr-stack` from the step that creates it |

**The Green row** is the row that implements the node — *Green*, *Restructure*, *Migrate* or
*Implement* in the presets, whatever its command (`/green`, `/green-100`, `/code-restructuring`,
`/plan-tdd-migration`). A changeset with no `[wf]` rows is backfilled by the node's first row command
(step contract, step 2); the orchestrator derives the stage from the evidence alone and says so.

**"Tests green" comes from CI first.** A terminal-green test check on the head SHA is the evidence, and
it costs nothing. With no usable CI result (no run on that SHA, still running, only lint ran), probe
instead: create the node's ephemeral worktree (pipeline step 0) and run the commands in its changeset's
`## Verification` for the packages it owns. Keep that worktree if the node goes on to `[G]` or `[W]`;
remove it if the node turns out `done`. A node whose Green row reads ✅ but whose tests are red on the
head is `G:resume` — the evidence wins, and the report names the disagreement. A node with **commits
after the red commit but no CI and no probe result** is `G:resume`, never `W` — a green row that
finds nothing red halts, so a wrong `W` is cheaper than a wrong `G`, and a wrong guess in either
direction is not acceptable; probe.

A branch **pinned** by another worktree is `stopped:0` (somebody is working on it), exactly as in step 0.

### Step R3 — show the table, then dispatch

Print one table: node, PR, status, the evidence that decided it (a SHA, a check name, a thread count),
the complexity score, and the stage it starts at. Then run Dispatch as normal, with these changes:

- A node's **ledger row begins at its derived stage**, not at `queued`. `G:resume`, `W` and `F` rows
  start at that stage's subagent; a node ahead of the others never waits for them.
- A dependency counts as **delivered** when its Green row is ✅ — status `W`, `F`, `done` or `landed`.
- Each stage brief for a resumed node adds the facts the stage needs and says: **re-verify, do not
  redo.** A row that ended with TODOs open resumes at its first open TODO. `G:resume` gets the head SHA, the commits after red and the tests still failing, and builds on
  them. `W` re-runs its own validations rather than trusting that green was proven. An `[F]` with no
  `[W]` agent to continue is a **fresh** agent, sized by `[W]`'s row, that first reads the diff and the
  changeset.
- **Nodes with `plan:` statuses are planned first**, by the orchestrator, because pass 2 is
  bottom-up and runs in the planning worktree. The implementation pipelines of nodes already past
  red start alongside, as in the ordinary command — planning never waits on them and they never wait
  on it.
- If the stack already has its **sweep node**, it is an ordinary node with these statuses. If not, it is
  reserved and planned at the tail after the pipelines drain, as usual. The TODO gate lists only TODOs
  with no recorded decision; a TODO that already carries a `defer` consent line is not listed again,
  and the developer's answers carried by this invocation are applied first.
- Where the evidence is ambiguous (a probe that fails to run, a head that moved while reading), that
  node is not started: it goes in the final summary under **⛔ Needs you** with what was read.
  Every other node carries on. Do not stop to confirm the table.

The rest of the command — what the invocation decides, halts, the completion gate, the sweep — is
unchanged.

## Sizing every subagent — model and effort, always stated

**Every subagent this command starts gets an explicit `model` and an explicit `effort`.** No stage
runs on a default. The command's own instruction is what authorises passing `effort` on the Agent
call. The one exception is where effort cannot be set — an agent continued with `SendMessage` keeps the
effort it started with, and the Composer model on Muse has no effort knob — and there the ledger and
the announcement say `inherited` or `n/a`, not nothing.

**Haiku may be set up to `xhigh`.** Effort is how a small node on a small model gets enough depth;
reach for a larger model only after the effort ladder is spent.

**The input is the changeset's `**Complexity**: N/5` header line** (scored at planning, see
`pr-lifecycle/references/changeset.md` § Header Metadata, re-scored in the red commit). A changeset without one is scored
now from that rubric and the announcement says so. The orchestrator may move **one row** off the score
when the red commit contradicts it (far more failing tests, or more packages, than planned) — never
silently, and never more than one row.

Which column a row takes follows its place in the node's table: the **Green row** is `[G]`, the
**Wrap row** is `[W]`, and the post-wrap procedures — `/fix-pr` and `/yolo`'s Approve — are `[F]`;
they are not rows. A row the developer added is sized by its neighbours, and since Wrap is the last
row, it takes `[G]`'s.

| Complexity | `[G]` the Green row | `[W]` the Wrap row |
|---|---|---|
| **1** | Haiku · low | Sonnet · low |
| **2** | Haiku · medium | Sonnet · low |
| **3** | Haiku · high | Sonnet · medium |
| **4** | Haiku · xhigh | Opus · low |
| **5** | Sonnet · medium | Opus · medium |

- **`[G]` retry.** A stage that returns 🔴 because the model was out of its depth may be retried
  **once, one row up** (score 1 → 2 … 4 → Sonnet · medium). Sonnet · medium is the ceiling. A node that
  seems to want more has a boundary problem: the stage stops and says so rather than escalating
  silently. Record both attempts.
- **`[W]` raise.** `[W]`'s effective score is the complexity **+1** (cap 5) when `[G]` needed its
  retry, a file this PR pushed has to be decomposed (over 500 lines), or the code-issue gate found
  added issues. Opus · medium is the ceiling.
- **`[F]` continues `[W]`'s agent**, so it keeps `[W]`'s model and effort. A fresh `[F]` (the original
  is gone — context exhausted, restart, or a reopened layer) uses `[W]`'s row for the node.
- **Composer mode (`#composer-subagent`, `#coder`) driver:** Sonnet · low, passed explicitly. Muse: Composer, effort `n/a`.

### Announce the choice — every time a subagent starts

Before each Agent call, in the orchestrator's own text, **one line to the user** saying what was chosen
and why. One line per subagent, never batched, never skipped because several nodes dispatch at once.
It names the node, the stage, the model · effort, and the **reason** — the complexity score and the
signals behind it:

```
▶ n3 #2402 [G] row 3 /green → haiku · xhigh — complexity 4/5 (two packages, proto change); first attempt
▶ n1 #2401 [W] row 4 /pr-wrap → sonnet · medium — complexity 2/5 raised by 1: [G] needed its retry
↗ n3 #2402 [G] retry → sonnet · medium — haiku · xhigh stopped 🔴 out of its depth on the proto seam
▶ n3 #2402 [F] /fix-pr + Approve → continues [W]'s agent (sonnet · medium, effort inherited) — round 1
▶ n5 #2406 [G] row 3 /green → haiku · high — complexity 3/5 moved up one row: red commit has 14 failing tests, plan said 6
▶ n2 #2404 [W] row 4 /pr-wrap → sonnet · low — complexity 1/5; resuming at W, evidence: CI green on 3fa9c1e
```

The same model, effort and reason go in the ledger row. A user who disagrees can say so on the spot;
the next start uses their answer.

## What stays interactive — one interview, then `#yolo`

The planning interview is the user's input, and it is the **only** time this command asks. Ask
**ahead**: the interview covers `/plan-pr-stack` Step 1 (requirements, the kind per slice, the
decomposition question with the concurrency cap, the host and the sweep node) **and every question
the run can foresee** asking later. That means a ground-softening restructure you would propose, a
routing that departs from the kind matrix, any slice that can only reach V4 verification (its
consent cannot be deferred), naming the user sees, an API shape between nodes, and which of two
behaviours wins (`behaviour-modifiers/references/yolo.md` § 1, *Ask everything you can ahead of
time*).

**Close the interview by asking for acceptance.** Show the settled answers in one block, one line
per decision, and ask the developer to accept or correct them. That is the last question. From the
moment they accept, the run is under **`#yolo`**:

- No further question to the developer, from the orchestrator or any stage. Each one is a deferred
  answer (`deferred-work` skill, `references/deferred-answer-record.md`).
- The orchestrator's own questions during pass 1, pass 2 and the sweep's planning have no
  supervisor. It picks its recommendation and records it.
- A stage's question is relayed to the orchestrator (*Questions from a stage*, below).
- Every tool output is bounded (`behaviour-modifiers/references/yolo.md` § 3), in the orchestrator and in
  every stage.
- Halts that ask for the developer's word stay halts: a deferral of planned scope, the TODO gate,
  V4 consent the interview did not settle.

With `#ask` in the request, the questions after acceptance go to the developer instead, batched
(`behaviour-modifiers/references/yolo.md` § *`#ask`*).

Each node's guardrail is verified in pass 2's 6e and listed in the final summary under **Decided
without review**. A pipeline starts on a node whose guardrail rows are ✅. A guardrail that would
not hold has already halted that node ⛔.

### Questions from a stage — the orchestrator supervises

A stage that would ask writes the deferred-answer record, finishes and pushes whatever does not
depend on the answer, and reports `❓ question` with the record's path. Its ledger row reads
`<stage>:question`. A `composer-subagent` driver relays its Muse agent's question the same way
and never answers it. The orchestrator then:

1. **Reads the record** and decides with what the stage cannot see: the developer's interview
   answers, the other nodes' changesets and PR Stack blocks. It decides **Answered** (one of the stage's
   options) or **Refined** (options rewritten, its own recommendation picked).
2. **Announces it** in one line, like a stage start:
   `❓ n3 #2402 [G] caption-store → refined: c) sidecar file — n5 reads the same store`.
3. **Continues the same agent** with `SendMessage`, carrying the *Supervisor review* section
   verbatim. The stage pastes it into the record, commits it with the work that follows, and carries
   on. The asked and the reviewed versions both stay in the record.
4. When the same question reaches it from **several nodes**, it answers once and sends that answer
   to each of them, each record citing the first.

A question never stops pass 2 or another node. Only the asking node waits, and its dependents wait
as they would for its `[G]`.

## Hooks into pass 2

**Hook 1 — after 6g, once the planning worktree has left PRₖ.** The branch is pinned only while it
is checked out here, so the order is: finish 6g for PRₖ → `git checkout` PRₖ₊₁ (its 6a), or, for the
last node, Step 7's restore of `$ORIGINAL_BRANCH` → *then* run the **dispatch** below. Never create
the worktree for PRₖ while this worktree still has it checked out; `git worktree add` refuses, and
the workaround (`--force`, detaching) is the pinning problem `/plan-pr-stack` Step 4a exists to avoid.

**Hook 2 — whenever a pipeline's `[G]` stage reports green.** That can unblock nodes whose red commit
is already pushed. Run the dispatch again. It also re-runs after every pipeline finishes, to refill
the concurrency cap.

### Dispatch — which nodes start

A node is **ready** when all of these hold:

1. Its planning `[wf]` rows are ✅ and commit 2 is pushed.
2. It has no **started** pipeline: its ledger row is absent, `queued` or `blocked:n<j>`. A row in
   `G`, `W`, `F`, `done` or `stopped` is excluded. (In resume mode a row is created at the node's
   derived stage — see *Step R3*.) `queued` and `blocked` rows are **re-evaluated by
   every dispatch** and move to `G` the moment rules 1 and 3–5 hold, which is how a node waiting for a
   free slot or a resumed blocker ever starts.
3. **Every node it depends on has delivered its Green row.** The dependencies are the edges its
   changeset's `### Green wave` lists under what it waits on, in node numbers — the committed source,
   current after 6g (6f can add or drop one). **Before each dispatch, compare them with `gh stack view` and the PR bodies' `## Stack` blocks.** On a mismatch, correct the changeset's Stack Context and PR body's Stack block now (`pr-stack` skill § *No epic issue — topology and waves*), instead of waiting for Step 6h. Branch-line
   neighbours that are not dependencies do not count. A dependency has delivered when its Green row
   is ✅ in its committed changeset with the head pushed. **While any dependency's `[G]` is queued, in progress, or being
   retried, this node waits, even with a free slot and a pushed red commit.** Its worktree is not
   created, and no subagent starts. Wave 1 nodes have no dependencies. `/green` would stop at its
   ancestor-functionality gate (`green.md` 0b) anyway, so an early start is only a wasted worktree.
4. No node it needs is halted (⛔ row, 🔴 report). Mark it **blocked**, not failed, and say which
   node blocks it.
5. The running count is below the **concurrency cap**.

**Concurrency cap: 3**, unless the user set another number in this request. Each worktree is ~7 GB
once `uv sync --group dev` and the package builds have run, and every green PR that lands makes the layers
above it stale (`plan-pr-stack` Step 10). Say the cap in the Step 1 decomposition question so the
user can change it before anything is created — it is part of that interview question. Say there too that a **sweep node** will be appended
at the tail (see *The sweep node*), with its scope unknown until the stack has been implemented. Nodes that are ready beyond the cap queue in
stack order, blockers first.

**Every kind runs the pipeline; its rows say what that means.** A Feature or Bug fix node's Green
row is `/green`, a Refactor node's is `/code-restructuring`, a mechanical migration's is
`/plan-tdd-migration`'s Migrate row, an infra node's `/green` against its V3 command, a rebalance's
`/green-100` — whatever the preset wrote and any override replaced. The row's own command decides
whether it can run, and halts ⛔ when it cannot (nothing red, an ancestor stub); the pipeline does
not second-guess it. Its dependents then wait as `blocked:n<j>`, and the final summary says so.

### Ledger

Keep one file in the scratchpad: `yolo-pr-stack-<slug>.md`, one row per node — branch, PR number,
worktree path, stage (`queued · G · W · F · done · stopped:<stage> · blocked:n<j>`), the
`[wf]` row it is on, the complexity
score, **model · effort used per stage with the reason** (both attempts, when retried), head SHA at the
last report. Update it on every report. It is the orchestrator's memory
across a context reset: after one, re-derive stages from `git worktree list`, the branches' pushed
state, each node's `[wf]` rows and each PR's checks, never restart a node whose row is past `queued`/`blocked`. The ledger is not committed.

## The pipeline, per ready node

### 0 — Ephemeral worktree

```bash
W="$(dirname "$PWD")/yolo-<slug>-n<k>"        # a sibling of the planning worktree
git fetch origin pr-<k>-<slug>
git worktree add "$W" pr-<k>-<slug>            # must succeed: nothing pins the branch
git -C "$W" status --porcelain | grep -v '^?? '   # must be empty
git -C "$W" rev-list --count origin/pr-<k>-<slug>..HEAD   # must be 0
(cd "$W" && uv sync --group dev && uv run mypy)   # each package in scope; never a full-repo build
```

If the add is refused because the branch is pinned, **stop that node** and mark it `stopped:0` —
somebody is working on it. Do not `--force` and do not make a second copy.

### Binding a subagent to the worktree

The Agent tool has no working-directory parameter, and `isolation: "worktree"` would cut a fresh
branch, which is the opposite of what is wanted. Bind in the prompt, and say all of this:

- **First action:** `cd <W>` and confirm `git rev-parse --show-toplevel` is `<W>` and
  `git branch --show-current` is `pr-<k>-<slug>`. Stop if either differs.
- Every file path is absolute and under `<W>`. Every Bash call starts with `cd <W> &&`, because the
  shell may not persist. Never touch the planning worktree or any other worktree.
- Work **this branch only**: no `gh stack sync`, no `gh stack rebase`, no `gh stack submit`, no cascade
  rebase. `/pr-stack-rebase` in single mode is the only rebase. Never amend, never `--no-verify`.
- The branch is a stack member and a successor's base: **commit and push** before reporting.
- Run the rows named in the brief **as `/yolo` runs a row** (`.agents/commands/yolo.md` § *The
  loop*, steps 1–4): grep the rows before each row, run its command's file end to
  end with the row's tags, and confirm the row reads ✅ or ➖ in the committed rows (after the wrap,
  in the PR body, or the wrap commit's message until a PR exists, per the skill's step contract
  step 1) before the next. A row that halts ⛔ ends the
  stage. The halts listed in `yolo.md` § *Halts no invocation can pre-approve* apply unchanged.
- **Modifiers: `#yolo`** (plus any the request carries), on its own line in the brief
  (`behaviour-modifiers` skill § *Passing modifiers down*): never ask, record a question as a
  deferred answer and report `❓ question` instead of acting on it, and bound every tool output.
- Report in the format at the end of this file, and nothing else.

Fork-style context is not needed and costs tokens. Use a **fresh** subagent for `[G]` and a **fresh** one for `[W]` (stage `[F]` continues `[W]`'s agent, see below) with the brief
above, the PR number, the changeset path, and the rows to run. Do not paste the whole of this file.

### Stage G — the Green row

Run the node's **Green row** (and any ⬜ row before the Wrap row) in `<W>` — whatever command it
names: `/green`, `/green-100`, `/code-restructuring`, `/plan-tdd-migration`. On a stack branch the
row's command commits and pushes its work. Its halts end the stage: nothing red, a planned-scope
deferral, a stack gate (ancestor functionality, a leak in `origin/<base>..HEAD`, unplanned
deletions), tests or type-check still red.

**Model and effort.** From the changeset's complexity score — *Sizing every subagent* above. Pass both
`model` and `effort` on the Agent call and announce the choice first.

### Stage W — the Wrap row

Start only when `[G]` reported ✅ and pushed. Run the node's **Wrap row** (`/pr-wrap`) in `<W>`. Under
the step contract it applies every cleanup, Minor included, decomposes files this PR pushed over 500
lines, solves every code issue this PR added, decides each TODO and lists it in its summary, wraps
the docs, retitles, and marks the draft ready — without asking.

**Stack-shared files are the one thing the brief adds.** `/pr-wrap` step 4 splits a file that other
stack PRs also modify and then cascades a rebase over the whole tail, each layer in its own
worktree. That cannot run here — sibling pipelines have those branches pinned. So the brief
overrides it: **do not split a stack-shared file**; record it in the file's
`<package-dir>/docs/code-issues/` record (its history row: left for the sweep node) and list it in
the report. The sweep node splits it later. Every other file is decomposed now.

**An oversized, non-fluent test file** a node grew is decided by that node's share of it, as under
`/yolo` (`.agents/skills/testing/references/fluent-style.md` § *When a PR grows an oversized,
non-fluent test file*): ≥ one third of the legacy lines → `[W]` migrates it in the node (unless it is
stack-shared — then it is the sweep's); below → a `**Priority:** 1` record whose history row names
the sweep node.

**Model and effort.** `[W]`'s row for the node's complexity, raised by one when the *Sizing* rule says so —
pass both `model` and `effort`, announce first.

### Stage F — post-wrap: `/fix-pr`, then Approve

Start only when `[W]` reported ✅. **Continue `[W]`'s own agent** with `SendMessage` (load it with
`ToolSearch("select:SendMessage")` if its schema is not loaded) — do not spawn a new one. Same context, same conversation: it already
holds the diff, the changeset and every cleanup decision, which is what makes its answers to review
comments accurate, and it is already bound to `<W>`. The message names the procedures and the stop
conditions below. Muse: resume the same subagent the same way. Run, in `<W>`, the post-wrap `/fix-pr`
(Wrap step 9 already readied the PR; nothing here has a row or a TODO) **repeatedly**, until both
hold on the **current head SHA**:

- every check is terminal and passing, and
- every review thread is addressed — the main (non-nit) comments fixed or answered with evidence, per
  `fix-pr.md`'s reaction protocol.

One `/fix-pr` run already polls running checks and fixes failures as they appear, so the loop is for
what it hands back: a new push that restarts CI, a new comment, a bot re-review. Between rounds the
subagent re-reads the PR state; it does not sleep-poll. Its halts end the loop with a 🔴, and it
**never** retriggers a flaky check unprompted:

- a flaky or infra failure that needs a retrigger → ⛔ naming the retrigger;
- the same check failing on a **third** consecutive push → ⛔;
- a fix for one failure that keeps causing another → ⛔;
- **a round cap of 5.** A fifth round with the PR still not green is a ⛔, not a sixth try.

Then **`/yolo`'s Approve** (`yolo.md` § *Approve*): wait out the checks on the head SHA,
sweep the threads once more, check every gate line, post `#skipreview`, observe `APPROVED`. A stack
member staying `BLOCKED` until its predecessors land is expected. **No Land and no merge here**:
a registered stack lands only through `merge-async` (`pr-stack` golden rule 3), with
`/merge-pr-stack`, never through `#automerge` or a regular merge, and never past a failing check —
optional (non-required) ones included; `[F]` treats a red optional check as a red check.

**Model and effort.** Whatever `[W]`'s agent already runs — a continued agent cannot change either. So `[F]`
has `[W]`'s model and effort, and there is no escalation or de-escalation; the announcement says
`continues [W]'s agent` with those values. A check that keeps failing or a thread arguing a design
point is what the round cap and the halts are for: the stage stops and reports.
If the agent is no longer resumable (context exhausted, harness restarted), start a fresh agent on
`[W]`'s row for the node, with the same brief, announce it, and say so in the ledger.

### Models on Muse

The Haiku / Sonnet / Opus tables above are the **Claude Code** choice. On **Muse**, stages **G**
(`/green`, or `/code-restructuring`) and **W** (`/pr-wrap`) run on the **Composer** model, for every
node whatever its size — Muse has no per-node model ladder to size against, so the complexity
rubric does not choose a model or effort there. Still announce each start, with the complexity score
and `effort n/a`. Stage **F** continues `[W]`'s agent, so it is Composer too. Binding to the worktree, the stage order and the halts
are identical on both harnesses. Record `composer` in the ledger as the model for G, W and F.

### Composer mode (`#composer-subagent`, `#coder`)

When the user asks for it — `#composer-subagent` (or `#composer`), `#coder`, or in words ("let
Composer do it", "run it on coder") — every implementation stage is done by the Muse agent
(`agent -p`) on Composer, driven by a Claude Code subagent, through the **`composer-subagent` skill**
(`.agents/skills/composer-subagent/SKILL.md`). Read it first. `#coder` adds the **host**: the stages
run on a Coder workspace through the **`coder-remote` skill** (`.agents/skills/coder-remote/SKILL.md`),
and `#coder` implies `#composer-subagent`. **Only the implementation rows are offloaded: `[G]`
the Green row, `[W]` the Wrap row and `[F]`'s post-wrap `/fix-pr`.** Planning stays with the
orchestrator's own model: the interview, the decomposition question, pass 1, all of pass 2
(changesets, PRDs, the red commits with their failing tests, the 6e guardrail verification), the
sweep node's planning and the TODO gate — and so do Approve and Land, as in `/yolo`. A node reaches
Composer only after its planning rows are ✅, exactly as the default pipeline starts. The dispatch
rules, the ledger and the halts are unchanged: every stage takes the skill's **row consent**, so a
halt comes back as the node's ⛔ row, written, committed and pushed by the Muse agent. What changes is who runs each implementation stage, and where:

| | Default | `#composer-subagent` (host `local`) | `#coder` (host `<ws>`) |
|---|---|---|---|
| Step 0 worktree | `git worktree add` beside the planning worktree | the same | the orchestrator runs `coder-remote.sh worktree <ws> pr-<k>-<slug> yolo-<slug>-n<k>`, then the warm-up (`coder-remote` skill § *A worktree per unit of work*: `scripts/setup-worktree.sh`, `uv sync --group dev`, package builds) through `coder-remote.sh exec` in a background call |
| Who edits code | the stage subagent | the Muse agent, in the node's worktree | the Muse agent on the workspace |
| Stage subagent | does the stage, model by the rubric | a **driver**: Sonnet · low (effort passed explicitly), briefed with `composer-subagent` `references/driver-brief.md` and the stage's prompt from it | the same |
| Model doing the work | the G/W rubric | **Composer, every stage, every node** — `COMPOSER_MODEL` from `composer-agent.sh ensure <host>`. The rubric does not apply and there is no retry one step up | the same |
| `[F]` continues `[W]` | `SendMessage` to `[W]`'s agent | `SendMessage` to `[W]`'s **driver**, which resumes `[W]`'s **Muse session** (`--resume <SESSION_ID>`, same name `yolo-<slug>-n<k>-W`) — the same conversation on both sides. `[G]` is its own session, `yolo-<slug>-n<k>-G` | the same |
| Step 3 removal | `git worktree remove` | the same | `coder-remote.sh remove-worktree <ws> <dir>` |

**The orchestrator readies the host before the first dispatch**, and says the host and
`COMPOSER_MODEL` in the decomposition question next to the concurrency cap. Locally:
`composer-agent.sh ensure local`, guiding the user through a missing agent CLI or login
(`composer-subagent` § *Make the host ready*). On Coder: `coder-remote.sh ensure <ws>`, then
`composer-agent.sh ensure <ws>`, handling the login stops (exit 10/11: tell the user to
`coder ssh <ws>` and log in, then wait), and `coder schedule extend <ws> 8h`. The cap still applies on
both: the workspace has the disk for more, but every green PR still makes the layers above it stale.

**Restarts are the orchestrator's.** A host stop or reboot kills a turn; the driver's next `wait`
reports `RUN_EXIT=16` and it resumes the session itself. On Coder the agent runs in tmux, so a
dropped connection costs nothing, and a driver that reports `🔴 transport-lost` (the workspace is
down) is *paused*, not stopped: its ledger row keeps its stage with `:paused`. The orchestrator runs
`ensure` once for the outage, re-verifies each paused worktree with `coder-remote.sh worktree`, and
`SendMessage`s each paused driver to resume its session. A transport loss never counts against the
round cap or the turn cap, and never escalates.

Add per row in the ledger: host, worktree path, and per stage the run name and Muse `SESSION_ID`.
The stream lives on the host (`~/.composer-runs/<name>/stream.jsonl`), so after a context reset
`composer-agent.sh summary <host> <name>` re-derives a stage's state. A `🔴 stopped` node keeps its
worktree, local or remote.

### 3 — Green: remove the worktree

The node is done when stage F ends with the green condition above and its Approve observed `APPROVED`. Then, from the **orchestrator**:

```bash
git -C "$W" status --porcelain | grep -v '^?? '            # must be empty — untracked build artifacts are expected
git -C "$W" rev-list --count origin/pr-<k>-<slug>..HEAD    # must be 0 — nothing unpushed
git worktree remove --force "$W" && git worktree prune
```

If anything is uncommitted or unpushed, do not remove: push it, or use `/abandon-worktree`. **Never
delete the branch** — it is the PR, and successors are based on it. Mark the ledger row `done`, then
run the dispatch again.

A **stopped** node keeps its worktree: it holds the diagnosis context, and the developer's answer
to its ⛔ row resumes it there. Say where it is.

## The completion gate, with pipelines running

`/plan-pr-stack` Step 7 restores `$ORIGINAL_BRANCH` as usual — that is Hook 1 for the last node. Step 8
(the cascade `/pr-stack-rebase from #1 to #n`) needs **every stack branch free**, and a running
pipeline pins its own. So:

1. Restore `$ORIGINAL_BRANCH` (Step 7). Report pass 2 as finished **and the pipelines as running**.
2. **Wait for the pipelines to drain** — every ledger row `done`, `stopped` or `blocked`. The
   orchestrator is notified on each background subagent's completion; it does not poll in a loop.
3. Run Step 8's cascade over whatever has no pinned branch. Greens moved the stack, so *"every layer
   already current"* is **not** the expected answer here, and a rebased layer is not a finding to
   alarm on — but a layer whose rebase changes its tests or build state is. Report each layer.
4. A `stopped` node keeps its worktree and therefore its branch pinned: the cascade stops **at that
   layer** and reports it. Do not `--force` around it.
5. **A rebased layer is not done until its new head is green.** Any layer whose head the cascade
   changed — or whose base moved after its own `[F]` finished, because a predecessor pushed during
   `[W]` or `[F]` — is **reopened**: set its ledger status back to `F`, re-create its worktree (step 0), and run
   `[F]` again — `/fix-pr` and Approve, since the force-push dismissed the approval — with a fresh agent on `[W]`'s row for that node (the original one is gone with its worktree), announced like any start, until
   the green condition holds on the new head, then remove the worktree again. Cascade first, then
   reopen, bottom-up, so a layer is not re-run twice. The final report lists every reopened layer.
6. **Sweep.** With every layer green, run *The sweep node*: collect, plan, run its pipeline, then the
   TODO gate. The command is not finished until the gate has an answer for every open TODO; until it
   does, the stack is halted there. A `continue` answer adds nodes, which return to this gate when
   they are green.
7. **Report the stack ready** — landing is *Landing*, below.

## The sweep node — no new code issue leaves this stack

Planning, implementing and wrapping a stack leaves debris: `docs/code-issues/` records that
`/pr-wrap` added or reopened, stack-shared files it declined to split (above), and TODOs recorded
under `<package-dir>/docs/todo/`. `/yolo-pr-stack` ends by planning **one extra node at the tail**
whose job is to pay all of it down. **No code issue the stack added or reopened may exit the stack.**
A TODO may, but only by the developer's decision.

The node's scope cannot be known in pass 1, so it is **reserved** at the decomposition question and
**planned after the pipelines drain** (completion gate step 3, after the cascade).

### Collect

From the orchestrator, against the stack's tail, once every other ledger row is `done`:

```bash
mb="$(git merge-base origin/master origin/pr-<N>-<slug>)"
git diff --name-only --diff-filter=AM "$mb"..origin/pr-<N>-<slug> -- '*/docs/todo/*.md' '*/docs/code-issues/*.md'
```

Then run `/analyze-code-issues` on every package the stack touched and diff its findings against the
records at `$mb`: a finding that is not in the base records, or whose measurement got worse, is
**added or reopened by this stack** even if no `/pr-wrap` recorded it. Pre-existing records the stack
did not touch are out of scope. The list is the sweep's backlog; put it in the ledger.

**`non-fluent-tests` records are in the backlog too** — the legacy suites the stack's nodes added
fluent tests to, which each `/pr-wrap` attributed pre-existing and left for the sweep. This is the Boy
Scout rule at the tail: the sweep closes every one of them, and it **may rewrite any other test file
the stack touched** — whole files, not only the suites a record names — where that file shares
builders, matchers or drivers with one being migrated, or scores below 8 on the rubric
(`.agents/skills/testing/references/fluent-style.md`). List those extra files in the ledger with
their before-score. **Oversized test files go first** — every `**Priority:** 1` record, and any
test file the stack touched that is ≥ 500 lines and below 8: the sweep migrates them before anything
else in its backlog, and migrates before it splits (`fluent-style.md` § *Oversized test files come
first*). A stack-shared test file `[W]` declined to split is one of these.

If any node is `stopped`, `blocked` or `halted`, the backlog is incomplete. The stack **halts at the
sweep**: end the turn with the summary, and under **⛔ Needs you** the options — a) sweep what exists
now, b) wait for the halted nodes. Never sweep silently over a partial stack. The answer arrives as a
re-invocation (resume mode).

### Plan

A tail node via `/add-to-pr-stack`, kind **Refactor** (`refactor(...)`), planned like any Refactor
node: changeset (with its `Complexity` score — scored from the backlog's size, since it sizes the sweep's own implementer) with `## Verification` (V2, a recorded baseline of the suites covering the touched
code — green before and after), `## Stack Context` naming every other node as an inherited
dependency, a `plan.jsonl` per `code-restructuring` Steps 1–6, discovery, **no PRD**. The changeset
lists each backlog item by record path and the intent that closes it. It also takes every
stack-shared file `[W]` declined to split — safe now, since nothing downstream shares it. Its
`## Workflow` is the **restructure** preset. 6e verifies its guardrail, as for any node; the red
commit is the plan and baseline. Its Green row (`/code-restructuring`) applies the plan and deletes
it in the same commit (`code-restructuring` step 8).

**`non-fluent-tests` records are never in that node.** A Refactor node expects a `plan.jsonl`, and a
fluent migration is a different kind (`.agents/skills/testing/references/fluent-style.md` §
*Migrating a suite*). They go to a **second tail node**, a **Test-style migration**
(`Type: Test Style` · `Behaviour: preserves`, `test(...)`, preset **test-style**), appended
**before** the restructure sweep node — a non-fluent test file is migrated before it is split, and
that node splits stack-shared files — or the only sweep node when the backlog holds nothing else. Its changeset's
V2 `## Verification` carries each suite's before-state (titles, count, coverage, fluent score with
per-test rows); it has **no `plan.jsonl`**; its pass-2 commit is that before-state (6c-quater); and
its implementation row is **Migrate** via `/green` (`/green` step 0.9) — test files only, whatever
toolkit fits. Run, `[W]` and the TODO gate below apply to both nodes.

A backlog item that **no restructure can close** is not forced into the plan: a TODO that is really
deferred feature work, a behaviour change, or something blocked on a named external. It goes to the
**TODO gate** below instead. A code issue is never one of those; if a code issue seems to need new
behaviour, split that behaviour out as its own TODO and still fix the issue.

### Run

The ordinary pipeline over its rows: `[G]` `/code-restructuring`, `[W]` `/pr-wrap`, `[F]` `/fix-pr`
and Approve, with the model rubric above. Two additions:

- `[G]` for the Migrate row runs `/green` on the test-style contract: same tests green, every
  behaviour still asserted, coverage not lower, each migrated suite ≥ 8.
- `[W]` re-measures with `/analyze-code-issues`. The sweep node must add **no** code issue and must
  close **every** code issue in its backlog (record deleted by the commit that resolves it, per
  `deferred-work`). Anything left over halts the Wrap row ⛔, not a TODO. Splitting a file is not an escape:
  the sweep node is where stack-shared files get split.
- Resolved TODOs are deleted by the commit that resolves them. TODOs the sweep node itself would
  add are not allowed; it either does the work or halts.

### TODO gate — a halt, and the developer decides

After the sweep node is green, collect the TODOs **still open that the stack added** (the same diff
as above, minus what the sweep deleted). Each Wrap row already decided a disposition per TODO and
listed it in its summary; this is the one place the stack's deferrals are shown whole, and the
decision that lets a TODO leave the stack is the developer's:

```
### TODOs this stack leaves open
| # | TODO file | Packages | Why it was not done | Recommendation |
|---|-----------|----------|---------------------|----------------|
| 1 | <package-dir>/docs/todo/2026-…-….md | … | … | continue the stack / defer |
```

A non-empty table **halts the stack**: the final summary carries it under **⛔ Needs you**, each row
with two options — **continue** (add a node for it via `/add-to-pr-stack` — plan it as the kind it
really is — and run it through the pipeline, then show the gate again for whatever remains) or
**defer** (record the consent in the TODO file per `deferred-work`, and leave it) — and the turn
ends. The developer answers by invoking `/yolo-pr-stack` again on the stack with a decision per row;
resume mode applies them. An empty table is stated in one line: *"This stack leaves no open TODOs."*
Never defer on the developer's behalf, and never report the stack finished with the table
unanswered.

## Landing — not from this command

**This command does not merge.** `#automerge` in the request is not merge intent here: once the TODO
gate has an answer for every row, report the stack as ready and point at `/merge-pr-stack`, which
lands it bottom-up through `merge-async` — the only path a registered stack's PRs accept.

## What invoking `/yolo-pr-stack` decides

For every node's pipeline, on that node's branch only: run its `## Workflow` rows after the planning
rows, unattended, exactly as their commands run under the step contract; then its post-wrap `/fix-pr`; post `#skipreview` through
each node's Approve; remove the ephemeral worktree with `git worktree remove --force` once step
3's tracked-changes and unpushed checks pass — the force is for the untracked build artifacts only.
Every halt in `yolo.md` § *Halts no invocation can pre-approve* still halts that node, and a halt
never blocks pass 2 — only the nodes that need the halted one.

Also decided: appending the sweep node with `/add-to-pr-stack` and running its pipeline. Not
decided: deferring a TODO (only the developer's answer to the TODO-gate halt records one) and adding
a node for a TODO without that answer.

Not decided, so not done: any merge, `#automerge` or `merge-async`, `gh stack unstack`, `--force` on a push,
on `git worktree add` or on a rebase (the one exception is `git worktree remove --force` in step 3),
a retrigger of a flaky check, editing another node's branch, and the cascade over pinned branches.

## Subagent report format

```
## <stage> — n<k> #<PR>: ✅ done | 🔴 halted | ❓ question
rows: <k step ✅ evidence> · … (as committed in its [wf] lines)
head: <sha> (pushed: yes/no)
did: <≤5 bullets>
decided without review: <each row summary's Decided without review, one line each>
halted because: <only when 🔴 — the ⛔ row, its Result, and the options it lists>
question: <only when ❓ — the deferred-answer record's path; nothing built on it yet>
deferred answers: <every record this stage wrote or updated: path · kind · decision · asker | supervisor>
files left for a human: <stack-shared files not split, TODOs left, anything else>
```

The orchestrator reads only this, so a stage that finishes with "it seems to work" has not finished.

## Final report

The summary from the `pr-lifecycle` skill § *Summary*, for the whole stack: `/plan-pr-stack` Step 9's content
(including every node's guardrail under **Decided without review**), plus every stage report's
**Decided without review** lines, per node, plus the **pipeline table**, one row per node:

```
n1 #2401  ✅ done      G haiku·low  W+F sonnet·low (2 fix rounds)  worktree removed
n2 #2404  ✅ done      G sonnet·low W+F sonnet·med (1 fix round)   worktree removed
n3 #2402  🔴 stopped:F G sonnet·med W+F opus·low  — F: third push failing `test:it`   worktree kept at <path>
n4 #2403  ⏸ blocked:n3 (needs n3's behaviour)      never started
```

Then **Deferred answers**: one table for the whole run (`behaviour-modifiers/references/yolo.md`
§ 4), the orchestrator's own records and every stage's, each with the stage's pick and the
orchestrator's review. Then every 🔴 with its ⛔ row and options under **⛔ Needs you**, every **blocked** node and what
unblocks it, the stack-shared files `[W]` declined to split, and the cascade verdict per layer. The
**sweep node** has its own row, then the backlog it took (code issues closed, TODOs closed) and the
TODO gate's table — under **⛔ Needs you** while unanswered, with the developer's answer per row once
given, and the pointer to `/merge-pr-stack` for landing. A node that is not ✅ is stated plainly — no
pipeline is "mostly done".

## Rules

- **Run `/plan-pr-stack` whole.** This command adds a mode; it removes nothing. 6e still verifies
  every node's guardrail, and a pipeline starts only after its node's planning rows are ✅ and
  commit 2 is pushed.
- **Each node's `[wf]` rows are what runs.** Its next row (the skill's grep) is its stage; ⛔ is a
  halted node. Re-grep before every row; a developer edit to the rows is honoured.
- **A worktree is created only after the planning worktree has left that branch** — never before 6g's
  checkout of the next node or Step 7's restore.
- **A node starts only when every dependency's Green row is ✅; one dependency still in `[G]`
  holds it back.** Wave 1 first; later waves as
  their predecessors' `[G]` stage reports, not when their red commit lands.
- **Stages run in row order: G → W → F.** `[G]` and `[W]` are separate fresh subagents; `[F]` **continues
  `[W]`'s agent** rather than starting another. The next stage starts on the previous one's
  report, never in parallel with it. The orchestrator chains them; subagents do not spawn the next.
- **Model and effort by the changeset's complexity score, always both.** On Claude Code `[G]` runs
  Haiku (low → xhigh) up to Sonnet · medium, `[W]` Sonnet · low up to Opus · medium, `[F]` inherits
  `[W]`'s agent; on Muse every stage uses Composer; in **Composer mode** (`#composer-subagent`,
  or `#coder` for a Coder workspace) every stage's work runs on the Muse agent's Composer, driven
  by a Sonnet · low subagent. **Announce one line to the user at each subagent start** (node, stage,
  model · effort, why) and record it in the ledger.
- **Resume reads the rows, then the evidence.** A stack that is partly done restarts each node at its first
  unfinished row; nothing done is redone, nothing unseen is trusted, and the status table shows the
  evidence behind every row.
- **Composer mode only on request** — the user's words, `#composer-subagent` or `#coder`. The
  orchestrator owns the host (Muse agent install and login guidance, warm-up, restarts); drivers
  never start, stop or provision it.
- **Bind by prompt, verify by git.** A subagent confirms its toplevel and branch before writing, and
  the orchestrator confirms the head SHA is pushed before it starts the next stage.
- **Concurrency cap 3** by default, stated at the decomposition question.
- **A halt is local.** It stops that node and blocks only the nodes that need it. It keeps its
  worktree. Pass 2 and every unrelated pipeline carry on.
- **Remove a worktree only when its PR is green and nothing is unpushed.** Never delete a branch.
- **No cascade, no `gh stack sync` / `rebase` from a pipeline worktree**, and no merge or `#automerge` from
  anywhere in this command; `#skipreview` only through a node's Approve. `#automerge` in the request is not
  merge intent here: report the stack as ready and point at `/merge-pr-stack`, which lands it with
  `merge-async`.
- **Reserve a sweep node, plan it after the pipelines drain.** No code issue the stack added or
  reopened exits it; the sweep node closes them all or halts. Open TODOs halt the stack for the
  developer, and each one is *continue* or *defer* — never silently left, never deferred for them.
- **One interview, then `#yolo`.** Ask everything foreseeable up front and close with acceptance.
  After that, every question is a deferred answer, a stage's question is relayed to the
  orchestrator, and both versions are kept in the record.
- Never use `--no-verify`. Never amend.

## Related

**Commands**: `/plan-pr-stack` (the whole of planning and both passes; writes each node's `## Workflow`; scores each changeset's `Complexity`), `/yolo`
(the single-branch runner whose loop, halts and Approve this reuses), `/next`, `/green`,
`/code-restructuring`, `/pr-wrap`, `/fix-pr`, `/pr-stack-rebase`, `/add-to-pr-stack`, `/analyze-code-issues`, `/abandon-worktree`, `/fix-pr-stack`, `/merge-pr-stack`
**References**: `.agents/skills/pr-lifecycle/SKILL.md` (the `[wf]` rows, presets, step contract, halts, summary)
**Skills**: `behaviour-modifiers` (`#yolo`, `#ask`, the relay), `composer-subagent` (Composer mode), `coder-remote` (its Coder host), `deferred-work` (record formats, the bar for deferring), `pr-stack` (`.agents/skills/pr-stack/SKILL.md`) — § *Delete a temporary worktree as soon as
its branch is pushed*, § *Green waves*
