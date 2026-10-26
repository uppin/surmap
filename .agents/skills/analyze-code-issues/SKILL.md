---
name: analyze-code-issues
description: Run tool-backed code issue analysis before restructuring — CRAP scoring, coverage gaps, git hot-files, type-escape density, and dead-code vs missing-tests classification via surmap, for TypeScript, Rust and Python. Reads the package's existing `<package-dir>/docs/code-issues/` record first and reconciles every finding against it — updating, renaming a moved issue, recording a regression, deleting the record of what is genuinely fixed — so re-analysis never duplicates. Use when planning a restructure, choosing refactor targets, re-measuring a package already analyzed, or when the user asks how to run CRAP analysis, find high-risk untested code, detect unused code, or measure how much `any` / `Any` a package carries.
---

# Analyze Code Issues

Tool-backed targeting pass that feeds [`code-restructuring`](../code-restructuring/SKILL.md). Complements `/analyze-clean-code` (LLM heuristic at PR-wrap); does not replace it.

## When to use

- Before `code-restructuring` step 1.5 (mandatory prerequisite)
- When choosing which files/modules to split first
- When the user asks about CRAP, coverage gaps, unused code, or churn-heavy hotspots

## Workflow

### 1. Identify the target

Package directory (e.g. `mapping-pipeline/stereo-ingest`) or specific files. State scope in the output.

### 1.5. Read the existing record first — this is a re-measurement, not a first look

Before running anything, load what is already known about this package. Most runs of this skill are
the **second or fifth** run against the same code, and the value of the run is the *delta*: which
issues moved, which cleared, which are new. A run that ignores the record produces duplicates and
loses every hand-verification note somebody already paid for.

```bash
ls <package-dir>/docs/code-issues/ 2>/dev/null                  # the listing IS the index
grep -H 'Location:\|Status:\|Metrics:' <package-dir>/docs/code-issues/*.md
ls <package-dir>/docs/code-issues/   # every file is open
```

A file whose `**Status:**` begins `Resolved` (or `Closed`) predates delete-on-resolve, for example
from a branch cut before the migration. It is **not** open and must not be updated or reopened:
`git rm` it in the run's commit and say so in the reconciliation report.

Read every open file's `Location`, `Metrics` and `Verified by hand`. Build a small map — one row per
existing issue: `(category, file, symbol) → filename, last metrics, status`. That map is what step 7
reconciles against. If the directory does not exist, this is the package's first analysis: say so in
the targeting note, and expect every finding to be new.

### 2. Establish a green baseline

```bash
uv run mypy   # plus its workspace dependencies
uv run pytest -q
```

Do not analyze a red tree. Record pass/fail counts.

### 3. Collect coverage from every test tier

Missing-tests is only valid against the **full** suite. A function covered by e2e but missed by
unit is not a missing test. Vitest wipes `coverage/` at the start of each run, so a chained
`uv run pytest -q` keeps only the last tier — copy each tier aside, then pass every directory.

For the target package, run **every coverage script that exists**:

| Tier | Typical script |
|---|---|
| unit | `test:unit:coverage` |
| it | `test:it:coverage` |
| component | `test:component:coverage` |
| e2e | `test:e2e:coverage` / `coverage:e2e` |

Python/Rust packages with a single `coverage` script: that run *is* the suite.

```bash
# Python — copy aside between tiers (coverage tooling may clean coverage/ on start)
uv run pytest -q
cp -a coverage coverage-unit
uv run pytest -q
cp -a coverage coverage-it
uv run pytest -q
cp -a coverage coverage-e2e

# Rust native tests (one run is the suite)
uv run pytest -q

# Python (coverage.py via pytest — one run is the suite)
uv run pytest -q
```

If a tier has no coverage script, say so in the targeting note. Do **not** treat its absence as
"fully tested".

Produces `coverage/per-test/*`, `coverage-final.json` (TS), `rust-coverage-final.json` (Rust),
`python-coverage-final.json` (Python) per directory.

