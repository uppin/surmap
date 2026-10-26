# Fluent style — the mandatory shape of every test an agent writes

Every test an agent **writes or rewrites** in this repo follows the
[`fluent-tests`](../../fluent-tests/SKILL.md) skill: three visible acts, a name that reads as a
sentence about behaviour, builders for data, matchers or drivers that state intent, one behaviour per
test. Load that skill and its framework reference (`references/python/pytest.md`) **before writing the first test** — it is the *how*. This file
is the repo's *contract* around it: when it applies, how a test is scored, what a non-fluent suite
becomes, and how a suite is migrated without holding up the work that found it.

`fluent-tests` lives in this repo's `.agents/skills/` and is read from there. **Never edit it to carry repo rules** — they go here.

## The mandate

| Situation | What is written |
|---|---|
| A new test file | fluent, every test |
| A new test in an **existing, non-fluent suite** | **still fluent.** The suite's style is not a precedent. Add the builder, matcher or driver the new test needs next to the suite (or in the package's testkit) rather than copying the suite's raw setup |
| A test this change **edits** (strengthened assertions, a reproduction tightened in place) | the edited test is brought to fluent as part of the edit — only that test, not its neighbours |
| The **rest** of a non-fluent suite | **left alone** by this change. Rewriting it is a migration (§ *Migrating a suite*) — its own PR, never mixed into a feature, bug fix or restructure diff |

It applies to every command that writes tests — `/plan-red`, `/red`, `/reproduce`, `/plan-ft-dev`
(its testing plan), `/plan-pr-stack` 6e, `/roadmap-red`, `/green` and `/green-100` (tests added for
coverage), `/plan-test-rebalance` (replacement tests), `/fix-tests` (a test rewritten to fix it) — and
to every tier: unit, in-memory integration, and session-replay e2e. The rhombus decides the tier;
this decides the shape.

A fluent test sitting in a non-fluent file looks inconsistent. That is accepted, and deliberate: the
alternative — matching the legacy style — adds more tests that someone has to migrate later.

## The score

Each test is checked against ten yes/no questions. A check that cannot apply (no structured data, so
no builder needed) counts as **yes**.

| # | Check | A "no" looks like |
|---|---|---|
| 1 | **Name is a behaviour sentence** — the `describe` + `it` read as one statement of what the system does | `should work`, `test 3`, `calls fetchAsset`, the method name |
| 2 | **Three acts are visible** — Given, When, Then are separable at a glance | setup, action and assertions interleaved; a second action after the first assertion |
| 3 | **Flat** — no `if`, loop, `try/catch`, or early return in the body; at most one `describe` level of nesting under the file | branching on environment or result; a `for` over cases (use `it.each`) |
| 4 | **One behaviour** — one When, and the assertions describe one outcome of it | three scenarios in one test; asserting unrelated side effects |
| 5 | **Data by builder or factory**, with defaults, overriding only what the test is about | a 15-field literal; a fixture file whose content matters but is not shown (*mystery guest*) |
| 6 | **Assertions state intent** — a domain matcher, a driver query, or one structural equality | a roulette of `toBeDefined` / field-by-field checks over internals; asserting a mock of our own module was called |
| 7 | **Concrete, meaningful values** | `Math.random()`, `Date.now()` in an expectation, `foo` / `test123` where the value carries meaning |
| 8 | **No noise** — setup beyond a few lines lives in a helper, builder or driver; no dead setup, no commented-out code | 30 lines of wiring above a one-line assertion |
| 9 | **Async by event or `eventually`**, never by sleeping | `setTimeout`, fixed `wait(500)`, polling loops |
| 10 | **Readable cold** — from the name and the Then block alone, a reader new to the code can say what is verified | the assertion only makes sense after reading the production code |

**Test score** = checks passed (0–10). **Suite score** = the mean over the suite's tests, one
decimal. Checks 3 and 9 are also the repo's general anti-patterns (`docs/architecture.md`),
so failing either is a defect on its own, not just a lost point.

### Thresholds

