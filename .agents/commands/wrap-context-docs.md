---
description: Transfer knowledge from changesets/PRDs into documentation, wrap completed work
---
## Wrap Context Documentation

Transfer knowledge from changesets and PRDs into actual documentation. Use after implementation work is done.

## When Invoked

1. **Find relevant documentation**:
   - Changesets: `docs/<area>/1-WIP/`
   - PRDs: `docs/*/1-WIP/`
2. **Update or wrap** based on status.

## A procedure, not a row

`/pr-wrap` runs this as its step 8; it is not a `## Workflow` row of its own. Its stops — an Outcome still `(filled by /green)`, an open TODO under a row other than Wrap
with no deferred-work record, an incomplete changeset (*When Wrapping is Blocked*) — are reported to the caller, which halts
its Wrap row ⛔ with them (`.agents/skills/pr-lifecycle/SKILL.md` § *Halts*). Invoked by
hand, it reports the same stops and ends.

Wrapping deletes the changeset, and its `[wf]` rows go with it. That is expected, not a
missing section: the caller carries the rows forward — into the wrap commit's message and the PR
body (`/pr-wrap` step 8). Wrap is the last row, so that copy is final.

## Core Principle: Transfer Knowledge, Not Just References

**"Wrapping" means:**
1. **Extract final state** from changeset/PRD
2. **Update actual documentation** with new content (feature docs, dev docs)
3. **Write a history file** as audit trail

**NOT:**
- Only writing a changelog/changesets history file
- Leaving feature/dev docs unchanged
- Creating links to archived PRDs/changesets

### What "Apply to Target Docs" Means

**NOT just writing a history file.** You must:

1. **Read and understand** the changeset/PRD completely
2. **Extract final state** (State B) — what the docs SHOULD say after wrapping
3. **Find merge points** — which sections in target docs need updates
4. **Transform content** — convert changeset/PRD language to final-state language
5. **Merge intelligently** — replace, add, enhance, or remove sections
6. **Update the actual feature/dev docs** with the new content
7. **THEN** write a new per-entry history file as an audit trail (never append to a shared file)

## History files (one file per wrap)

Do **not** append to a shared `changelog.md` or `changesets.md`. Parallel branches conflict on those
files on every wrap. Each wrapped PRD or changeset is its **own file** under the current docs
directory:

| Kind | Path |
|------|------|
| Feature (PRD) | `docs/{product-area}/changelog/YYYY-MM-DD-short-description.md` |
| Package (changeset) | `{group}/{package}/docs/changesets/YYYY-MM-DD-short-description.md` |

**Filename**: ISO date of the wrap, then a kebab-case slug that names the change (what landed, not
`update` or `fix`). Must be unique in that directory.

**Changelog entry** (`docs/{product-area}/changelog/`):

```markdown
# {Title}

**Date:** YYYY-MM-DD
**Feature:** {Feature name}

{release-note body in past tense}

**Deferred answers** — decided under `#yolo`, awaiting review at wrap:
- `docs/{product-area}/deferred-answers/YYYY-MM-DD-<slug>.md` — {question} → {decision}
```

**Changeset history entry** (`{package}/docs/changesets/`):

```markdown
# {Title}

**Date:** YYYY-MM-DD
**Type:** Feature | Bug Fix | Refactor | Architecture Change
**Packages:** surmap

{release-note body in past tense}

**Deferred answers** — decided under `#yolo`, awaiting review at wrap:
- `{group}/{package}/docs/deferred-answers/YYYY-MM-DD-<slug>.md` — {question} → {decision} ({asker | supervisor})
```

The **Deferred answers** block appears only when the changeset had a `## Deferred Answers` section
(step 7c). **Product** records go in the product area's changelog entry, and **Technical** records
go in the history entry of the package that owns them. Paths are backticked, never linked. The entry
is never revised, so a later review does not touch it. The commit that deletes the record says
whether it was confirmed or overridden, and `git log --diff-filter=D -- <path>` finds it.