Python is a **first-class language here**, not an afterthought: `surmap` registers a
`pythonLanguageProvider` supplying complexity (through the `source-metrics` binary's
`rustpython-parser` front end) and the coverage join, and `surmap`'s pytest plugin
writes the per-test artifacts as `per-test/*.py.json`. CRAP, `issues`, `hot-files` and
`duplicate-tests` all cover Python.

### 4. Build the analysis toolchain (once per session)

```bash
uv run mypy
```

### 5. Run targeting

```bash
code-analysis report                    # if not already run by `coverage`
code-analysis issues --path <pkg-dir> \
  --coverage-dir coverage-unit \
  --coverage-dir coverage-it \
  --coverage-dir coverage-component \
  --coverage-dir coverage-e2e
code-analysis hot-files --path <pkg-dir> --top 20
code-analysis types --path <pkg-dir>    # type-escape density; add --no-typecheck to skip mypy
```

Pass every copied tier directory, and run from the package directory — `--coverage-dir` is
resolved against the current directory, not against `--path`. Omit a flag only when that tier does
not exist on the package. `issues` already includes the dead / missing-tests / test-only sections.
A function is covered if **any** run entered it. Use the dedicated command when you only want that
classification:

```bash
code-analysis dead-code --path <pkg-dir> \
  --coverage-dir coverage-unit \
  --coverage-dir coverage-it \
  --coverage-dir coverage-component \
  --coverage-dir coverage-e2e
```

`types` needs no coverage run. Its **authoritative** half type-checks the target with mypy, which
is the slow part and only applies to Python — so `--no-typecheck` gives the syntactic census alone
in milliseconds. It also accepts `--fail-on-violations` to exit non-zero, which is opt-in: the
report is advisory by default like every other metric in this skill.

### 5b. Judged category: non-fluent tests

The one category no tool computes. Score test suites against the fixed rubric in
[`testing/references/fluent-style.md`](../testing/references/fluent-style.md) § *The score* — ten
yes/no checks per test, suite score = the mean — after loading the
[`fluent-tests`](../fluent-tests/SKILL.md) skill for what each check means in the suite's framework.

**Scope is the test files you were asked about, not the package.** Scoring by reading is expensive,
so it runs over: the test files a PR touched when invoked from `/pr-wrap` or `/validate-tests` (they
hand you the list, and for a pre-existing file only the tests the PR did **not** write count); the
files a planner names at Step 2b; every test file under `--path` only when the developer asks for a
package-wide measurement. Say which in the targeting note.

A suite scoring **below 7** is a `non-fluent-tests` finding against the file — and a test file of
**≥ 500 lines** scoring **below 8** is one too, with `**Priority:** 1 — oversized, <n> lines`. List
the Priority 1 records first in the targeting note. Record one per suite, never per test. The per-test score table **is** the record's `Verified by hand` section — a judged
score without its rows cannot be re-checked by the next run.

### 6. Produce a targeting note

Summarize for the developer:

- Top CRAP functions (TypeScript, Rust and Python) — complex **and** untested
- Lowest-coverage files
- Highest git churn files
- **Large source files** — ≥ 500 lines too large; 300–499 ok (reduce when possible); < 300 great
- **Authored type escapes** — every one is a finding; the threshold is 0
- **Dead code** — unused in production and not referenced by tests. Delete candidate. Confirm with
  find-references before removing, and check other packages when the symbol is **exported**.
- **Missing tests** — referenced from production, not entered by **any** of unit / it / component /
  e2e. Add tests; do **not** delete. A single coverage run is not enough — the report says how
  many runs were merged.
- **Test-only** — imported by tests, not by production. Public API, test helper, or unused
  production. Check consumers before deleting.
- **Non-fluent suites** (5b, when in scope) — suite score, test count, most-failed checks. A
  migration candidate (`fluent-style.md` § *Migrating a suite*), never a delete