| What | Bar | Below it |
|---|---|---|
| A test **this change wrote or edited** | **≥ 8**, and checks 3 and 9 pass | fixed in this PR — `/validate-tests` reports it 🔴, `/pr-wrap` step 2 fixes it. Never recorded as debt |
| A **suite this change wrote** (a new file) | suite score **≥ 8** | as above — the whole file is this PR's |
| A **pre-existing suite** this change touched | suite score **≥ 7**, counting only the tests this change did not write | a `non-fluent-tests` code issue for the suite (below). Never a reason to fail this PR |
| An **oversized** test file (≥ 500 lines) this change touched | suite score **≥ 8** | a `non-fluent-tests` code issue with **`Priority: 1`** — § *Oversized test files come first* |

Score the tests honestly against the table, one row per test, and keep the per-test rows in the
report: a suite score with no rows behind it is not reproducible, and the next run cannot tell a
real improvement from a generous reading.

## A non-fluent suite is a code issue

A pre-existing suite below 7 becomes a record in the
[code-issue record](../../deferred-work/references/code-issue-record.md) convention, category
**`non-fluent-tests`**, identity `(non-fluent-tests, <test file>, —)`:

```
<package-dir>/docs/code-issues/non-fluent-tests-<test-file-slug>.md
```

```markdown
**Location:** `src/services/map-layer-service.it.test.ts` — whole suite
**Category:** non-fluent-tests
**Detected:** YYYY-MM-DD by the fluent rubric (`testing/references/fluent-style.md`), via `/pr-wrap` step 2
**Metrics:** fluent score 4.6/10 · 31 tests · 24 below 8 · most-failed checks: 5 (builders) ×22, 6 (intent) ×19
**Restructure:** not required — a test-only rewrite; see *Migrating a suite*
**Priority:** 1 — oversized, 812 lines   <!-- only for a file ≥ 500 lines -->
```

`/analyze-code-issues` is the writer, as for every category (its § *Judged category: non-fluent
tests*): the score is judged against a fixed rubric rather than computed by a tool, so its `Verified
by hand` section is the per-test score table itself. Everything else is the ordinary contract —
reconcile before writing, one file per suite, `Measurement history` per run, deleted by the commit that
brings the suite to its bar — ≥ 7, or ≥ 8 for a `**Priority:** 1` (oversized) record, which stays
open until then even when the suite has passed 7 — renamed with `**Moved:**` when the file moves.

**Attribution — the one rule that differs from other categories.** `/pr-wrap` 7.6a solves in place
every record a PR *added*. A `non-fluent-tests` record on a **pre-existing** suite is not the PR's,
even though the PR added tests to that file and created the record: the legacy tests it measures
were already there. It is attributed **pre-existing**, kept, and listed in the summary — that is how
it bubbles up to whatever migrates it (below). Only a record on a suite the PR **created** is the
PR's, and the threshold table above has already fixed that one.

## Migrating a suite

A migration rewrites a suite to fluent **without changing what it verifies**: same behaviours, same
tier, same coverage, every test green before and after, suite score ≥ 8 after. It is
behaviour-preserving, test-only (no production file in its diff), and always **its own PR** — a stack
node of kind **Test-style migration** (`Type: Test Style` · `Behaviour: preserves`, preset
**test-style** — never `Type: Refactor`, which would route it to a `plan.jsonl`). It is never a
Restructure Prerequisite inside a feature changeset, because
it must not hold up that feature's green.

There are two shapes, and a stack may use both.

### Oversized test files come first

A test file of **500 lines or more** that is not fluent (suite score below 8) is the **No. 1
priority** of everything in this section. Its record carries `**Priority:** 1 — oversized, <n>
lines`, is closed only at a suite score of 8, and that line decides order everywhere a migration is
chosen:

- **Planning** — it is the first migration proposed, recommended *do it*, ahead of any other
  softening candidate the change runs into.
- **The sweep and `/fix-pr-stack`** — taken before every other backlog item, and never left behind
  when the sweep closes a partial backlog.
- **Migrate before you split.** A non-fluent test file is never split as it is: the split only
  spreads the raw setup into more files, and the builders and drivers the migration introduces are
  usually most of the lines. Migrate first, then split whatever is still ≥ 500 along its
  `describe` seams.

The file's `oversized-file` record stays as it is and closes with the same commit when the file ends
below 500; its *What would close it* names the fluent migration as the first step.

#### When a PR grows an oversized, non-fluent test file

