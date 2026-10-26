# Planning Step 2b — cross-checking both records

Planning reads the TODO and code-issue records **after** the code analysis, once you know which files
and modules the change touches, and **before** the changeset is written. Discovering an item during
`/green` is late: by then the only choices are to work around it, silently make it worse, or stop.

Called by `/plan-red`, `/plan-ft-dev`, `/plan-pr-stack` and `/add-to-pr-stack`, via
[`planning-phase.md`](../../planning/references/planning-phase.md) Step 2b.

Snippets below use `PKG` for a package **directory** (`mapping-pipeline/mapping-pipeline-server`). Both records
live in that package's docs: `$PKG/docs/todo/` and `$PKG/docs/code-issues/`.

## Scan

```bash
PKG=mapping-pipeline/mapping-pipeline-server          # one per package in scope

# 1. This package's own records — the listing is the index
ls "$PKG/docs/todo/" | sort -r | head -30
grep -rL 'Status:\*\* Resolved' "$PKG/docs/todo/" 2>/dev/null          # still open only
ls "$PKG/docs/code-issues/" 2>/dev/null
grep -rL 'Status:\*\* Resolved' "$PKG/docs/code-issues/" 2>/dev/null   # EVERY open issue, first
grep -rl 'Restructure:\*\* required' "$PKG/docs/code-issues/" 2>/dev/null | \
  xargs grep -L 'Status:\*\* Resolved'    # …of those, the ones needing a restructure

# 2. Records OWNED BY ANOTHER PACKAGE that name this one — REQUIRED, not optional.
#    A TODO lives under the package the work would land in, so a deferral that
#    constrains yours can sit in a sibling's docs. Step 1 cannot see it.
grep -rl -F 'surmap' */*/docs/todo/ 2>/dev/null | \
  xargs grep -L 'Status:\*\* Resolved'

# 3. Records against the files this change will edit, wherever they live
grep -rl 'src/services/<file-you-will-edit>.ts' */*/docs/code-issues/ 2>/dev/null
grep -rl -iE '(subasset|analyzer|pageNumber|<your-module>)' */*/docs/todo/ 2>/dev/null

# 4. Deferred answers still awaiting the developer's review — Technical in the package,
#    Product in the owning area (deferred-answer-record.md)
ls "$PKG/docs/deferred-answers/" docs/<area>/deferred-answers/ 2>/dev/null
grep -rl -F 'surmap' */*/docs/deferred-answers/ 2>/dev/null
```

**An open deferred answer is a decision the developer has not seen yet.** Its verdict goes under
`## Prerequisites` → `### Open Deferred Answers` (`pr-lifecycle/references/changeset.md` §2.5).
When the new change
would build further on its pick, the verdict is ⛔: a requirements question for the developer,
asked in this plan's interview, or, under `#yolo`, recorded as a new deferred answer that cites the
old one. The developer then reviews both together. Building on it silently makes an override more
expensive with every change.

**Step 2 is the one that gets skipped.** When both records lived in one flat directory a single
listing found everything; now a package's own directory is only *part* of what applies to it. The
`**Packages:**` line is what makes the cross-package grep work, so an item whose author omitted a
package is invisible here — if you find one, fix its `**Packages:**` line as you go.

**Enumerate every open issue before narrowing.** `Restructure: required` and a per-file grep are
*lenses* on the open set, not the set itself — a missing-tests or type-escape record in the path of
this change is a prerequisite too, and filtering it out of the scan means it never gets a verdict.

**A package with no `docs/code-issues/` directory has not been analyzed**, which is not the same
as clean. Name those packages in the changeset, and run `/analyze-code-issues` when the change lands
in code the analyzers would have something to say about (a large service, an untested path, a file
you are about to grow).

Read the **body** of every candidate, not the heading. A TODO's *why it could not be done* paragraph
and a code issue's *what would close it* section are what decide the verdict.

## Classify every hit