Never maintain an index that lists every entry — that reintroduces the conflict. Directory order by
the `YYYY-MM-DD-` prefix is the chronology. Skip writing the file only when a Wrap-row TODO
already created it.

### A history file is terminal — nothing links to it

**No stable document may reference an individual history entry.** Not `1-OVERVIEW.md`, not a feature
document, not a package `README.md`, `README.md` or dev doc. That means no `See
[changelog/2026-…](…)` trailer on a paragraph, no `**Implementation**: see [changelog](…)` line, no
`([changelog](…))` parenthetical, no "Change History" / "Related changesets" list, and no entry in
`## Product Area Documents`.

**A bare path counts.** ``- Package history: `…/docs/changesets/2026-09-14-x.md` `` names the same
immutable delta a markdown link would; the backticks change nothing about where it sends the
reader. The test is what the reference *points at* — one dated entry — never how it is spelled.

The reason is what a history file *is*: a dated record of one delta, written once and never revised.
A stable doc states the **current** behaviour. A link from the second to the first invites the
reader to reconstruct today's truth from a pile of deltas, and it rots — an entry describing
behaviour that three later entries replaced still reads as current to whoever follows the link. If
a fact in a history entry still matters, **the fact belongs in the stable doc, stated in State B**;
the link is what you write instead of doing that work.

Directory pointers are the one exception: a single `- [changelog/](./changelog/) — change history`
line in a product area's document list is structure, not a reference, and stays.

Links run one way — a history entry may cite PRs, stable docs and other history entries freely.

## Update Documentation (`/update-context-docs`)

### Row TODOs

The only checkboxes in a changeset are the TODOs nested under its `[wf]` rows (`  - [ ]` open,
`  - [x]` done — no `[~]`): milestones, Scope deliverables and acceptance tests under Green (or the
kind's implementing row), wrap obligations under Wrap. They are ticked as the work completes them
(`.agents/skills/pr-lifecycle/SKILL.md` § *Workflow rows*):

```bash
grep -E '^(- \[wf |  - \[[ x]\] )' "$cs"
```

## Prerequisites for Wrapping

**ALL must be true:**
- **The PR is being set ready for review** (or already is). This is the wrap trigger — see below.
- No open TODO under any row before Wrap, or each open one carrying its deferred-work record
- All acceptance criteria met
- Status changed to Complete

### When wrapping happens
A stacked PR has no extra document to worry about: its stack context is a section of its own
changeset, so it is wrapped and deleted with it. There is no shared manifest to hand on, and a wrap
never touches another branch.



**Wrap at the moment the PR is set ready for review** — the changeset's Wrap row (`/pr-wrap`). Two
things this rules out:

- **Not while the PR stays a draft.** Draft means the work is still moving; its changeset belongs in
  `docs/<area>/1-WIP/` where the next session can pick it up. Wrapping early deletes the working
  document and hands reviewers docs for something still changing.
- **Not deferred to after merge.** By then the PR has been reviewed against a changeset describing a
  delta rather than the feature docs the change produced, and the wrap becomes a separate chore that
  is easy to forget.

Readying the PR is the signal that the work is final enough for its knowledge to move into the
permanent documentation.

In a **stack**, ready and wrap **bottom-up**. Each predecessor's docs must leave `1-WIP` before its
successors' — that ordering is what the forward-only linking rule relies on, since a forward link
from a predecessor to a successor's docs dangles if the successor is wrapped first.

## Wrapping Process

### For Changesets

1. **Execute the Wrap row's TODOs** — the wrap obligations the planner nested under the Wrap row
   (formerly the Final Checklist): every `[ ]` item in order before proceeding, ticking each `[x]` as
   you complete it. Do not mark the changeset complete until all are ticked. See
   `.agents/skills/pr-lifecycle/references/changeset.md` §17 for the format.
2. **Extract final state (State B)** from changeset (ignore deltas, process descriptions)
3. **Identify merge points** in dev documentation
4. **Apply content transformations** to package READMEs and dev docs
4a. **Apply the architecture-diagram update — this is where a diagram changes.** Where the
   changeset's `## Technical Changes` carries an `### Architecture Diagram` block (or a
   Wrap-row TODO names one), apply that update to the declared diagram file — resolved
   from the owning `README.md` (the package's own first, then the group-level
   `{group}/AGENTS.md`), honoring the format it declares (`mermaid` is the default). Write the
   diagram in State B like every other doc: the component topology as it now is, never
   "added an edge to …". Planning specified this update; the wrap is the only step that ever edits
   a diagram file. No block and no TODO → the diagram needs nothing; do not redraw it
   speculatively
