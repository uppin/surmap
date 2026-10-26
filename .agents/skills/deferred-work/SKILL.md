---
name: deferred-work
description: >-
  The file-per-item records this repo keeps for work it did NOT do and decisions nobody reviewed — changeset TODOs and code issues in the docs of the package they describe (`<package>/docs/todo/`, `<package>/docs/code-issues/`), and deferred answers, the questions a `#yolo` run decided instead of asking (`docs/<area>/deferred-answers/` for Product, `<package>/docs/deferred-answers/` for Technical). Defines when deferring is legitimate at all (the bar is high: the goal of a changeset is its full planned scope), the record formats, how planning cross-checks both as changeset prerequisites, the restructure-before-green contract, and how records are closed. Use when planning a changeset or a PR stack, when something cannot be finished, when persisting `/analyze-code-issues` output, when a `#yolo` run would have asked a question, or when landing a stack.
---

# Deferred Work — TODOs, Code Issues and Deferred Answers

Three records, one file per item, all read as often as they are written, and all **in the docs of
what they describe** — so a record travels with the code it is about, and someone reading a
package finds its open debt without knowing this skill exists.

```
<package>/docs/                       ← e.g. src/surmap/surmap-server/docs/
├── code-issues/                      ← THE RECORD: analyzer findings, one file per issue
│   └── <category>-<file-slug>[-<symbol>].md
├── todo/                             ← THE RECORD: deferred work, one file per item
│   └── YYYY-MM-DD-<slug>.md
└── deferred-answers/                 ← THE RECORD: a Technical question #yolo decided, one per file
    └── YYYY-MM-DD-<slug>.md

docs/<area>/deferred-answers/         ← THE RECORD: a Product question #yolo decided, one per file
└── YYYY-MM-DD-<slug>.md

.agents/skills/deferred-work/         ← the rules, not the records
├── SKILL.md                          ← you are here: the bar, the paths, the rules
└── references/
    ├── todo-record.md                ← TODO file format, categories, lifecycle
    ├── code-issue-record.md          ← code-issue file format, identity, reconciliation
    ├── deferred-answer-record.md     ← deferred-answer file format, Product vs Technical, review
    └── planning-cross-check.md       ← Step 2b: verdicts, right-sizing, restructure prerequisite
```

`<package>` is the package's **directory**, not its npm name: a record for `surmap`
lives at `mapping-pipeline/mapping-pipeline-server/docs/code-issues/`. Shell snippets throughout use
`PKG=<the package directory>`, so the two record directories are `$PKG/docs/todo/` and
`$PKG/docs/code-issues/`.

| Record | Path | One file is | Written by | Read by |
|---|---|---|---|---|
| **Changeset TODO** | `$PKG/docs/todo/` | one thing a changeset planned or discovered and **could not** finish | `/green`, `/plan-red`, `/plan-pr-stack`, `/pr-wrap`, `/fix-pr-stack` | planning Step 2b, `/fix-pr-stack` Wave 1, `/pr-wrap` step 7.6 |
| **Code issue** | `$PKG/docs/code-issues/` | one analyzer finding against one symbol or file | `/analyze-code-issues` | Step 2b, `/code-restructuring` step 1.5 |
| **Deferred answer** | `$PKG/docs/deferred-answers/` (Technical), `docs/<area>/deferred-answers/` (Product) | one question a `#yolo` run decided instead of asking: the options, the asker's pick, the supervisor's review, what was built on it | any command under `#yolo` (`behaviour-modifiers` skill) | the developer, Step 2b, the summary and PR body |

Neither directory has an index. The directory listing **is** the index — an index file is a shared
append-point, so every branch that recorded a finding would edit the same lines and conflict on
merge. Same reason `docs/<area>/1-WIP/` and `{package}/docs/changesets/` have none.

**A TODO is owned by one package, and says which others it touches.** A code issue is per-package by
construction — it names a file. A deferral often is not: it can constrain two packages at once. The
owning package is the one the deferred work would land in, and every affected package is named in
the record's `**Packages:**` line. That line is load-bearing now rather than informational: Step 2b
finds a TODO filed under another package **only** by grepping for its own package names, so a
missing `**Packages:**` entry hides the item from the planner it was written for.

## The rule that comes before every format

**A changeset's goal is the full scope that was planned.** The PRD and the changeset are the
contract. A TODO file is not a scope-reduction lever, not a way to end a session tidily, and not
somewhere to park the part that turned out to be hard.

Before writing a TODO for **planned** scope, the deferral must pass **all four**:

1. **It is impossible now, not merely expensive.** Name the thing that makes it impossible. If the
   sentence you write is "this would take a while", it fails.
2. **Every route around it is wrong.** Name the two or three ways you could proceed and say why each
   is *incorrect* rather than inconvenient.
3. **The developer consented.** You asked, in this session, and they agreed to defer. Record their
   words. An unconsented deferral of planned scope is a silent scope cut, which is the failure this
   record exists to make impossible.
