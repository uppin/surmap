---
description: Green phase with a 100% coverage gate - conventional /green, then accumulate coverage from every tier and prove the changeset's production code is fully covered
---
## Green-100 - Green Phase With a 100 % Coverage Gate

`/green-100` is `/green` plus a **pre-validation coverage gate**. Everything up to green is the
conventional workflow; then, before its row can close, it must prove that **100 % of the production code this changeset introduced or changed
is covered by tests** — and that the coverage sits at the right tier.

Use it when the changeset's production code must not ship with a coverage gap. Use plain `/green`
when it need not.

**Fully agent-driven.** The gate loops without stopping for input. Test output never enters the
context: `code-analysis cov-acc run` executes each suite itself, streams the output to a log, and
prints one summary line.

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`), through
`/green`'s *Workflow row*. Owns **Green** in the rebalance preset and any Green row swapped to it.
Result: `100 % of <n> lines, <t> tiers @ <sha>`, plus the e2e deletion commit in the rebalance
preset (Phase C). Halts, beyond `/green`'s: an exemption (B5 case 3); a Phase C equivalence check
that still finds lines on the e2e-unique list.

**Row TODOs** — `/green`'s (Phase A), then:

- Coverage accumulated from every tier the package declares (B2)
- 100 % of the changed lines covered, each gap closed at its tier or exempted (B3–B5)
- Result recorded in the changeset (B6)
- Equivalence proven, e2e deleted in its own commit (Phase C — rebalance preset only)

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, this command's work is done by the Muse
agent (`agent -p`) on the newest Composer model, driven by a Sonnet · low subagent — the
`composer-subagent` skill (`.agents/skills/composer-subagent/SKILL.md`), stage G (with this file in place of `green.md`), with the
skill's **row consent**. `#coder` does the same on a Coder workspace (`coder-remote` skill) and implies
`#composer-subagent`. The main agent readies the host (guiding the user through a missing Muse agent
CLI or login), runs the preflight, briefs the driver, reports a halt — the row's ⛔, written, committed and pushed by the Muse agent — in its
end-of-turn summary, and verifies the result. Every step of this file still runs; only who types changes. The coverage gate (Phase B) is part of the stage.
Only on request — never chosen on the agent's own initiative. Every modifier this command honours,
`#yolo` included, is defined once in the `behaviour-modifiers` skill
(`.agents/skills/behaviour-modifiers/SKILL.md`).

## Phase A - Run `/green` Unchanged

Follow **`.agents/commands/green.md` end to end**: the stack pre-run (step 0), the restructure
prerequisite (0.5), verify-red (1), implementation (2), post-green TODOs (3), the deferred-work
reconciliation (3.5), and commit and push (4) — except that the row closes only after Phase B (and
Phase C, in the rebalance preset).

Nothing in this command replaces or relaxes any of that. In particular:

- **Code quality > test passage** still holds. The gate below never justifies a workaround.
- If step 1 finds nothing red, `/green-100` halts exactly where `/green` halts. There is no green
  phase, so there is nothing to gate.
- Phase B starts only when the changeset's planned tests pass.

## Phase B - The Coverage Gate

### B1. What Is In Scope

**In scope: the production lines this changeset added or modified**, against the merge-base with the
branch's actual base — plus every line of a production file the changeset created.

```bash
BASE=$(gh pr view --json baseRefName --jq .baseRefName 2>/dev/null || echo master)
git merge-base --is-ancestor "origin/$BASE" HEAD   # sanity: rebase first if this fails
```

**Not in scope**: lines the changeset did not touch, even in a file it touched. **But their absence
is never an excuse.** "This file was at 12 % before" does not lower the bar for the lines you wrote;
the gate is diff-scoped precisely so that a badly-covered file cannot dilute a new change into
looking acceptable.