5. **Transform language**: "Changed to X" → "Uses X", "Now supports Y" → "Supports Y"
6. **Merge operations**: Replacement, addition, enhancement, or removal of sections
7. **Update change history**: Write a new file
   `{group}/{package}/docs/changesets/YYYY-MM-DD-short-description.md`
   *(skip if a Wrap-row TODO already added it)*
7b. **Reconcile the deferred-work records — driven by the changeset's Outcome column.** Do this
   **before** deleting the changeset: `## Prerequisites` is the only place the mapping from this
   change to the records it addressed exists, and step 8 is about to remove it. Load the
   `deferred-work` skill (`.agents/skills/deferred-work/SKILL.md`);
   both records living under the package they describe — `<package-dir>/docs/todo/` and
   `<package-dir>/docs/code-issues/`.

   Skip this step if the changeset has no `## Prerequisites` section.

   **Read each row's Outcome and act on it** — `/green` step 3.5a wrote it, `/pr-wrap` step 7.5
   gated it, `/pr-wrap` step 7.6 decided the disposition of anything this PR left open (listed under
   *Decided without review*), and this is where it takes effect:

   | Outcome | Action on the record |
   |---|---|
   | ✅ **Resolved** | **delete the file** (`git rm`). Its closing line and — for a code issue — the new measurement go in the commit message; git keeps the history |
   | ◐ **Partly** | **update and leave open**: the improved numbers as a `Measurement history` row (a `**Progress:**` line for a TODO), and *What is left* / *What would close it* narrowed to just the remainder, naming the PR that moved it |
   | ➖ **Unchanged** | nothing. The record is already correct; rewriting it to say "considered again" is churn |
   | ⛔ **Deferred** | confirm the TODO file exists, with a named blocker and — for planned scope — the developer's recorded decision (their answer to a ⛔ halt) |

   **An Outcome cell still holding `(filled by /green)` is a stop, not a detail.** It is
   indistinguishable from work nobody did, and once the changeset is deleted the question cannot be
   answered. Determine what happened and fill it, or report it as a ⛔ stop — do not wrap past it.

   **Narrowing a ◐ Partly record is the step people skip.** Leaving its *What is left* describing the
   original gap means the next planner's Step 2b re-plans work that is already done. The record must
   describe the **remainder**, not the history — the history goes in `Measurement history` and the
   `**Progress:**` line.

   **Delete a record only when its Outcome is ✅ Resolved.** They live in
   `<package-dir>/docs/{todo,code-issues}/` — package documentation, not changeset companions, and
   **not** `docs/<area>/1-WIP/`, which this step empties. Wrapping a package's docs never sweeps its
   record directories: it removes the resolved records and nothing else.

   **Every open TODO under a row other than Wrap is a deferral and needs a TODO file** — an
   unfinished milestone or Scope deliverable, a Technical Debt item, likewise a `TODO`/`FIXME` left
   in code. Check each has one,
   with a named blocker and, for **planned** scope, the developer's recorded decision. A gap with no
   record is a silent scope cut: **stop and report it as ⛔ rather than wrapping over it.**

   Report all of it in the Wrap Report: records closed, records updated and left open, records
   confirmed, records opened.