- **Intersection**: high CRAP ∩ hot files = best restructuring candidates
- **Large ∩ hot**: too-large files (≥ 500 lines) ∩ hot files = split-first candidates when churn and size align
- **Escapes ∩ hot**: files with the highest escape **density** ∩ hot files = the code most likely to
  break silently while it is being changed, since the type system is not holding it. Use the
  per-100-line rate here, not the raw count — a large file always wins on count

Reported only — no CI gate. File-length thresholds match [`/analyze-clean-code`](../../commands/analyze-clean-code.md).

### Reading a type-escape report

Two numbers, and the gap between them is often the real finding.

- **Authored** escapes are what someone wrote and can delete in that file — `any` / `Any`,
  `as any`, `cast(Any, …)`, `# type: ignore`, `@ts-expect-error`, a bare `dict`, `dyn Any`,
  `unsafe`, `transmute`. **Threshold 0**: every one is a finding.
- **Leaked** escapes are `Any` reaching the code from a dependency that ships no type information.
  Counted and attributed to the responsible dependency, but **not** held to the threshold — the
  remedy is a stub package, not an edit to the file that reports it.

**Count and density are separate metrics.** The table is ordered by count, because that is what the
zero threshold measures. The `per 100 lines` column is the density metric: it answers how
concentrated the escapes are rather than how many there are, and it is the one to intersect with
churn. Attribution of leaked `Any` is incomplete by nature — mypy only names a dependency it
reports an import error for, so one that ships no `py.typed` without erroring counts toward the
total without being named.

**"Not measured" is not "clean".** Only Python has an authoritative pass, and it needs a synced
venv and a `pyproject.toml` at or above the target. When it cannot run, the report says so rather
than reporting zero leaked escapes — read that as *unknown*, and do not conclude the package is
well typed from the authored count alone.

**Annotation coverage is not precision.** A package can report ~100% of annotation slots filled
while the type checker still calls 14% of its expressions `Any`, because `Any` leaking in from an
untyped dependency is invisible to a syntactic pass. The report names that divergence when it is
material; when it does, trust the type checker and treat the annotation figure as the flattering
one. Rust's escape signal is the weakest of the three by design — it counts type erasure and
soundness escapes only.

### 7. Reconcile and persist — one file per issue, next to the package's dev docs

The targeting note is for the developer reading it now. The **record** is what planning reads months
later, and it lives with the package it describes. Reconciling this run's findings against the
existing record (7a–7e) comes **before** any file is written; one open file per symbol, ever.

```
<package-dir>/docs/code-issues/<category>-<file-slug>[-<symbol>].md
```

```
mapping-pipeline/mapping-pipeline-server/docs/code-issues/
  crap-map-layer-service-apply.md
  missing-tests-subasset-processing-service.md
  oversized-file-session-replay-service.md
  type-escapes-asset-mapper.md
  dead-code-legacy-page-index.md
```

Categories mirror the sections above: `crap`, `missing-tests`, `dead-code`, `test-only`,
`oversized-file`, `type-escapes`, `hot-file`, `duplicate-tests`, `non-fluent-tests` (5b — identity
`(non-fluent-tests, <test file>, —)`).

**No date prefix, deliberately.** A code issue is a standing property of the code, not an event, so
re-running this skill must **find and update** the file that already names that symbol rather than
deposit a second copy of the same finding. The identity is `(category, file, symbol)` and the
filename encodes it.

**There is no index file.** The directory listing is the index; an index would be a shared
append-point that conflicts on every parallel branch.

#### 7a. Reconcile against the record — never write before matching

Every finding this run produced is matched against the step-1.5 map **before** any file is written.
Duplicate issue files are the failure mode this step exists to prevent: two files describing the same
function, with different numbers and only one of them carrying the hand-verification note, and no way
for a later reader to tell which is current.