Excluded from the measurement entirely (they are not this changeset's production code): test files
and test doubles, generated code (`src/protogen/**`, WASM bindings, `*.d.ts`), bootstrap entry
points a package's own coverage config already excludes, and documentation.

### B2. Accumulate Coverage From Every Tier

The store is a SQLite database that **survives context resets** — it is the resume point, so this
loop can run across many contexts without ever re-running a suite it already recorded.

```bash
code-analysis cov-acc status --package <pkg-dir>     # what is already recorded, what is stale
```

For **every tier the package has** — that is every `test:*:coverage` script in its `package.json`,
including e2e — that `status` reports as missing or stale:

```bash
code-analysis cov-acc run --tier unit      --package <pkg-dir>
code-analysis cov-acc run --tier it        --package <pkg-dir>
code-analysis cov-acc run --tier component --package <pkg-dir>
code-analysis cov-acc run --tier e2e       --package <pkg-dir>
```

Each `run` resolves that tier's coverage script, executes it with output redirected to a log under
the store, ingests the resulting coverage into the DB keyed by `(tier, file, line)` **and the file's
git blob hash**, and prints one line. Read the log **only** when a run fails.

Rules:

- **A tier that exists must be ingested.** A missing tier is not "assumed covered" — `verify`
  refuses a verdict until every tier the package declares has a current run. If a tier's script is
  genuinely absent, say so in the summary; do not invent an exemption.
- **e2e included.** The e2e tier's coverage is source-mapped back to `src/*.ts` at runtime
  (`common-testing/session-test-helpers/scripts/instrument-dist-coverage.mjs`), so it joins the other
  tiers on the same keys. It needs the workspace packages built first — the tier's own script does
  that.
- **Never ingest a red run.** A failing suite's coverage is a partial trace of a broken state.
  `run` will not ingest a non-zero exit; fix the failure, then re-run.
- **Staleness is per file, by blob hash.** Editing one file invalidates that file's rows in every
  tier, not the whole run. `status` names the file and the tiers that need re-running — re-run only
  those. This is why closing a gap does not cost a full re-measurement of the package.

### B3. Verify

```bash
code-analysis cov-acc verify --base "origin/$BASE" --package <pkg-dir>
```

`verify` unions every current run in the store, intersects with the in-scope diff lines from B1, and
prints per file: uncovered lines, uncovered branches, uncovered functions. Non-zero exit means a gap
(or a missing/stale tier). A clean run is the gate passing.

### B4. Close Each Gap — At the Right Tier

For every gap, the tier is not a preference. It is decided by the rhombus rule in
[docs/architecture.md](../../docs/architecture.md#test-balance--the-rhombus):

> **What would a test double have to stand in for?**
> Nothing → unit (`*.test.ts`). Only code we do not own → in-memory integration (`*.it.test.ts`).
> The process boundary itself → e2e (`*.e2e.test.ts`).

So, per gap:

1. **Default to `*.it.test.ts`** — the wide middle. Real implementations for everything we own,
   in-memory doubles only at ports to foreign code.
2. **Only pure, double-free code goes to `*.test.ts`.** If the unit test you are about to write
   needs `vi.mock` on a module we own, it is in the wrong tier — write the in-memory test instead.
3. **Do not close a coverage gap with an e2e test.** Ever. E2E is unique flows and success
   scenarios only; an error branch reachable only from e2e is a *design* finding — the code owns
   something it is reaching past a port. Fix the seam, then cover it in memory.
4. **Write real tests.** Every anti-pattern in the testing guide still applies — no branches in
   tests, no fallback assertions, no `expect(true).toBe(true)`, no test that exists to walk a line
   without asserting the behaviour on it. **A coverage-driven test that asserts nothing is worse
   than the gap it closed**, because it silences the gate permanently.
   And every one is **fluent** (`fluent-tests` skill, ≥ 8 on
   `.agents/skills/testing/references/fluent-style.md`) — a coverage test is still read by people.
5. Then re-run only the tiers `status` marks stale, and `verify` again.

Loop B2 → B4 until `verify` is clean.

### B5. When a Line Genuinely Cannot Be Covered

Three real cases, in the order to try them:

1. **The line is dead** — nothing reaches it. Delete it. That is the finding, and deleting it is the
   fix (confirm with find-references first; check other packages if the symbol is exported).
2. **The line is unreachable because a dependency is not behind a port** — the seam is the problem.
   Extract the port and cover it in memory. This is the common case and it is a design improvement,
   not a detour.
3. **Neither** — then it is an exemption, and an exemption is **not yours to grant**. There is no
   ignore-comment escape hatch in this gate: an `istanbul ignore` added to pass it is a coverage
   lie, and it outlives the session. Follow `/green` step 3.5c: halt the row ⛔ with the line, the
   blocker and the refuted alternatives; on re-invocation record the developer's words in Result,
   write `<package-dir>/docs/todo/YYYY-MM-DD-<slug>.md` quoting them, and name that file in the
   changeset row. Then say so in the summary with a visual indicator.

"It is hard to cover", "the file is enormous", "the session is long" are none of the three.

### B6. Record the Result in the Changeset

Add to the active changeset in `docs/<area>/1-WIP/`, under `## Coverage Gate`:

```markdown
## Coverage Gate (`/green-100`)

| Metric | Value |
|---|---|
| In-scope changed production lines | 214 |
| Covered | 214 (100 %) |
| Tiers ingested | unit, it, e2e (component: no script) |
| Tests added to close gaps | 9 it, 2 unit, 0 e2e |
| Exemptions | none |
```

If anything was exempted, the row names the `<package-dir>/docs/todo/` file. An exemption with no file is
the same gap, unrecorded.

## Phase C - Rebalance Preset Only: Prove Equivalence, Then Delete

When the row is the rebalance preset's Green (`/plan-test-rebalance` wrote the changeset), the row's
work also includes that plan's execution steps after the replacements are green
(`.agents/commands/plan-test-rebalance.md` step 7):

1. **Verify equivalence**: re-run `code-analysis cov-acc unique --tier e2e`. Every line the plan
   promised to move down is gone from that list. If one is still there, the replacement did not do
   its job: halt the row ⛔ with the lines in Result, and delete nothing.
2. **Delete the e2e cases** the plan marked Demote and Delete — only those the plan names — in one
   commit that touches only e2e files, with the new shape table in the message.
3. **Re-measure** the shape and record it where the plan says.

## Success Criteria

- ✅ Every `/green` success criterion (that command's list applies unchanged)
- ✅ Every tier the package declares has a **current** run in the store — none missing, none stale
- ✅ `code-analysis cov-acc verify` exits clean: **100 %** of in-scope changed production lines,
  branches and functions covered
- ✅ Each gap closed at the tier the rhombus rule picks — **no gap closed by an e2e test**
- ✅ No `istanbul ignore` / coverage-suppression comment added anywhere in the diff
- ✅ Every added test asserts behaviour, not line traversal
- ✅ `## Coverage Gate` table filled in the changeset; any exemption carries a
  `<package-dir>/docs/todo/` file with a named blocker and recorded consent

## What NOT to Do

- ❌ Don't close a coverage gap with an e2e test, or by widening an existing e2e test's assertions
- ❌ Don't add `/* istanbul ignore next */`, `# pragma: no cover`, or any equivalent to pass the gate
- ❌ Don't write a test whose only purpose is to enter a line — assert the behaviour or delete the line
- ❌ Don't ingest coverage from a failing suite
- ❌ Don't skip a tier because it is slow. Skip it only if the package has no script for it, and say so
- ❌ Don't lower the scope to "files I fully understand" — the scope is the diff
- ❌ Don't treat a pre-existing 0 % file as permission for a partial verdict
- ❌ Don't paste suite output into the context; read a log only when a run fails
- ❌ Don't grant your own exemption. That needs the developer's recorded consent

## Related

**Commands**: `/green` (phase A, in full), `/red` (writes the tests this row greens),
`/plan-test-rebalance` (when the gate keeps pushing coverage down a tier across a whole package; its
plan drives Phase C), `/pr-stack-rebase` (required pre-run on a stack branch)
**Guide**: [docs/architecture.md](../../docs/architecture.md#test-balance--the-rhombus) — the rhombus, and the tier rule this gate enforces
**Skills**: `tdd` (`.agents/skills/tdd/SKILL.md`), `hexagon-testable-architecture`
(`.agents/skills/hexagon-testable-architecture/SKILL.md`) — the ports that make the middle band
possible, `deferred-work` (`.agents/skills/deferred-work/SKILL.md`) — exemption records
**Tool**: `code-analysis cov-acc` (`common/code-analysis/`) — the accumulating coverage store