7c. **Carry the deferred answers into the history entries** — before deleting the changeset,
   because its `## Deferred Answers` section is the only place that ties those records to this
   change. Skip this step if there is no such section. For each row:
   - **Product** → a line in the **Deferred answers** block of the product area's changelog entry
     (step 7 for a PRD, *For PRDs* below). If this change wraps no PRD, it goes in the owning
     package's history entry with its Kind stated.
   - **Technical** → a line in the owning package's `docs/changesets/` entry.
   - **The record itself is not touched.** Wrap never deletes a deferred answer. Only the
     developer's review closes one, so the record stays open in its directory past the merge.
   - A row whose record the developer already answered during the PR (`/review-deferred-answers`
     writes the outcome into the row) goes in the entry with that outcome, `→ c) (confirmed)` or
     `→ overridden to a)`, so the entry says what the change finally shipped. Answers given after
     the wrap never revise the entry. The record's deletion commit carries them.

   Tick the Wrap TODO `Deferred answers carried into the history entries`, and list them in the
   Wrap Report.
8. **Delete source**: Remove the changeset from `docs/<area>/1-WIP/` (not archived). Also delete
   its companion `{changeset-slug}-initial-discovery.md` in the same directory. Do **not** merge
   Combined Conclusions or Exploration sections into package docs — that file is planning
   evidence, not State B. If the companion is missing, say so in the Wrap Report and continue.
   The changeset's `[wf]` rows are deleted with it; the caller has already carried them
   forward (see *A procedure, not a row*).
   For a restructure, also delete any spent plan the changeset's `## Plan` names
   (`git rm -r <package-dir>/restructure/<slug>/`) — `code-restructuring` step 8 should already
   have; this is the backstop. `git ls-files '*/restructure/*/plan.jsonl'` must print nothing.
9. **Verify the docs**: `uv run pytest -q` must exit 0 — deleting the
   source can orphan a link that pointed at it. See **Verify the docs after wrapping**.

### For PRDs

1. **Extract final state (State B)** from PRD (ignore change rationale, deltas)
2. **Identify merge points** in feature documentation
3. **Apply content transformations** to feature documents
4. **Transform language**: Remove "changed", "updated", "new" language → state final state cleanly
5. **Merge operations**: Replacement, addition, enhancement, or removal of sections
6. **Update change history**: Write a new file
   `docs/{product-area}/changelog/YYYY-MM-DD-short-description.md`
7. **Delete source**: Remove PRD from `docs/*/1-WIP/` (not archived)
8. **Verify the docs**: `uv run pytest -q` must exit 0. No stable
   document should reference the PRD you just deleted — nothing links into `1-WIP/`
   (`docs/AGENTS.md`). A reference that predates that rule, most often a product-area
   `1-OVERVIEW.md` line: **delete it** — its content has just been merged into the feature docs;
   do not repoint it at the changelog entry. See **Verify the docs after wrapping**.

**State B, Not Delta**: Documentation must read as cohesive, unified documents without traces of change process.

### Behaviour-preserving restructures (`Type: Refactor`)

A restructure changeset wraps to a deliberately narrow set of edits, because nothing it describes is a
behaviour change:

- **The changelog entry, always.** A new release-note file in each affected package's
  `docs/architecture.md` — or the package README's history, where the
  package has no `docs/` — naming what moved, stating that behaviour is unchanged, and carrying the
  baseline-vs-after numbers that back the claim.
- **The plan, never.** `plan.jsonl` is not documentation and is not wrapped anywhere: it is deleted
  (step 8), and the changelog entry may cite the commit that applied it, never its path.
- **Dev docs only where the move made them false**, as itemised in the changeset's Wrap-row TODOs:
  file and module maps, "add a new X here" instructions, member listings, code examples and diagrams
  carrying an old path. Rewrite those to State B; do not narrate the move.
- **Nothing else.** Do not merge State B across the rest of the package docs. For a restructure most of
  State B *is* State A, and rewriting prose that is still accurate is churn a reviewer has to read and
  cannot verify. **A changelog-only wrap is a correct and common outcome here.**
