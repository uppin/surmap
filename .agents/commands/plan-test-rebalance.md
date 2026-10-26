---
description: Measure a scope's test shape and plan the move to the rhombus - which e2e tests to delete, and which lower-tier tests must exist first to keep the same code covered
---
# Plan Test Rebalance

## Intent

The User intends to move a scope's tests toward the **rhombus**: very few e2e tests, a wide middle
band of in-memory integration tests, a few double-free unit tests. See
[docs/architecture.md](../../docs/architecture.md#test-balance--the-rhombus).

This is **planning only** — no test is written, moved or deleted here. The output is a changeset
whose plan another command executes.

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). It owns
row 1, **Measure and plan**, of the **rebalance** preset: it writes the changeset's `## Workflow` from
that preset (step 8) and closes row 1 ✅ with the shape before → target and the count of e2e cases
to delete. The later rows — Red, Green with the equivalence proof and the deletion, Wrap, PR,
Checks — are the preset's. When the scope is already a rhombus, row 1 closes ✅ "already a rhombus"
and every later row ➖ with that reason. It halts row 1 ⛔ when the tiers cannot be counted (a
`vitest list` that errors, step 2) or the scope needs a behaviour change first (§ *What NOT to Do*).

**Row TODOs** (Measure and plan) — seeded when the row starts; a re-run resumes at the first open one:
`Tier counts measured (step 2)` · `Every e2e case triaged (step 3)` · `Equivalence traced (step 4)` ·
`Replacements planned (step 5)` · `Design findings recorded (step 6)` · `Changeset, rows and their
TODOs written (step 8)`

## The One Rule That Orders Everything

> **Coverage goes down a tier before the test above it is deleted.**

Never the reverse, and never in the same commit. A deletion whose replacement is not yet green and
not yet proven to cover the same code is not a rebalance — it is a coverage cut with a tidy name.

## Workflow

### 1. Scope

A package (`src/surmap-server`), or a feature area within one. State the scope in the plan.
Rebalancing more than one package at a time makes the equivalence proof in step 4 unreadable — do
them one at a time, in one changeset if they are related.

> **Vitest tiers only — and name what is excluded.** This workflow counts Vitest `unit` / `it` /
> `e2e` suites (`*.test.ts`, `*.it.test.ts`, `*.e2e.test.ts`). Many packages also run component,
> pytest unit, integration and session-replay suites — for example `src/surmap` uses
> Playwright for `test:e2e` and has component/E2E framework tiers. Inventory those separately in the shape
> table (cases + wall clock on their own row) or state explicitly that they are out of scope for
> this rebalance. **Never treat a Vitest-only count as the package total.**

### 2. Count Test Cases per Tier — Cases, Not Files

File counts hide the shape; a single e2e file with 40 `it`s is an ice-cream cone on its own.

**Discover each tier's config from `package.json` — do not hard-code filenames.** Read the
`test:unit`, `test:it`, and `test:e2e` scripts for a `--config <file>` flag; when absent, unit
often uses `vitest.config.ts` with a path argument (e.g. `vitest run test/unit`), not
`vitest.unit.config.ts`. `src/surmap-server` is an example: it has `vitest.config.ts`,
`vitest.it.config.ts`, and `vitest.e2e.config.ts`, but no `vitest.unit.config.ts`.

```bash
cd <pkg-dir>
# Replace each --config with the file the package's script actually uses.
uv run pytest --collect-only -q tests/ | wc -l  # unit
uv run pytest --collect-only -q tests/ -k integration | wc -l
uv run pytest --collect-only -q tests/ -k replay | wc -l
```

`vitest list` enumerates collected cases, one per line, so it counts what actually runs — including
`describe.each` expansions, which grep cannot see. Record wall-clock per tier from the last full run
too; the shape argument is about cost as much as count.

**Never discard stderr** (`2>/dev/null`) on `vitest list`. A missing config or failed import must
stop the command with a clear error — piping a failed run to `wc -l` reports zero and produces a
bogus shape table.

`list` imports the test files, so it needs the package's **workspace dependencies built**. A
`Failed to resolve entry for package "@/…"` here is a missing `dist/`, not a config problem: run
`uv run mypy` and re-list. Do not switch to grepping for `it(` because of it —
that undercounts every
`.each` table in the suite.

Produce the current-shape table:

| Tier | Cases | % of total | Wall clock | Rhombus target |
|---|---|---|---|---|
| e2e | 38 | 31 % | 11 m 40 s | ≤ 5 % — unique flows, success only |
| it | 54 | 44 % | 26 s | the majority |
| unit | 31 | 25 % | 4 s | few — double-free only |

Name the anti-shape it currently is (ice-cream cone / mock-heavy pyramid / hollow rhombus), or say
it is already a rhombus — in which case the honest output of this command is "no rebalance needed",
and it stops here.

### 3. Triage Every E2E Case Against the Four Conditions