| Verdict | Meaning | Where it goes |
|---|---|---|
| ⛔ **Blocking** | the change cannot be implemented *correctly* without it | `## Prerequisites`, **and** a TODO under the row that clears it — it is work, not a note |
| ⚠ **During** | the change touches it, would make it worse, or must not re-introduce it | `## Prerequisites`, as a constraint on how the work is done |
| ℹ **Answered** | planning resolved an open question the item asks | `## Prerequisites` with the answer — and close the item at wrap |
| — **Unrelated** | same area, different concern | nothing. Do not pad the changeset |

**Blocking means correctness, not convenience.** The test: name the two or three ways to proceed
without it, and check whether each is *wrong* rather than annoying. A 700-line service you would
rather not read is not blocking. A service whose only extension point is a function no test enters,
where the change must alter that function's behaviour, is.

Record the verdict even when it is "considered, not fixed here". The value is that a reviewer sees the
item was weighed rather than missed.

## Right-size the fix

| Size and location | Shape |
|---|---|
| Small, inside this change's own files | do it here; say so in `## Prerequisites` |
| Small, in shared code | **a separate change that lands first.** On a **single PR** (`/plan-red`) that is a prerequisite PR off the trunk. On a **stack** (`/plan-pr-stack`) it is **its own stack node** (typically PR₁) — never a PR outside the stack this command is creating. Name it in `## Prerequisites` so nobody starts the dependent work before it exists |
| Large, or `Restructure: required` | its **own changeset** — a `Type: Refactor` restructure changeset, executed before green (below). In a stack, **its own node in that stack** |

⚠ **Never absorb a large restructure into a feature change.** It buries a reviewable diff under a
mechanical one, and no reviewer can then tell the behaviour change from the move. That is the whole
reason `/code-restructuring` plans its own changeset.

## The restructure prerequisite — planned in the changeset, executed before green

When the verdict is a restructure, the changeset carries it as an executable prerequisite and
`/green` (step 0.5) runs it **before** the first line of implementation. Implementing on top of a
structure you are about to change means writing the code twice and reviewing a diff that is both at
once.

In the feature changeset's `## Prerequisites`
([`pr-lifecycle/references/changeset.md`](../../pr-lifecycle/references/changeset.md) §2.5):

```markdown
### Restructure Prerequisite — executed BEFORE green

- `/code-restructuring` against `mapping-pipeline/mapping-pipeline-server` — tracked as the Green row's first TODO
  - **Code issues closed**: `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md`
  - **Restructure changeset**: `docs/<area>/1-WIP/YYYY-MM-DD-<name>-restructure.md` (`Type: Refactor`)
  - **Why before green**: this changeset's implementation lands inside `fillSessionFlow`; splitting it
    afterwards would re-touch every line the feature added
  - **Commit**: its own commit, before any implementation commit
```

Three contract points that are easy to get wrong:

1. **The baseline carve-out.** `/code-restructuring` step 1 demands a green baseline and calls a red
   one a stop. A changeset that has been through `/plan-red` *has* red tests by design. So the
   baseline here is **"green except this changeset's own planned red tests"** — list those tests by
   name in the restructure changeset's `## Baseline` as known-red, and require every other suite to
   match. Anything red that is not on that list is still a stop.
2. **The restructure rewrites this changeset's own red tests.** Their imports and paths move with
   everything else, mechanically, through the language service. That is expected and correct; it
   lands in the restructure commit, and the tests must still fail for the same reason afterwards —
   verify that, because a red test that stops failing during a restructure has been broken, not
   fixed.
3. **It stays behaviour-preserving.** The restructure implements nothing. If a seam turns out to need
   the feature's behaviour to exist first, that is a planning error: stop and re-sequence rather than
   sliding implementation into the restructure commit.

**Planning reserves the restructure changeset's path; it does not write the document.** That is
`/code-restructuring` step 4, which needs the seam analysis first. Naming the path here is what lets
`/green` find the work without re-deriving it.

## Softening the ground — a restructure you propose, not one a record asked for

The scan above finds debt somebody already wrote down. This section is the other source: **your own
reading of the code during Step 2**, when the structure as it stands would make the change you are
about to plan harder or riskier than it needs to be.