| The finding | The record | Action |
|---|---|---|
| present | **no match** | **new file** — but only after 7b's moved-identity check says it is genuinely new |
| present, numbers moved | open file matches | **update in place**: `Metrics`, a `Measurement history` row, and any new detail. Keep the file |
| present, numbers unchanged | open file matches | **touch the history only** — one row saying `unchanged`. Do not rewrite the prose; churn in this directory is noise |
| **absent** (tool no longer reports it) | open file matches | **verify, then delete the file.** Confirm by hand that the code changed rather than the measurement — see 7c |
| present | no file, but `git log --diff-filter=D` shows a deleted record for it | **new file** citing the deleting commit (7d) |
| present, **different category**, same symbol | a file for the old category | **new file** for the new category, and **delete** the old one (7e) |

Say in the targeting note how many findings fell into each row. That count is the run's headline for
anyone who has seen the package before.

#### 7b. Match a moved identity before concluding "new"

The identity is `(category, file, symbol)`, and **all three move**. A renamed file, a renamed symbol,
or a function relocated by a `/code-restructuring` run all present as "no match" to a filename lookup
— and filing a new file then leaves two records for one problem, the older one now pointing at a path
that no longer exists.

So before writing any new file, search the record by each part of the identity independently:

```bash
D=<group>/<package>/docs/code-issues
grep -rl 'applyOperations' "$D"                       # by symbol, wherever it now lives
grep -rl 'map-layer-service' "$D"                      # by file stem, ignoring the path
grep -rn 'Location:' "$D" | grep -i 'edit'            # by neighbourhood
git log --follow --oneline -3 -- src/services/map-layer-service.ts   # was this file renamed?
ls <group>/<package>/docs/changesets/ | tail -5       # did a restructure land recently?
```

A hit means **rename the existing file** to the new identity (`git mv`, so the history follows),
update its `Location`, and add a `**Moved:**` line saying where it came from and what moved it. It
does **not** mean a new file.

If the symbol is genuinely gone rather than moved, that is 7c, not a new file.

#### 7c. A finding that disappeared is not automatically fixed

When the tool stops reporting something the record has open, **do not resolve it on that basis
alone.** The measurement can vanish for reasons that are not a fix, and each has a different answer:

| Why it vanished | How to tell | Action |
|---|---|---|
| The code was genuinely fixed | the symbol is there, the numbers are good | **`git rm` the file.** The commit message carries the new measurement and what closed it |
| A coverage tier that ran last time did not run now | step 3 recorded fewer tiers than the file's `Metrics` names | **leave open**, and add a history row saying the run was not comparable. Resolving here is the worst outcome this skill can produce: it retires a real gap on a weaker measurement |
| The symbol moved | 7b's searches hit | **rename the file**, keep it open |
| The symbol was deleted | no references anywhere | **`git rm` the file**; the message says `code removed` |
| mypy / the authoritative pass could not run | step 5 said so | **leave open**; "not measured" is not "clean" |

A resolved issue's file is **deleted**, so a directory listing is always the open set. History lives
in git (`git log --diff-filter=D -- <path>`).

#### 7d. A regression is a new file that cites the deleted one

Fixed issues are deleted, so a returned issue finds no file. Before writing it as a first discovery,
check `git log --diff-filter=D --oneline -- '<package-dir>/docs/code-issues/<category>-<slug>*.md'`.
On a hit, write the new file with a `**Regressed:** <deleting commit> (<date>)` line and a line in
*Why it matters here* on what let it back in, if the run can tell. The fact that it was fixed once
and came back **is** the finding. Still exactly one file per symbol.

#### 7e. A category change supersedes; it does not fork

The same symbol can change category — a `missing-tests` symbol whose last production caller goes away
becomes `dead-code`; a `dead-code` symbol somebody wires up becomes `missing-tests`. Identity includes
the category, so this is a **new file** — but leaving the old one open would give the symbol two live
records that contradict each other.