An e2e test earns its place only if it proves wiring nothing below it can reach, is a success
scenario, walks a unique flow, and has that justification written down
([the E2E section](../../docs/architecture.md#e2e-tests)).

One row per e2e case, and the verdict is one of exactly three:

| Case | Verdict | Why |
|---|---|---|
| `boots and serves process_frame over the SlamBackend port` | **Keep** | only test that exercises real transport + bootstrap |
| `rejects a frame with an unknown calibration_id` | **Demote → it** | an error branch; nothing about the wiring |
| `process_frame persists the static layer` | **Delete** | the same assertion already exists in `test_slam.py` |

- **Keep** — names the unique wiring. If the justification is missing, write it as part of the plan.
- **Demote** — the behaviour is real and must survive at a lower tier. Every demotion becomes a
  replacement test in step 5.
- **Delete** — already asserted below, verified in step 4. Nothing to write.

Do not use a fourth verdict. "Maybe later" leaves the e2e test in place forever.

### 4. Prove Equivalence From Per-Test Coverage

The repo records **per-test** coverage (`coverage/per-test/<id>.json` + `.meta.json`), so which lines
a single e2e case uniquely covers is a measurement, not an argument.

```bash
cd <pkg-dir>
code-analysis cov-acc run --tier unit      # populate the store, one tier at a time
code-analysis cov-acc run --tier it
code-analysis cov-acc run --tier e2e
code-analysis cov-acc unique --tier e2e    # lines covered by e2e and by no other tier
```

`cov-acc unique --tier e2e` is the list the rebalance has to answer for: **every line there needs a
lower-tier test before its e2e case can go.** A **Delete** verdict is only valid when that case
contributes nothing to this list; if it does contribute, the verdict is **Demote**, not Delete.

**Line uniqueness is necessary but not sufficient.** Two tests can execute the same regions while
asserting different outcomes or failure modes. A **Delete** verdict also requires an explicit
lower-tier replacement (step 5) that carries the demoted case's **assertions**, not just its line
hits — and step 7's gate is: replacement green **and** every named assertion listed in the plan.
See also `common/code-analysis/AGENTS.md` (*Reading a duplicate-tests report*): identical coverage
signatures do not mean identical assertions.

Cross-check **within-tier** redundancy (same tier, same coverage directory):

```bash
code-analysis duplicate-tests --coverage-dir coverage-e2e
```

`duplicate-tests` accepts **one** `--coverage-dir`; repeated flags are reduced to the first only.
For cross-tier overlap, `cov-acc unique --tier e2e` is authoritative — not a second
`--coverage-dir`. To compare signatures across tiers inside one directory, copy each tier's
`coverage/` aside before the next vitest run (each run wipes `coverage/`), merge the per-test
artifacts into one tree, then run `duplicate-tests` on that merged directory.

**Rank the results by steady state, not by the reported `recoverableMs`** — that figure is inflated
by cold starts and by failed members. Recompute as *cheapest member's time × redundant count*; a
group whose members are all slow-because-cold is not the saving it appears to be.

### 5. Plan the Replacement Tests

For each **Demote**, the tier is decided by the rhombus question — *what would a double have to
stand in for?* — not by where it is convenient to write.

| # | Replaces (e2e case) | New test | Tier | Covers (from step 4) | Blocked by |
|---|---|---|---|---|---|
| 1 | `rejects unknown calibration_id` | `test_slam.py` → `rejects an unknown mediaId` | it | `slam/rtabmap.py:88-96` | — |
| 2 | `retries on RtabmapUnavailable` | `test_slam.py` → `retries then surfaces RtabmapUnavailable` | it | `slam/fake.py:41-70` | port extraction, item D1 |

Rules:

- **Every replacement is fluent** (`fluent-tests` skill, ≥ 8 on
  `.agents/skills/testing/references/fluent-style.md`), whatever style the suite it lands in has.
- **No replacement is an e2e test.** If the only way to cover a demoted behaviour is another e2e
  test, that is a design finding for step 6 — not a replacement.
- **A unit test replacement must be double-free.** Needing `vi.mock` on our own module means the
  replacement belongs in the middle band.
- Each row names the exact lines from step 4 it is responsible for **and the assertions** the
  demoted e2e case carried. That mapping is what the execution phase verifies, and what makes the
  deletion in step 7 safe.

### 6. Design Findings — Behaviour That Cannot Move Down Yet

A demoted behaviour with no in-memory home is a **seam** problem: production code is reaching past a
port. List each one as its own item — the port to extract, the adapter to introduce, the coordinator
to replace real Greyhound with
([hexagon-testable-architecture](../skills/hexagon-testable-architecture/SKILL.md)).

These are **prerequisites** of the replacement tests that depend on them, so they carry an item id
(`D1`, `D2`) that step 5's *Blocked by* column references. A rebalance that skips them silently
degenerates into deleting e2e tests and hoping.

Anything found here that is not part of this effort's scope belongs in
`<package-dir>/docs/code-issues/` rather than in this plan's body.

### 7. Sequence the Execution — Add Below, Then Delete Above

The plan must be executable in this order, and the commits must be separate:

1. **Design findings** (step 6) — each in its own commit, no behaviour change.
2. **Replacement tests red, then green** — the preset's Red and Green rows (`/plan-red`, then
   `/green-100`; a table may swap Green to `/green` when the changeset changes no production code).
3. **Verify equivalence**: re-run `cov-acc unique --tier e2e`. Every line the plan promised to move
   down is gone from that list. **This is the gate on step 4** — if a line is still there, the
   replacement did not do its job and the deletion does not happen.
4. **Delete the e2e cases** — Keep-verdict cases stay, Demote and Delete cases go, in one commit
   that touches only e2e files, with the new shape table in the message.
5. Re-measure step 2 and record the resulting shape.

### 8. Write the Plan Into a Changeset

**If a changeset for this work is already in context** — the session is mid-flow on one, or the
User named one — **reuse it.** Add a `## Test Rebalance` section carrying steps 2–7 (shape table,
triage table, replacement table, design findings, sequence), and add to its `[wf]` rows a
**Measure and plan** row closed ✅ by this run, plus whichever rebalance-preset rows it does
not already have — never reorder or close the rows already there. Do not open a second changeset
for what is one piece of work; two changesets over one branch is how an Outcome column ends up
half-filled in each.

**Otherwise this is a bigger effort of its own** — start it per the `pr-lifecycle` skill §
*Start a changeset* (`.agents/skills/pr-lifecycle/SKILL.md`), slug `test-rebalance-<scope>`, with:

- **Type**: `Test Rebalance` (with `**Behaviour**: preserves`) — **not** `Refactor`, which would
  route this work into a restructure's `plan.jsonl` workflow. No production behaviour changes, and
  the plan must say so explicitly, since a rebalance that also changes behaviour cannot be reviewed
  as one
- **Verification**: **two rungs, because the replacements never fail first.** V1-characterisation
  for the replacement tests — green the moment they are written, since the behaviour they pin
  already exists, and valuable because they *would* fail if a later change altered it. Plus **V3**
  for the equivalence claim, which is a measurement rather than a test:
  `**Command:** cov-acc unique --tier e2e`, with the **before** list recorded here and the **after**
  list as the gate on the deletion (step 7.3) — every line the plan promised to move down is gone
  from it. Without the V3 half, a deletion is a coverage cut with a tidy name
- **Workflow**: the rebalance preset, row 1 closed ✅ by this command
- **Initial Discovery**: the tier inventory, the per-test coverage traces, and the duplicate-tests
  output belong in the companion, not in the changeset body
- **State A / State B**: the shape tables from step 2 and its target
- **Prerequisites**: step 2b of planning, plus the step 6 design findings
- **Implementation Milestones**: step 7's five stages as TODOs nested under the row that does each
  (Red, Green); under Wrap the wrap obligations plus the optional `/pr-wrap` steps this change needs
  (`/pr-wrap` § *Workflow row*, *Row TODOs*), which `/pr-wrap` may extend
- **Testing Plan**: the replacement table from step 5

## Success Criteria

- ✅ Vitest tier counts measured with `vitest list` (cases, not files), with wall clock; non-Vitest
  suites inventoried or explicitly excluded
- ✅ Current anti-shape named — or "already a rhombus, no rebalance needed" and the command stopped
- ✅ **Every** e2e case triaged to exactly one of Keep / Demote / Delete, each with a reason
- ✅ `cov-acc unique --tier e2e` captured, and every line on it assigned to a replacement test
- ✅ No replacement test is an e2e test; no unit replacement needs a mock of our own code
- ✅ Design findings listed with ids, and referenced by the replacement rows they block
- ✅ Execution sequenced add-below-then-delete-above, in separate commits
- ✅ Plan written into the **existing** changeset when one is in context, otherwise a new one with
  its initial-discovery companion

## What NOT to Do

- ❌ Don't delete an e2e case in the same commit as (or before) its replacement
- ❌ Don't delete a case that still contributes lines to `cov-acc unique --tier e2e`
- ❌ Don't plan an e2e test as a replacement for a demoted e2e test
- ❌ Don't rebalance for speed alone — the argument is diagnosability and coverage placement; the
  time saved is a consequence
- ❌ Don't count test files and call it the shape
- ❌ Don't rank duplicate-test groups by raw `recoverableMs`
- ❌ Don't open a second changeset when one is already in context
- ❌ Don't change production behaviour in a `Refactor` rebalance — a needed behaviour change is a
  separate changeset, and it is planned before this one
- ❌ Don't write or move a single test here. This is planning

## Related

**Commands**: `/plan-red` (the Red row — writes the replacement tests), `/green-100` and `/green`
(the Green row), `/plan-ft-dev` (changeset conventions), `/analyze-code-issues` (coverage and CRAP
targeting for the same scope), `/validate-tests` (quality of what gets written)
**Guide**: [docs/architecture.md](../../docs/architecture.md#test-balance--the-rhombus)
**Skills**: `hexagon-testable-architecture` — the ports the middle band needs; `testing`;
`deferred-work` — where out-of-scope findings go
**Tool**: `code-analysis cov-acc` (`common/code-analysis/`) — the accumulating coverage store and
`unique --tier`

**Contract**: `.agents/skills/pr-lifecycle/SKILL.md` — the rebalance preset and the step
contract the later rows follow.