Suggest it. Do not decide it — a preparatory restructure spends the developer's review budget before
the feature has earned any, so it is theirs to approve.

### The signals

The strongest one is specific to how this repo works:

> **The acceptance-test step cannot write a clean failing test against the current shape**
> (`/plan-red` Step 8, `/plan-pr-stack` Step 6e — the step that writes the tests, whatever its number
> in the calling command). If expressing the
> acceptance test needs a mock of a mock, a private method reached through a cast, or a whole service
> constructed to exercise one branch — the ground needs softening. A test you cannot write cleanly
> now is a test that will be rewritten in `/green`, and a red phase built on a contorted seam
> specifies the contortion.

Others, in rough order of how often they are real:

| Signal | The restructure it implies |
|---|---|
| The change must alter a function **no test enters**, and there is no seam to test it through | `extract_method` at the boundary, so the new behaviour has a testable unit |
| A dependency the change needs to substitute is **constructed inline** | extract it to a parameter or a module boundary the test can inject at |
| The change adds a **fourth responsibility** to a file that already carries three, and the seam is obvious | `split_file` along the existing seam, *before* adding the fourth |
| The change touches a symbol whose **every caller** would otherwise be rewritten | move it and let a facade absorb the callers (Rust `reexport`; in TS/Python the facade line is written by the developer after apply) |
| Two nodes of a stack would both edit the same oversized file | not a per-node prerequisite — the systemic restructure node below |
| The change adds tests to a suite that is **not fluent** (an open `non-fluent-tests` record, or a quick score below 7 — below 8 for a file ≥ 500 lines, which is **Priority 1**: proposed first, recommended *do it*) | a **Test-style migration** of that suite — always its own PR below the first change that writes into it, never a Restructure Prerequisite, because it must not hold up that change's green ([`testing/references/fluent-style.md`](../../testing/references/fluent-style.md) § *Migrating a suite*) |

### The bar — justified by *this* change, or it is not a prerequisite

Four tests, and the first is the one that matters:

1. **Name the specific difficulty in this changeset that the restructure removes.** "The code would
   be nicer" is not a difficulty. "The acceptance test cannot reach `applyOperations` without
   constructing the whole service" is.
2. **It must be smaller than the change it enables.** A restructure that dwarfs its feature has
   stopped being preparation and become the work — replan it as its own changeset on its own merits,
   with the feature waiting or proceeding without it.
3. **It must be behaviour-preserving and expressible in the vocabulary.** Check the coverage table in
   `code-restructuring/references/plan-schema.md` before proposing: no operation moves a class
   member, and `extract_class` refuses statics, `super`, `#private` reads, `this` writes, accessors
   and decorated members. A seam the tools cannot reach is not a `/code-restructuring` job, and
   saying so is more useful than proposing one and retyping the code by hand.
4. **The blast radius is measured, not guessed.** Run `findReferences` over each symbol you would
   move and give the caller count. That number is the difference between a four-file diff and a
   forty-file one, and it belongs in the proposal rather than in the review.

### How to present it

One block per proposal, in the planning report, **before** the changeset is written:

```
🔧 Suggested restructure — soften the ground before implementing

  Difficulty it removes   The acceptance test for per-page fills cannot reach `fillPage` without
                          constructing SessionReplayService and its 6 collaborators; the test would
                          assert through a mock of a mock.
  Proposed               extract_method `fillPage` → `flow/page-filler.ts` (1 op)
                         move_symbol  `PageFillContext` → same module   (1 op)
  Blast radius           4 importers (findReferences); facade not needed — all 4 are in this package
  Cost                   ~1 commit, behaviour-preserving, baseline is the current suite
  If we skip it          the test asserts through 2 layers of doubles, and `/green` will almost
                         certainly rewrite it. Workable, but the red phase specifies the seam we
                         did not want.
  Recommendation         do it — it is 2 operations and it decides the shape of 5 acceptance tests.
```