Write the new file with `**Supersedes:** <old-filename> — <what changed>` and **delete** the old
one in the same commit. Exactly one file per symbol exists.

#### 7f. Update means add detail — it never overwrites judgment

When updating an existing file, tool output replaces tool output. **Human content is appended to, not
replaced.** This is the rule that makes the record worth re-reading:

| Field | On update |
|---|---|
| `Metrics`, `Location`, `Detected` tooling line | **overwrite** with the current run's values |
| `Measurement history` | **append a row.** Never rewrite or prune earlier rows — the trend is often the finding (a CRAP score climbing across three runs says the file is being actively made worse) |
| `What the tool found` | rewrite to the current measurement |
| `Verified by hand` | **append**, dated. Never delete an earlier verification: it records what the tool got wrong, which a fresh run cannot rediscover. If a new run contradicts it, add the contradiction and say which is right |
| `Why it matters here`, `What would close it` | **refine** when the run learned something — a seam identified, a consumer found, a blind spot confirmed. Leave alone when it learned nothing |
| `Restructure:` | change only with a stated reason. Flipping it to `required` makes the issue a planning prerequisite; flipping it away removes one |
| Anything a developer wrote by hand | leave it. If it is now wrong, add the correction next to it rather than deleting their reasoning |

**A run that learned nothing new writes nothing but a history row.** Rewriting prose to say the same
thing differently is churn a reviewer has to read and cannot verify, and it buries the one file that
did change.

#### 7g. File format

Full template and field semantics: the [`deferred-work` skill](../deferred-work/SKILL.md).

```markdown
# <category>: <symbol or file>

**Location:** `src/services/map-layer-service.ts:412` — `applyOperations`
**Category:** CRAP
**Detected:** YYYY-MM-DD by `code-analysis issues --path mapping-pipeline/mapping-pipeline-server`
**Metrics:** CRAP 2704 · complexity 52 · coverage 4% (unit+it+e2e merged) · 780 lines
**Restructure:** required — `split_file` + `extract_method`, `/code-restructuring` territory
**Status:** Open
<!-- optional, only when they apply -->
**Moved:** was `src/map-layer-service.ts` — relocated by the fill-flow split (PR #2231)
**Supersedes:** `missing-tests-apply-operations.md` — last production caller went away
**Regressed:** 4f2c9e1 (2026-07-02, PR #2104 deleted the record)

## Measurement history

| Run | CRAP | Complexity | Coverage | Lines | Tiers merged | Note |
|---|---|---|---|---|---|---|
| 2026-06-14 | 1980 | 44 | 6% | 610 | unit, it | first detection |
| 2026-08-01 | 2704 | 52 | 4% | 780 | unit, it, e2e | growing under active change |
| 2026-09-09 | 2704 | 52 | 4% | 780 | unit, it, e2e | unchanged |

## What the tool found
## Why it matters here
## What would close it
## Verified by hand
```

The **`Measurement history`** table is what makes an updated file worth more than a fresh one: a
score climbing across three runs says the code is being actively made worse, and no single
measurement can say that. Append a row per run — including the runs that found nothing changed, and
including a run whose tiers were not comparable (say so in the note rather than leaving a gap that
reads like a clean measurement).

Three fields carry the weight:

- **`Metrics`** must name **which coverage tiers were merged**. A CRAP or missing-tests number from
  one tier is not a finding, and "not measured" is not "clean" — say which tiers had no coverage
  script (step 3).
- **`Restructure: required`** is what turns a note into a **prerequisite**: the restructure has to
  happen before new code lands on top of it, and a different skill executes it. Set it only where the
  fix is a `/code-restructuring` job (a split, an extraction, a move) rather than ordinary work
  (adding tests, deleting a dead symbol).
- **`Verified by hand`** is **mandatory before the file is written**. Every analyzer here has known
  blind spots — dynamic dispatch, package `exports`, importers in other packages, name-occurrence
  matching in Python and Rust. Confirm the finding and say what the tool got wrong. **An unverified
  finding is a lead, not an issue**, and must not be filed as one.