`/pr-wrap` step 4 must decompose a file the PR pushed past 500 lines or grew further, and for a
non-fluent test file that means migrating it first. Whether **this PR** does that — rewriting tests
it did not write — or hands it to a migration PR is **the developer's decision**:

- **Interactive** (`/pr-wrap`, `/next`): the Wrap row halts ⛔ at step 4 with the file, its score,
  its size and the PR's share of it (below), and the options *a) migrate it in this PR* ·
  *b) hand it to a migration PR* — the record gets `**Priority:** 1` and a history row quoting the
  answer; the file is not split meanwhile. The answer on re-invocation is recorded in **Result**.
- **`/yolo` and `/yolo-pr-stack`**: the agent decides, by how much of the file is this PR's work.

  ```bash
  # $old / $f are step 4's base path and current path — they differ when the PR renamed the file
  pr_lines=$(git diff --numstat -M "$mb"..HEAD -- "$old" "$f" | awk '{s+=$1} END {print s+0}')  # lines added or changed
  was=$(git show "$mb:$old" | wc -l | tr -d ' ')   # the legacy suite; an error here is a stop, never 0
  ```

  `pr_lines` ≥ one third of `was` — the PR is proportionally big against the suite, and a rewrite
  is a modest extension of work it already does → **migrate in this PR**. Below that — a small PR
  that happens to land in a large legacy file → **do not rewrite**: the record gets
  `**Priority:** 1` with a history row naming the numbers and the decision (under `/yolo-pr-stack`,
  naming the sweep node), and the migration PR, softening node or sweep takes it. Either way the
  decision and its two numbers go under **Decided without review**.

### 1. Ground-softening — for a suite tests are about to be written into

At planning (`/plan-red` and `/plan-ft-dev` Step 2b, `/plan-pr-stack` Step 2b), check the suites the
change will add tests to: an open `non-fluent-tests` record, or a quick score below 7. Where the new
tests would sit among legacy ones that share setup with them — the builders and drivers the new tests
need are exactly what the migration would introduce — **propose** migrating the suite first, using
the ground-softening presentation (`deferred-work/references/planning-cross-check.md` § *Softening
the ground*). The difficulty it removes is named in this change: *"the 4 new tests need an asset
builder and a stage driver; the suite has neither and builds 20-field literals inline."*

Approved, it is a **stack node placed immediately below the first node that writes into the suite**
— for a standalone `/plan-red` change, that makes it a two-node stack. It needs nothing from the
nodes around it, so it greens in **wave 1**, in parallel. The nodes above do not wait for it: they are
planned and red-tested against the file as it is today, writing their own tests fluent, and when the
migration greens they rebase over it (`## Inherited Restructure — expect rewrite`, as for any
softening node). Declined, make sure the record exists and note the decision in `## Decisions &
Trade-offs`.

### 2. The sweep — the Boy Scout rule at the tail

Every PR's `/pr-wrap` scores the pre-existing suites it touched and files or updates their
`non-fluent-tests` records. Those records **bubble up**: under `/yolo-pr-stack` the **sweep node**
collects them with the rest of the stack's code issues and closes them, and `/fix-pr-stack`'s
assessment of the stack's code issues does the same for a stack landed by hand. The sweep sits at the
tail, so nothing below waits for it.

The sweep has latitude the softening node does not need: it may rewrite **whole test files the stack
touched**, not only the suites a record names, when the file shares builders or drivers with one
that is being migrated. Its bar is the same — behaviour, tier and coverage preserved, score ≥ 8 — and
it closes every `non-fluent-tests` record it took.

### The toolkit is the implementer's choice

A fluent rewrite is mostly not expressible as `/code-restructuring` intents, and it does not have to
be. Pick what fits the suite: `restructure` operations to move shared setup into a builder or driver
module, a codemod for a repetitive pattern, or a rewrite by hand. Whatever the tool, the proof is the
same and is recorded in the node's `## Verification` at **V2**:

- **Before**: the suite's test count, its test titles, its coverage of the production files it
  exercises (the tiers that ran), its fluent score with the per-test rows.
- **After**: the same tests green, every behaviour from the before-list still asserted (a renamed
  test is mapped to its old title), coverage not lower, suite score ≥ 8.

A test that cannot be rewritten without changing what it asserts was asserting something other than
behaviour — raise it; do not quietly change the assertion inside a migration.
