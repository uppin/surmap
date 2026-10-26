# The TODO record — `<package>/docs/todo/`

Work a changeset planned or discovered and **could not** finish. One file per item, in the docs of
the package the work would land in.

Read [`../SKILL.md`](../SKILL.md) first — it carries the four-gate bar for deferring **planned**
scope at all (impossible not merely expensive · every route around it wrong · developer consented ·
what remains still ships coherently). This page is the format.

Snippets below use `PKG` for the package **directory** — `mapping-pipeline/mapping-pipeline-server`, not
`surmap`.

## Which package owns the file

The one the deferred work would **land in**. A code issue names a file, so its package is obvious; a
deferral often is not, and can constrain two packages at once.

- One file, under the owning package, always.
- **Every** affected package goes in `**Packages:**`, including the owner.
- Never copy the file into a second package. Two copies drift, and the second one is the copy nobody
  updates when the item is resolved.

That `**Packages:**` line is load-bearing rather than informational: planning Step 2b lists its own
packages' directories, and finds an item filed under a *different* package only by grepping for its
package names. Omit a package there and the record is invisible to the planner it was written for.

## Filename

`YYYY-MM-DD-<short-slug>.md` — the date the item was deferred or found. If the name is taken, append
`-2`.

The date prefix sorts the directory, and it is there because **a TODO is an event**: it happened on a
day, and a second deferral of the same area is a second file, never an edit to the first.

**Never add a second item to an existing file.** That is the shared append-point this layout removes
— two branches recording a finding in the same merge window would edit the same lines and conflict.
Editing a file to update *its own* item — a `**Status:**` change, a `**Progress:**` line, a narrowed
*What is left* — is a different thing, and it is required.

## Template

```markdown
# YYYY-MM-DD — <what is left undone>

**Category:** Deferred scope | Future enhancement | Known failing test | Blocked externally | Overridden answer
**Source:** `docs/<area>/1-WIP/YYYY-MM-DD-<changeset>.md` (PR #NNNN, stack `#<slug>` node K/N)
**Packages:** surmap, surmap
**Consent:** <the developer's own words agreeing to defer, and when> — or `n/a — future enhancement`
**Status:** Open

## What is left

<The remaining work, concretely enough that someone can pick it up: files, symbols, the behaviour
that is missing.>

## Why it could not be done now

<The blocker. Not "out of scope" — the thing that made it impossible. Name the routes around it and
why each is wrong. This paragraph is what tells the next planner whether it blocks them, and it is
the only reason the file is worth keeping.>

## What was done instead

<The state the code is actually in, so nobody reads the gap as an oversight. Where a marker was left
in code, give `file:line` for each `TODO`/`FIXME`.>

## When it becomes possible

