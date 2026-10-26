# The code-issue record — `<package>/docs/code-issues/`

One analyzer finding against one symbol or file, written by
[`analyze-code-issues`](../../analyze-code-issues/SKILL.md). One file per verified finding, in the
docs of the package whose code it is about.

`<package>` is the package **directory**: a finding against `surmap` is written to
`mapping-pipeline/mapping-pipeline-server/docs/code-issues/`. Snippets below use `PKG` for that directory.

## Layout and filename

```
mapping-pipeline/mapping-pipeline-server/docs/code-issues/
├── crap-map-layer-service-apply.md
├── missing-tests-subasset-processing-service.md
└── oversized-file-session-replay-service.md

mapping-pipeline/stereo-ingest/docs/code-issues/
└── type-escapes-page-tree.md

src/surmap/surmap-server/docs/code-issues/
└── dead-code-legacy-loader.md
```

`docs/code-issues/` inside the package's own directory — **with** its group prefix, exactly as the
paths above: `mapping-pipeline/mapping-pipeline-server/docs/code-issues/`, never `mapping-pipeline-server/docs/`. The
npm scope (`@/`) never appears. Filename `<category>-<file-slug>[-<symbol>].md`. Categories mirror what the analyzers report: `crap`,
`missing-tests`, `dead-code`, `test-only`, `oversized-file`, `type-escapes`, `hot-file`,
`duplicate-tests`, and the one judged category, `non-fluent-tests` — a test suite below 7 on the
fluent rubric (below 8 and `**Priority:** 1` when the file is ≥ 500 lines — migrated before any
other item and before the file is split), one file per suite, its per-test score table as `Verified
by hand`, and its own attribution rule: on a pre-existing suite it is never the PR's that filed it
([`testing/references/fluent-style.md`](../../testing/references/fluent-style.md)).

**No date prefix, deliberately — unlike a TODO.** A code issue is a **standing property of the
code**, not an event: re-running the analyzer must find and update the file that already names that
symbol rather than deposit a second copy of the same finding. The identity is
`(category, file, symbol)`, and the filename encodes it.

**No index.** The listing is the index.

## Template

```markdown
# <category>: <symbol or file>

**Location:** `src/services/map-layer-service.ts:412` — `applyOperations`
**Category:** CRAP
**Detected:** YYYY-MM-DD by `code-analysis issues --path mapping-pipeline/mapping-pipeline-server`
**Metrics:** CRAP 2704 · complexity 52 · coverage 4% (unit+it+e2e merged) · 780 lines
**Restructure:** required — `split_file` + `extract_method`, `/code-restructuring` territory
**Status:** Open (a record exists only while the issue is open — fixing it deletes the file)
<!-- only when they apply -->
**Moved:** was `<old path>` — relocated by <what moved it>
**Supersedes:** `<old-filename>` — <what changed about the category>

## Measurement history

| Run | CRAP | Complexity | Coverage | Lines | Tiers merged | Note |
|---|---|---|---|---|---|---|
| 2026-06-14 | 1980 | 44 | 6% | 610 | unit, it | first detection |
| 2026-08-01 | 2704 | 52 | 4% | 780 | unit, it, e2e | growing under active change |
| 2026-09-09 | 2704 | 52 | 4% | 780 | unit, it, e2e | unchanged |

## What the tool found

<The measurement, and which coverage tiers were merged to get it. "Not measured" is not "clean" —
say which tiers had no coverage script.>

## Why it matters here

<What breaks, or breaks silently, while this stands. A CRAP number is not a finding on its own; the
finding is that this function is where behaviour changes go and nothing catches a mistake.>

## What would close it

<Concretely: add tests for X (missing-tests — never delete), delete Y after a find-references check
(dead-code), split at the seam between A and B (oversized). Say whether it is a
`/code-restructuring` job or ordinary work, because that decides where it lands in a changeset.>

## Verified by hand

<MANDATORY before the file is trusted as a prerequisite. Every analyzer has known blind spots —
dynamic dispatch, package `exports`, cross-package importers, name-occurrence matching in Python and
Rust. Say what you checked and what the tool got wrong. An unverified finding is a lead, not an
issue.

APPEND on re-analysis, dated; never delete an earlier verification. It records what the tool got
wrong, and a fresh run cannot rediscover that. If a later run contradicts it, add the contradiction
and say which is right.>
```

## The three fields that carry the weight

- **`Metrics`** must name **which coverage tiers were merged**. A CRAP or missing-tests number from
  one tier is not a finding, and "not measured" is not "clean".
- **`Restructure: required`** is what turns a note into a **prerequisite**: the restructure has to
  happen before new code lands on top of it, and a different skill executes it. Set it only where the
  fix is a `/code-restructuring` job (a split, an extraction, a move) rather than ordinary work
  (adding tests, deleting a dead symbol). See
  [`planning-cross-check.md`](planning-cross-check.md).