- **No PRD and no `docs/<area>/` changelog.** Those describe behaviour, which did not change. The exception
  is a package whose product is its structure — a public API surface, a codemod tool — where the surface
  moving is itself the user-visible change.

If a `Refactor` changeset arrives with no doc TODOs under its Wrap row, the split was planned without one:
derive the doc work by grepping the package's docs for the moved paths and symbols before wrapping, and
say which docs you checked. See the `code-restructuring` skill.

## Verify the docs after wrapping — MANDATORY

**A wrap deletes files, so it can break links that were valid a moment earlier.** The
changeset, the PRD and the discovery companion all disappear, and anything that pointed at
them becomes a dead link. Nothing should — no stable document links into `1-WIP/`
(`docs/AGENTS.md`) — but a reference written before that rule, or by mistake, surfaces here. `surmap`'s **build** is the relative-link checker, so a dead
link is not a lint warning: it **fails the CI build** for a package the PR never
touched, and the failure surfaces ~30 minutes after the push instead of here.

Run this after deleting the sources and before reporting the wrap done:

```bash
uv run pytest -q
```

Exit 0 is required. A dead link naming a document you just deleted is the wrap's own
doing, and there are exactly two honest repairs:

- **Delete the referring line.** The default. A link to a PRD or changeset existed to say
  "this work is in flight"; once wrapped, the statement it pointed at lives in the stable
  doc you just updated. The line has no reader left.
- **Replace the link with the fact.** When the referring sentence still needs what the
  deleted document said, write that statement into the stable doc in State B.

Never repoint a dead link at the changelog or `docs/architecture.md` entry — see **A history
file is terminal**. Never leave it pointing at the deleted path.

Then confirm the wrap actually cleared `1-WIP` for this PR, which is what lets it go up
for review:

```bash
uv run pytest -q
```

`check-unwrapped-wip.mjs` uses `--diff-filter=AM`, so it fails a **ready** PR that adds
*or modifies* any `1-WIP` file. Ticking a box in an umbrella PRD that stays in `1-WIP`
counts as a modification and will block the PR — record that information in the permanent
changelog entry instead, and leave the in-flight umbrella untouched.

Both commands are cheap and local. Running them is the difference between fixing a dead
link in the working tree and discovering it from a red CI build.

## Stack Mode — wrapping one PR of a stack

**Detect first:**

```bash
BRANCH=$(git branch --show-current)
gh stack view 2>/dev/null | grep -F "$BRANCH"
if [ -n "$BRANCH" ]; then
  grep -l "## Stack Context" docs/<area>/1-WIP/*.md 2>/dev/null \
    | xargs grep -l --fixed-strings "$BRANCH" 2>/dev/null
fi
```

No hit → ordinary branch, skip this section. An empty `$BRANCH` is not a match. Do **not**
`grep -l "Inherited Dependencies"` across `1-WIP` without this branch's name in the same file.
A hit → wrap **this PR's** documentation under the extra rules below, then apply the readiness gate. Model: the `pr-stack` skill
(`.agents/skills/pr-stack/SKILL.md`).

### W1. Wrap only the docs THIS PR owns

A stacked branch's tree contains its **predecessors'** docs as well as its own — they are inherited,
not yours. Wrap **only this PR's own changeset, PRD, and `{slug}-initial-discovery.md`** — the set
whose `## Stack Context` names this branch.

- ❌ Never wrap or delete a **predecessor's** docs — that PR wraps its own when it lands.
- ❌ Never wrap or delete a **successor's** docs — they do not exist in this branch anyway, and
  deleting them from a shared file would surface as loss in the successor's diff.
- ❌ Never delete `docs/<area>/1-WIP/*-whole-work-initial-discovery.md` — that is `/plan-pr-stack`
  Step 2's temporary whole-work dump, removed in Step 5 after every PR has its own companion.
  Wrap deletes only **this PR's** `{slug}-initial-discovery.md`.