Then **ask**. Do not fold an unapproved restructure into `## Prerequisites`, and do not start it.
During planning, before the changeset is written, this is an interview question and is asked in the
turn. When the signal only appears once a step is running — `/plan-red`'s Red row cannot write a
clean acceptance test — the step does not ask mid-turn: it halts its row ⛔ with this block in the
summary, and the developer's answer on re-invocation is the approval
(`.agents/skills/pr-lifecycle/SKILL.md` § *Halts*).

### If the user approves

It becomes an ordinary **Restructure Prerequisite** in `## Prerequisites` (above), with
`**Source:** planner judgment — <the difficulty>` instead of a code-issue path. Everything else is
identical: its own `Type: Refactor` changeset, `/green` step 0.5 runs it before any implementation,
its own commit, implements nothing.

### If the user declines

**Record the observation; do not let it evaporate**, and do not re-propose it next session as if it
were new:

- **Measurable** (an oversized file, an untested complex function) → run `/analyze-code-issues` on
  the package and file a proper code-issue record with numbers. That is the durable form, and the
  next planner's Step 2b will find it.
- **Not measurable** (a seam that is merely awkward) → a TODO with
  `**Category:** Future enhancement`. No consent needed — it was never in the changeset's scope.

Either way, note in the changeset's `## Decisions & Trade-offs` that the restructure was proposed and
declined, and what the change does instead. A reviewer reading a contorted test seam should be able
to see it was a decision rather than an oversight.

## A systemic restructure across a PR stack

Occasionally Step 2b finds an issue that is not one node's problem: the seam every node builds on, or
a file more than one node has to edit. **`/plan-pr-stack` has one shape: its own node in this
stack**, placed immediately before the first node that needs it (PR₁ when it is the ground the
whole stack builds on). There is no "prerequisite PR off the trunk" option here — that would be a
PR the planner created that is **not** in the stack. Landing it first is merge order, not a second
stack. The developer still approves whether to do the restructure; they do not choose a sibling PR
off `$TRUNK`.

**The restructure node does not block the planning of the nodes above it.** They are planned, stubbed
and red-tested against the structure **as it is today** — the pre-restructure structure. That is
deliberate: planning cannot wait for an execution that happens in `/green`, and the alternative
(planning against a structure nobody has produced yet) is guesswork.

The consequence is accepted up front: **when the restructure node greens, the nodes above it break.**
Their stubs move, their imports move, their red tests fail differently. That is fine and expected —
repairing them is later-stage work, not a planning defect. What makes it safe rather than chaotic:

- every affected node's changeset carries an **`## Inherited Restructure — expect rewrite`** section
  (template in the [`pr-stack`](../../pr-stack/SKILL.md) skill) naming the restructure node, what
  moves, and that the repair is that node's own follow-up commit;
- the restructure node's `/green` reports, per successor, what it moved under them;
- each successor's next `/pr-stack-rebase` surfaces the conflict, and its **repair is a new commit**
  in that node — never an amend of its planning or red commit, and never an edit to the restructure
  node from a successor branch;
- the successor's red tests must still be red **for their own missing implementation** after the
  repair. A test that went green in the repair was satisfied by the restructure, which means it was
  never testing this node's behaviour — raise it, do not pocket it.

## Carry the verdicts into the changeset

The `## Prerequisites` tables have four columns and two authors. **Planning fills `Item`, `Verdict`
and `Disposition`** — what the item is and what this changeset intends to do about it — and leaves
**`Outcome`** as `*(filled by /green)*`. `/green` step 3.5a fills it with what actually happened,
`/pr-wrap` step 7.5 refuses to wrap while any cell is still a placeholder, and
`/wrap-context-docs` step 7b acts on the column to close, narrow or confirm each record **before the
changeset is deleted**.

So write a `Disposition` that a later phase can be held to: "fixed here — see the Green row's TODOs" is checkable,
"consider addressing" is not.



Every relevant item ends up in `## Prerequisites` with a verdict, and a ⛔ blocking one also earns a
TODO under the row that clears it. Reference each record **by path in backticks, not a Markdown link** — the changeset
and the record are now both in the docs tree, so a link would resolve — but a code issue is renamed
when the symbol it names moves, and the link rots silently. A backticked repo-relative path reads as
the identifier it is.