4. **The remaining scope still ships something coherent.** A changeset whose deferral leaves a
   half-wired feature is not deferred, it is broken — finish it or stop and ask.

Legitimate blockers, concretely:

- an external dependency that does not exist yet — an unpublished `surmap*` type, an
  unregistered permission scope, another team's endpoint, a proto not yet republished;
- a decision only the developer can make, which they were asked for and postponed;
- a predecessor PR in the same stack that is still a stub (the stack's own sequencing);
- work that would require breaking a boundary this repo enforces — implementing a symbol another
  stack node owns, adding a fallback, adding a test-environment branch to production code;
- infrastructure that does not exist — a missing coverage tier, an unbuilt harness, a toolchain gap.

**A finding is not a TODO.** An oversized file, an untested complex function, dead code, a type
escape: these are analyzer findings and live in `$PKG/docs/code-issues/`, written by
`/analyze-code-issues`. Never file one as a `docs/todo/` entry, and never invent a TODO category
("Deferred split") to hold it.

**Not** legitimate, and this list is the whole point of the section: it is hard; it is slow; the
tests are flaky; the file is enormous; the session is running long; it is polish; "we can do it in a
follow-up". Those are descriptions of the work, not obstacles to it.

> A deferral of something the changeset never planned is not a deferral at all — it is a
> **future enhancement**, and those are welcome. Write them freely with
> `**Category:** Future enhancement`; rules 1–4 govern *planned scope* only.

## The three records

- **[`references/todo-record.md`](references/todo-record.md)** — the TODO file: filename, template,
  categories, consent, deleting on resolution, and the query cookbook.
- **[`references/code-issue-record.md`](references/code-issue-record.md)** — the code-issue file:
  identity-based naming, template, measurement history, and why re-analysis reconciles instead of
  duplicating.
- **[`references/deferred-answer-record.md`](references/deferred-answer-record.md)** — the
  deferred-answer file: Product vs Technical and where each lives, template (options as asked,
  supervisor review, what was built on it), and review — confirmed, overridden, superseded.

**A deferred answer is not a deferral of scope.** It is a decision that was made and built on,
waiting to be reviewed. It never stands in for the developer's consent to cut planned scope (the
four gates below), which stays a ⛔ halt under `#yolo` too.

Why the two naming conventions differ, since it looks like an inconsistency otherwise:

| | Changeset TODO | Code issue |
|---|---|---|
| Filename | `YYYY-MM-DD-<slug>.md` | `<category>-<file-slug>[-<symbol>].md`, **no date** |
| Because | a deferral is an **event** — it happened on a day, and a second deferral in the same area is a second file | a finding is a **standing property of the code** — re-running the analyzer must update the file that already names that symbol |
| Sorted by | the date prefix | category, then location |

**A record exists only while its item is open.** All three are **deleted** when the item is fully
resolved: `git rm` the file in the commit that fixes it, say what closed it in that commit's message
and the PR body, and let git keep the history (`git log --diff-filter=D -- <path>`). There is no
`Resolved` state: a file in the directory is open work, so the directory listing is the open-items
list. A partly-addressed item stays, updated (see the rules below).

## Reading both records at planning time

Planning reads these **after** the code analysis, once you know which files and modules the change
touches, and **before** the changeset is written. Discovering an item during `/green` is late: by
then the only choices are to work around it, silently make it worse, or stop.

**[`references/planning-cross-check.md`](references/planning-cross-check.md)** is that step — the
scan commands, the verdict table (⛔ blocking / ⚠ during / ℹ answered / — unrelated), how to
right-size each fix, the **restructure prerequisite** contract that `/green` executes before any
implementation, and what to do when a restructure spans a whole PR stack.

It also covers the **other** source of a restructure prerequisite: not a record at all, but the
planner noticing that the structure as it stands would make this change harder or riskier —
**softening the ground**. That one is *suggested to the developer and never decided*, must be
justified by a named difficulty in this change rather than by tidiness, and if declined gets filed
(a code issue if measurable, else a `Future enhancement` TODO) so it is not re-proposed as new next
session. On a stack (`/plan-pr-stack`), an **approved** ground-softening or shared-code fix is a
**stack node** — never a PR this command opened that is not in the stack.

## What these records are **not**

| Not this | That is |
|---|---|
| the TODO record | `/tech-backlog` — GitHub issues labelled `tech-backlog`, for long-lived technical work nobody has planned. A TODO is a specific gap left by a specific changeset |
| the TODO record | an open TODO nested under a changeset's Green row — work `/green` **must** do once the implementation exists. Those are held, not deferred, and `/green` works through them |
| the TODO record | `TODO(pr-<k>)` stub markers — a planning stub the owning stack node implements in its own `/green` |
| the code-issue record | `/analyze-clean-code` — the LLM heuristic pass at PR-wrap. Complementary; a code-issue file is tool-measured and carries numbers |
| the deferred-answer record | **Decided without review** in a summary — a choice a review gate used to show (a cleanup, a split). A deferred answer is a question the developer would have been *asked* |
| any record | a place to record something you have not told the developer about |