- If this branch's tree still contains a predecessor's changeset in `1-WIP` and that PR has already
  merged and wrapped, that is a stale inherited copy: leave it to `/pr-stack-rebase` (its deletion
  arrives with the base), do not re-delete it here.

### W2. Forward links — keep them stable, never add a back-link

Per the forward-only linking rule, this PR's changeset/PRD may carry a `## Successor PRs` section
pointing at successor docs still in `docs/<area>/1-WIP/`. Those paths disappear when the successors wrap,
so **do not carry 1-WIP paths into permanent documentation**. In the changelog/dev-doc entry, reference
successors by their **PR number and URL** (stable) plus the stack name — not by their doc path.

Never add a link from this PR's docs back to a predecessor's: the predecessor wraps first, and the
link would dangle immediately.

### W3. Nothing hands off — this PR's docs are all it has

There is **no shared stack document**. Each PR's stack context lives in a `## Stack Context` section
inside its own changeset, so wrapping this PR wraps everything the stack needed from it:

- its `## Stack Context` (position, base, owned API surface, greenability) goes with the changeset —
  fold the durable parts into the package docs like any other State B, and let the rest go;
- its `## Inherited Dependencies — do not implement here` table is spent once this PR is green, so it
  is not transferred anywhere;
- **nothing is pushed to another branch, and no "action required" notice exists.** A wrap touches only
  the branch it runs on.

If this branch still carries a `docs/<area>/1-WIP/STACK-*.md`, it predates this model: fold each row into
the matching PR's changeset `## Stack Context` and delete the file. Do not re-create it, and do not
push it anywhere.

The whole-stack rationale — why the work was split this way — belongs in the package docs, transferred
by whichever PR's changeset states it. `gh stack view` remains the topology and `gh pr list` the
status; neither needs a committed copy.

### W4. Readiness gate — no WIP of this PR's own may remain

A stacked PR goes up for review only when **nothing of its own** is still in flight. Check each, and
report the list:

| Check | Command / where | Passes when |
|---|---|---|
| Own changeset wrapped | `docs/<area>/1-WIP/` | this PR's changeset is gone (content transferred, not just linked) |
| Own initial-discovery companion deleted | `docs/<area>/1-WIP/` | this PR's `{slug}-initial-discovery.md` is gone (deleted, not merged into package docs) |
| Own PRD wrapped | `docs/*/1-WIP/` | same, or explicitly deferred with a written reason |
| No spent restructure plan | `git ls-files '*/restructure/*/plan.jsonl'` | prints nothing — every applied plan deleted |
| No open TODOs | this PR's changeset before deletion | every TODO under the rows `[x]` — the Wrap row's included — or, outside the Wrap row, linked to its deferred-work record |
| Own stubs implemented | `grep -rn "TODO(pr-<this-k>)" <pkg>/src` | no hits |
| No WIP commits | `git log origin/<base>..HEAD --oneline` | no `wip:` / `fixup!` commit, unless the PR lands squashed |
| Docs read as final state | wrapped docs | no "in progress"/"will be added" language about **this** PR's surface |

**Inherited `TODO(pr-<other-k>)` stubs are NOT this PR's WIP** — they belong to the PR that owns them
and must stay exactly as they are. Only this PR's own `k` counts against the gate.

### W5. Push, then mark the PR ready for review

The wrap commit must be on the remote before the PR is put up for review:

```bash
git add -A && git commit          # never --no-verify, never amend
git push origin $(git branch --show-current)
gh pr ready <N>                   # this PR only
gh stack view                     # expect ○ open, no ⚠, base still the predecessor
```

**Never `gh stack submit --open`** — it marks new *and existing* PRs ready, publishing drafts further
up the stack that are still being implemented. If the push is rejected because the base moved, run
`/pr-stack-rebase` (this branch only), never `gh stack sync` from a per-PR worktree.