- **`Verified by hand`** is **mandatory before the file is written**. An unverified analyzer row is a
  lead, not an issue, and must not be filed as one.

**`Measurement history`** is what makes an updated file worth more than a fresh one: a score climbing
across three runs says the code is being actively made worse, and no single measurement can say that.
Append a row per run — including runs that found nothing changed, and runs whose tiers were not
comparable (say so in the note rather than leaving a gap that reads like a clean measurement).

## Re-analysis reconciles; it never duplicates

`/analyze-code-issues` reads this record **before** running anything and matches every finding
against it **before** writing. Duplicate issue files are the failure mode that reconciliation exists
to prevent: two files describing the same function, with different numbers, only one carrying the
hand-verification note, and no way to tell which is current.

The mechanics live in [`analyze-code-issues`](../../analyze-code-issues/SKILL.md) steps 1.5 and
7a–7h. The four rules worth knowing from here:

| Situation | Rule |
|---|---|
| The identity **moved** (file or symbol renamed, or relocated by a restructure) | match by **symbol and file stem independently**, not by filename — a filename lookup calls every moved issue "new". A hit means `git mv` plus a `**Moved:**` line |
| The tool **stopped reporting** it | not automatically fixed. Confirm the *code* changed. Fewer coverage tiers than last run means **not comparable**, not clean — leave it open and say so |
| A finding matches an issue a **deleted** record once held (`git log --diff-filter=D -- <path>`) | **new file** with `**Regressed:** <commit that deleted the record> (<date>)`. That it was fixed once and came back *is* the finding |
| The symbol changed **category** | new file with `**Supersedes:** <old-filename>`, and the old file **deleted**. Exactly one file per symbol exists |

## Partial resolution — the state that gets mis-recorded

A changeset that improves an issue without closing it leaves the record **open**, updated:

- a `Measurement history` row with the improved numbers and the PR that moved them;
- *What would close it* rewritten to name **only the remainder**;
- the file **kept** — deleting it would hide the remainder.

```markdown
| 2026-09-20 | 1180 | 31 | 44% | 310 | unit, it, e2e | PR #2401 split the orchestrator; `mergeSubassets` still uncovered |
```

**A partial fix whose file is deleted is worse than no fix recorded at all.** The file leaves the
directory, so the next planner's Step 2b never sees the remainder — and the metrics in the
record now understate the real risk. Equally, leaving *What would close it* describing the original
gap makes them re-plan work already done: the history goes in `Measurement history`, the remainder
goes in the prose.

`/green` step 3.5b writes this, `/pr-wrap` step 7.5b verifies it against the changeset's **Outcome**
column (`◐ Partly`), and `/wrap-context-docs` step 7b is the last chance to get it right — after
that the changeset is deleted and the mapping is gone.

**An update overwrites measurements and appends judgment.** Tool output (`Metrics`, `Location`, the
`Detected` line, *What the tool found*) is overwritten. `Measurement history` gains a row and is never
pruned. *Verified by hand* and anything a developer wrote are appended to, never replaced — if it is
now wrong, put the correction next to it rather than deleting the reasoning. A run that learned
nothing writes nothing but a history row.

## Querying

```bash
# every package that has been analyzed at all
ls -d */*/docs/code-issues 2>/dev/null

PKG=mapping-pipeline/mapping-pipeline-server
ls "$PKG/docs/code-issues/"                              # one package's findings

# still open, repo-wide — the glob is the index, so no directory list to maintain
ls */*/docs/code-issues/ 2>/dev/null
grep -rl 'Restructure:\*\* required' */*/docs/code-issues/ 2>/dev/null | \
  xargs ls                                                 # a restructure job
grep -rl 'map-layer-service' */*/docs/code-issues/        # findings against a file you will edit
grep -rl 'applyOperations' */*/docs/code-issues/         # by symbol, wherever it now lives
```

**There is no closed state.** A fully resolved issue's file is deleted in the fix commit, so every
file listed is open. Open-items queries written as `grep -L 'Status:\*\* Resolved'` still work and
match every file. Closed history is `git log --diff-filter=D -- <package>/docs/code-issues/`.

**A package with no directory here has not been analyzed** — that is not the same as clean. Say so in
the changeset, and run `/analyze-code-issues` when the change lands in code the analyzers would have
something to say about.

## Referencing a code issue from a changeset

Use the path in backticks, **not** a Markdown link — same reason as for a TODO
([`todo-record.md`](todo-record.md)): a code issue is renamed whenever the symbol it names moves, so a
Markdown link rots silently where a backticked path reads as the identifier.

```markdown
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md` | ⛔ Blocking | Restructure prerequisite below |
```