<The signal to watch: a package republished, a scope registered, a predecessor PR merged, a decision
made. For a stack-internal deferral this is usually "when PR #NNNN lands" — say so, because
`/fix-pr-stack`'s Wave 1 reads this line to decide whether the landing itself unblocks the item.>
```

## Categories

| Category | Means | Consent required |
|---|---|---|
| `Deferred scope` | the changeset planned it and did not deliver it | **yes** — the four gates apply |
| `Future enhancement` | never in the changeset's scope; an idea worth keeping | no |
| `Known failing test` | a test that fails for a reason outside this changeset's control | no, but name the reason |
| `Blocked externally` | waiting on something no one in this repo controls | no, but name what and who |
| `Overridden answer` | the developer overrode a deferred answer (`deferred-answer-record.md`) and the code built on the old pick still has to change | the developer's answer **is** the consent. Quote it, and cite the deleted record's path |

`Deferred scope` without a `**Consent:**` line is an invalid record — the deferral is a silent scope
cut, and the right move is to finish the work or raise it, not to file the file.

## Lifecycle

Delete a resolved item's file in the commit that resolves it (`git rm`), saying in the commit
message and the PR body what closed it. The history stays in git
(`git log --diff-filter=D -- <path>`), and the directory listing stays an honest list of open work.
There is no `Resolved` status.

An item whose blocker cleared but whose work is still outstanding stays **open**, with a note:

```markdown
**Status:** Open — unblocked 2026-09-14 by PR #2390
```

An item a changeset **partly** addressed also stays **open**, with a `**Progress:**` line — and its
*What is left* section rewritten to describe **only the remainder**:

```markdown
**Status:** Open
**Progress:** 2026-09-20, PR #2401 — the analyzer port is wired for the native path; the ML path
still falls through to the old helper.
```

Both distinctions are what `/fix-pr-stack` Wave 1, `/merge-pr-stack` Wave 4, and the next planner's Step 2b act on.

**Narrowing *What is left* is the half people skip.** Leaving it describing the original gap makes
the next planner re-plan work that is already done; the history belongs in the `**Progress:**` line,
not in the section that says what remains. And a partly-addressed item whose file is deleted as if
resolved is worse than one never touched: the remainder is lost.

## Who writes what, and when

| Phase | Writes |
|---|---|
| planning (Step 2b) | nothing here — it *reads*, and records a verdict + disposition in the changeset's `## Prerequisites` |
| `/green` step 3.5 | the changeset's **Outcome** cell first, then this record: closed, updated with `**Progress:**`, or left alone. New files for anything deferred |
| `/pr-wrap` step 7.5 | gates that every Outcome cell is filled and that each record matches it |
| `/wrap-context-docs` step 7b | acts on the Outcome column **before the changeset is deleted** — closes ✅, narrows ◐, confirms ⛔ |
| `/pr-wrap` step 7.6 | lists every unresolved TODO and code issue **this PR added**, and waits for the user to decide how to plan solving them |
| `/fix-pr-stack` Wave 1 | assesses every TODO and code issue the stack added, and plans with the user to **rescope an existing PR** or **add PR(s) at the tail** |
| `/merge-pr-stack` Wave 4 | re-verifies blockers after landing and executes leftover opt-out dispositions |

The changeset is deleted at wrap, so its Outcome column is the **only** place the mapping from a
change to the records it touched is ever written. That is why `/pr-wrap` refuses to wrap while a cell
is blank.

## Querying

There is no index — deliberately, for the same reason `docs/<area>/1-WIP/` has none. The directory
listing **is** the index, and the date prefix sorts it.

```bash
PKG=mapping-pipeline/mapping-pipeline-server
ls "$PKG/docs/todo/" | sort -r | head -20                  # one package, most recent first

# repo-wide: the glob replaces the single directory the flat layout gave for free
ls -d */*/docs/todo 2>/dev/null                            # packages carrying any TODO
ls */*/docs/todo/ 2>/dev/null                              # still open, everywhere
grep -rl 'Category:\*\* Deferred scope' */*/docs/todo/      # cut scope, not enhancements
grep -rl -F '#<stack-slug>' */*/docs/todo/                 # everything one stack deferred
grep -rl -iE '(subasset|analyzer|pageNumber)' */*/docs/todo/  # anything touching a module

# items OWNED elsewhere that name your package — the scan a per-package listing misses
grep -rl -F 'surmap' */*/docs/todo/
```

## This record is read, not only written

Planning **Step 2b** ([`planning-cross-check.md`](planning-cross-check.md)) scans it before a
changeset is written, `/pr-wrap` step 7.6 lists what this PR added, and `/fix-pr-stack` Wave 1
assesses what the stack added and plans with the user to rescope an existing PR or add tail PRs.
An item sitting in the
path of new work is found at planning time rather than during `/green` — where the only choices left
are to work around it, make it worse, or stop.

The two directions are complementary: what one change defers is what the next planner's scan finds.
That is why the *why it could not be done* paragraph matters more than the *what is left* one.

## Referencing a TODO from a changeset

Use the path in backticks, **not** a Markdown link:

```markdown
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-08-14-analyzer-fallback.md` | ⛔ Blocking | Fixed here — see Scope |
```

Both live in the docs tree now, so a link would resolve — but the changeset is **deleted at wrap**
while the record outlives it, and a record is renamed when what it names moves. A link encodes a
relationship between two files with different lifetimes; a backticked repo-relative path is
copy-pasteable and states the identity without implying the link.