**Keep the worktree.** The post-wrap procedures (`/fix-pr`, `/yolo`'s Approve and Land) run in
it. It is removed only once they are done, by whoever owns it (`/pr-wrap` § *The
worktree stays*, `/yolo-pr-stack` step 3), and never the branch, since a successor bases on it.

## Post-wrap Mode — re-wrapping a PR that is already wrapped

Used by a `/pr-wrap` re-run after the developer added commits to a wrapped PR. There is no changeset
or PRD any more, so the State B source is different:

- **Source.** The commits since the wrap commit (`git log --diff-filter=D -1 -- docs/<area>/1-WIP/<changeset>.md`
  finds it) and their diff: State B is what the code now does, read from that diff. The wrap commit's
  message and the PR body's `## Summary` give the context the original changeset had.
- **Targets.** The package and feature docs the first wrap wrote (its commit's diff names them),
  plus any doc the new diff makes false. Apply State B to them as *Apply to Target Docs* says.
- **History.** A re-wrap is a wrap, so it writes its **own** history file (§ *History files*), dated
  today, whose slug names the follow-up, and the first wrap's file stays as it was, since history is
  never revised. Its body names the commits and what they changed, and it may cite the first wrap's
  file (links run one way).
- **Nothing to delete**, and the verification below still runs.
- **Commit** it declared as a wrap (`Docs-Wrap: /wrap-context-docs` trailer), so the readiness check
  accepts the doc edits. A follow-up that changes no documented behaviour writes nothing, and the
  re-run says so.

## When Wrapping is Blocked

If prerequisites are not met, do not wrap. Report it as a ⛔ stop — the caller's row halts with it —
with a prominent disclaimer and **three options** for the developer:

1. **Complete All Work (Recommended)**: Finish all incomplete items, update status, and wrap again
2. **Accept Current State & Wrap**: Mark incomplete items as "Deferred", document WHY, update status to Complete (Phase N)
3. **Keep Working**: Continue development, keep the changeset current (`/update-context-docs`), wrap when complete

## Decision Logic

```
IF no open TODO before the Wrap row (or each has its record) AND all criteria met:
    → Execute each open Wrap-row TODO, ticking each [x] as completed
          Only continue once all of them are [x]
    → Extract final state (State B) from changeset/PRD
    → Apply content transformations to target docs
    → Write new changelog/changesets history files (one file per wrap)
    → Delete source document (not archived)
    → Delete `{changeset-slug}-initial-discovery.md` (not archived, not merged into package docs)
    → Run `uv run pytest -q` (must exit 0) and repoint any link the
      deletion orphaned at its permanent replacement
    → Run `uv run pytest -q`
    → Report success
ELSE IF incomplete:
    → Report what's missing
    → Display disclaimer with options (a ⛔ stop for the caller's row)
    → Skip wrapping
```

## Output Format

### Update Report
```markdown
## Documentation Update Report

### Changesets Updated
| Document | Progress | Status |
|----------|----------|--------|
| 2026-01-22-feature.md | 4/6 complete | 🔄 In Progress |

### Updates Made
- Implementation: TODOs ticked
- Testing: still open

### Remaining
- Acceptance tests not yet complete
```

### Wrap Report
```markdown
## Documentation Wrap Report

### Wrapped Documents
| Source | Target | Status |
|--------|--------|--------|
| 1-WIP/feature.md | <workspace>/{package}/docs/ | ✅ Applied |
| 1-WIP/fix.md | ft/feature/1-OVERVIEW.md | ✅ Applied |

### Deleted
- `docs/<area>/1-WIP/2026-01-22-feature.md`
- `docs/<area>/1-WIP/2026-01-22-feature-initial-discovery.md`
- `docs/<area>/feature/1-WIP/fix.md`

### Deferred-work records
Paths are repo-relative — each record lives in the docs of the package it describes. Driven by the changeset's `## Prerequisites`
Outcome column, read before the changeset was deleted.

| Record | Outcome | Action |
|--------|---------|--------|
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-08-14-analyzer-fallback-deferred.md` | ✅ Resolved | deleted — fallback removed in `a1b2c3d` |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/oversized-file-session-replay-service.md` | ✅ Resolved | deleted — 940 → 4 files, max 210 lines (in the commit message) |
| `mapping-pipeline/mapping-pipeline-server/docs/code-issues/missing-tests-subasset-processing-service.md` | ◐ Partly | **left open**, narrowed — `splitSubassets` now covered (12% → 71%); *What is left* now names `mergeSubassets` only |
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-07-02-subasset-revision-guard.md` | ➖ Unchanged | untouched |
| `mapping-pipeline/mapping-pipeline-server/docs/todo/2026-09-09-scope-registration.md` | ⛔ Deferred | 🆕 opened — blocked on ABAC scope registration; consent recorded |

*(No record is ever deleted by a wrap. A ◐ Partly record must describe the **remainder**, not the
original gap. An open TODO under a row other than Wrap with no record, or an Outcome cell still reading
`(filled by /green)`, is a stop — not a note.)*

### Skipped (Incomplete)
| Document | Missing |
|----------|---------|
| 1-WIP/other.md | Testing, Code Quality |

Reason: Complete remaining work before wrapping.
```

## Rules
- **Architecture diagrams: declared in `README.md`, specified in the changeset, updated only
  here.** Planning resolves the declaration (package `README.md`, then `{group}/AGENTS.md`) and a
  change that alters the depicted architecture carries an `### Architecture Diagram` spec in
  `## Technical Changes`; this command applies it. Never edit a diagram file outside a wrap, and
  never leave a diagram depicting State A after its changeset wrapped
- **Delete `<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/` files only when this changeset
  resolved them (✅).** They are not changeset companions: leave every other record for the next
  planner's Step 2b.
- **An open TODO under a row other than Wrap with no TODO file is a stop, not a note.** Raise the gap rather than wrapping
  over it — a deferral of planned scope needs a named blocker and recorded consent
  (`deferred-work` skill).
- **The changeset's `## Prerequisites` Outcome column drives step 7b**, and it must be read before
  step 8 deletes the changeset. An Outcome still reading `(filled by /green)` is a stop: once the
  changeset is gone the question cannot be answered.
- **A ◐ Partly record is updated and left open, with *What is left* narrowed to the remainder.**
  Closing it would drop it out of the open-items query and hide the remainder from the next
  planner's Step 2b; leaving its original gap description would make them re-plan work already done.
- Extract content from PRD/changeset → Update feature/dev docs → Write history file → Delete source and `{slug}-initial-discovery.md`
- Never only write a changelog/changesets file without updating docs
- Never keep delta language ("changed from X to Y") in final docs
- Never leave feature/dev docs unchanged
- Never wrap incomplete changesets (unless the developer chose Option 2 in answer to the ⛔ stop)
- Never wrap a PR that is staying a draft, and never defer wrapping to after merge — the trigger is
  setting the PR ready for review
- **Never report a wrap done without `uv run pytest -q` exiting 0** — that
  package's *build* is the link checker, so a link orphaned by the wrap fails CI for a package
  the PR never touched
- **Stack**: wrap only this PR's own docs — changeset, PRD, `{slug}-initial-discovery.md`, and
  `## Stack Context`. There is no shared manifest, nothing to hand to another branch, and no
  cross-branch push; no WIP of this PR's own may remain when it is marked ready for review

## Related

**Commands**: `/update-context-docs`, `/plan-ft-dev`, `/pr-wrap` (runs this as step 8), `/plan-pr-stack`,
`/pr-stack-rebase`, `/fix-pr-stack`
**References**: `.agents/skills/pr-lifecycle/references/changeset.md`,
`.agents/skills/pr-lifecycle/references/prd.md`,
`.agents/skills/pr-lifecycle/references/initial-discovery.md`
**Skill**: `pr-stack` (`.agents/skills/pr-stack/SKILL.md`) — when this branch is part of a PR stack
**Skill**: `deferred-work` (`.agents/skills/deferred-work/SKILL.md`) — the TODO and code-issue
records a wrap deletes when resolved and otherwise leaves alone