Write a file per finding you verified, not per row the tool printed. A hundred low-CRAP rows are a
table in the targeting note; they are not a hundred files.

**This directory is the one carve-out to "never modify `{package}/docs/` directly".** It is a
generated analysis record, not documentation of behaviour — the same standing `{package}/docs/changesets/`
has. Everything else under `{package}/docs/` still goes through the changeset workflow.

#### 7h. Report the reconciliation, not just the findings

The run's summary says what happened to the **record**, because that is what a reader who has seen
this package before needs:

```
Code issues — mapping-pipeline/mapping-pipeline-server (12 open before this run)
  🆕 new           2   crap-fill-orchestrator, type-escapes-subasset-mapper
  📈 updated       3   crap-map-layer-service (1980 → 2704 over 3 runs), …
  ➖ unchanged     5   history row only
  ✅ deleted       1   missing-tests-page-index — covered by the new it suite (PR #2244); file removed
  ♻️ regressed     1   dead-code-legacy-loader — new file, cites the commit that deleted its record (2026-07-02)
  🔀 renamed       1   crap-apply-operations — moved by the fill-flow split
  ⚠️ not comparable 1  type-escapes-asset-mapper — mypy could not run; left open
```

Name explicitly anything **left open because the measurement was weaker than last time** — that is
the one case where a reader might otherwise assume the issue was cleared.

### 8. Hand off

Stop here. Do **not** start `code-restructuring` inside this skill.

- The **targeting note** goes to the developer, and into the restructure changeset when one follows.
- The **issue files** are now read by planning: `/plan-red` and `/plan-pr-stack` Step 2b scan every
  in-scope package's `<package-dir>/docs/code-issues/` and give each hit a verdict in the changeset's
  `## Prerequisites`. An issue marked `Restructure: required` becomes that changeset's
  **Restructure Prerequisite**, executed by `/green` before any implementation.

When this analysis runs as [`code-restructuring`](../code-restructuring/SKILL.md) step 1.5, the
targeting note goes into that restructure changeset and its Plan row carries on from here.

## CRAP formula

`CRAP = complexity² × (1 − coverage)³ + complexity`

Join key is `(file, declaration line)`, never function name. A covered function scores exactly its complexity.

## Dead code vs missing tests

Uncovered is not unused. `code-analysis dead-code` (also included in `issues`) joins unused-export
/ unused-member / unused-local checks to the CRAP function table and classifies each symbol:

| Bucket | Meaning | Action |
|---|---|---|
| **Dead** | No production refs, no test refs | Delete candidate — confirm by hand, record before deleting (`code-restructuring` step 2) |
| **Missing tests** | Production refs, not entered by any of unit / it / component / e2e | Add tests — do not delete |
| **Test-only** | Tests import it, production does not | Public API or test helper — check consumers |

TypeScript unused detection is syntactic (`createSourceFile`): export/import graph, unused locals,
and class-member reachability via `this.X` / `Class.X`. That last one is the linter blind spot
`noUnusedLocals` / `no-unused-vars` do not see. Python and Rust unused detection is name-occurrence:
a name that appears elsewhere is treated as referenced, so collisions are missing-tests rather than
dead.

For each finding, inspect before acting. Dynamic dispatch, package `exports`, and other packages'
imports are invisible to a `--path` scan. Missing-tests against a single `coverage/` directory
overstates the gap whenever another tier exercises the code — collect every coverage script the
package has.

## References

- [`deferred-work` skill](../deferred-work/SKILL.md) — the bar for deferring, and how planning
  consumes these records
- [The code-issue record](../deferred-work/references/code-issue-record.md) — file format, identity
  rules, reconciliation contract
- [`surmap` README.md](../../../README.md)
- [CRAP feature doc](../../../docs/architecture.md)
- [Rust coverage doc](../../../docs/architecture.md)