## Rules

- **Full planned scope is the deliverable.** A TODO for planned scope needs a named blocker, refuted
  alternatives, and recorded developer consent. Without those, finish the work.
- **One file per item, and one item per file.** Never add a *second item* to an existing file — that
  is the shared append-point this layout removes. It is **not** a rule against editing a record:
  updating an item's **own** file is required, and a code issue's `Measurement history` and
  `Verified by hand` sections are explicitly append-only across runs. New item → new file; new
  information about an existing item → edit that item's file.
- **No index**, in either record. The listing is the index.
- **State *why*, not only *what*.** The blocker paragraph is what the next planner's Step 2b acts on;
  a TODO without one is unusable and should not be written.
- **Verify a code issue by hand before treating it as a prerequisite.** Every analyzer has blind
  spots; an unverified finding is a lead.
- **Re-analysis reconciles; it never duplicates.** One open code-issue file per symbol, ever.
- **Missing-tests is never a delete.** Those symbols are referenced from production.
- **Step 2b is mandatory in planning**, and every relevant item gets a verdict in the changeset's
  `## Prerequisites` — including the ones you decide not to fix.
- **A restructure prerequisite runs before green, in its own commit, and implements nothing.**
- **A ground-softening restructure is suggested, never decided.** Justify it by a named difficulty in
  the change at hand, measure its blast radius before proposing, and record the observation if the
  developer declines.
- **Never absorb a large restructure into a feature change or a feature stack node.**
- **Delete a record when it is fully resolved; never mark it `Resolved`.** The fix commit carries
  the `git rm`, so the record cannot outlive its item. A leftover `Resolved` file is a defect: it
  reads as open work to every scan. (Open-items queries that exclude `Status:** Resolved` stay
  correct, because no file carries the token any more.)
- **Record a partial fix as partial.** The record stays open, gains the improved numbers, and has its
  *What is left* / *What would close it* narrowed to the remainder. A partial fix deleted as
  if resolved hides the remainder from the next Step 2b — worse than not recording it at all.
- **`/green` writes the outcome into the changeset, not only into the record.** The changeset's
  `## Prerequisites` → `Outcome` column is the only place the mapping from a change to the records it
  touched exists, and the changeset is deleted at wrap — which is why `/pr-wrap` gates on it and
  `/wrap-context-docs` reads it before deleting.
- **Wrap deletes the records the changeset resolved, and only those.** Unlike
  `docs/<area>/1-WIP/`, which wrap empties, these files are package documentation: a wrap removes
  exactly the ones its Outcome column marks ✅ Resolved and leaves every other record alone.
- **A deferred answer is closed only by the developer's answer**, given when asked
  (`/review-deferred-answers`, or an interactive plan's interview). The record is deleted whatever
  the answer: confirmed, or overridden, in which case the code left to change becomes an
  `Overridden answer` TODO in the same commit. No command deletes one on its own judgment, except a
  superseded one, and wrap leaves them alone.
- **These records are the one thing `/analyze-code-issues`, `/green` and a `#yolo` run may write
  into `<package>/docs/` (and, for a Product deferred answer, `docs/<area>/deferred-answers/`)
  directly.** Everything else under a package's `docs/` goes through the changeset
  workflow in `docs/<area>/1-WIP/` (README.md's rule). A record is not prose about how the code works —
  it is a standing measurement with its own reconciliation contract, and routing it through a
  changeset would tie a record's life to a changeset's instead of to its item's.
- **A comment that cites a deleted record is read through git.** Source comments, `README.md` files and
  changesets name records by path, and a resolved record's path stops resolving. That is expected:
  `git log --diff-filter=D -- <path>` finds the commit that deleted it and its message says what closed
  it. Do not resurrect a record to satisfy a citation.
- **Refer to a record by its path in backticks, not a Markdown link.** Both trees are versioned
  together now, so a link would resolve — but a code issue is *renamed* when the symbol it names
  moves, and a link would rot silently where a backticked path reads as the identifier it is.

## Related

**Commands**: `/yolo`, `/yolo-pr-stack`, `/review-deferred-answers`, `/plan-red`, `/plan-pr-stack`, `/green`, `/pr-wrap`, `/fix-pr-stack`, `/add-to-pr-stack`,
`/merge-pr-stack`,
`/analyze-code-issues`, `/wrap-context-docs`, `/tech-backlog`
**Skills**: [`behaviour-modifiers`](../behaviour-modifiers/SKILL.md) (`#yolo`), [`analyze-code-issues`](../analyze-code-issues/SKILL.md),
[`code-restructuring`](../code-restructuring/SKILL.md), [`pr-stack`](../pr-stack/SKILL.md),
[`planning`](../planning/SKILL.md)
**References**: [`planning-phase.md`](../planning/references/planning-phase.md) Step 2b,
[`pr-lifecycle/references/changeset.md`](../pr-lifecycle/references/changeset.md) §2.5,
[`pr-lifecycle/references/restructure.md`](../pr-lifecycle/references/restructure.md)
