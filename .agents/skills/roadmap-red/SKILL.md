---
name: roadmap-red
description: "Plan and write failing tests for one item on a Roadmap tracker page (<service-host>/stash/<slug>) used as a roadmap. Takes the Roadmap URL and a reference to the item. Follows the plan-red workflow, verifies the page's progress claims against the code instead of trusting them, folds the page's open review comments into scope, and writes a changeset whose ## Stash Tracker section and Plan/Wrap TODOs say exactly what to publish back to the page (PR reference and PR state) — or what the developer must mark by hand when the agent cannot edit it."
---

# Stash Red

Plan-red flow for one item on a Roadmap page. The pattern,
its four rules and the procedures this file names are in the `roadmap-driven-development` skill
(`.agents/skills/roadmap-driven-development/SKILL.md`) — load it first.

## Arguments

```
/roadmap-red <stash-url> <item>
```

| Argument | Description | Examples |
|----------|-------------|---------|
| `stash-url` | The page's URL or bare slug — a slug is normalized to the canonical URL (`roadmap-driven-development` § *Read the page*). | `<service-url>` · `session-forms-roadmap` |
| `item` | Item id, heading, or task text on the page. Case-insensitive prefix match is fine. | `F-4` · `signature fields` · `"Export: flatten annotations"` |

If `item` matches more than one item on the page, list them and ask the user to confirm.

## Workflow row

Follows the `pr-lifecycle` skill (`.agents/skills/pr-lifecycle/SKILL.md`). Writes the `[wf]` rows
from the **stash** preset and owns row 1, **Plan and red**. Result:
`<mode> · Stash TODOs: <N> · <n> failing @ <sha>`. The item question above and the Step 4 scope
confirmation gather input, so they stay. Halts, beyond the skill's: the item is not on the page; a
publish fails (`roadmap-driven-development` § *Publish* step 5); nothing red after Phase 4.

**Row TODOs** (Plan and red) — seeded when the row starts; a re-run resumes at the first open one:
`Record initial discovery` · `Create/update PRD documentation` · `Create changeset` · `Scope confirmed
with the developer` · `Acceptance tests written and failing` · `Integration/unit tests written and
failing` · `Stash: Plan publish (or manual advice)` · `Tests committed with the changeset`

## Execution Flow

### Phase 1: Read the page and the code

**Step 1 — Read the page.** `roadmap-driven-development` § *Read the page*: auth, role, entry path,
download to `tmp/stash/<slug>/read`, comments. Locate the item; copy its text and its sub-tasks
**verbatim** — they become the acceptance checklist. Note any linked spec section on the page (or a
spec the page links to) and read it.

**Step 2 — Decide the mode.** Rule 2: **editable** or **manual**, with the reason.

**Step 3 — Verify the claims (Rule 1).** For the target item, every item it depends on, and every
item the page claims is related, check code and GitHub. Read the package `README.md`, identify what
is stubbed vs implemented, and the existing test patterns. Build the *Claims vs code* table. A
dependency that is ⚠️ *claimed, not found* is not built on — it is either in this PR's scope or a
⛔ halt (*re-scope* / *plan the dependency first*).

**Step 4a — Size the item.** Score it on the `Complexity` scale (`pr-lifecycle/references/changeset.md`
§1) from what Steps 1–3 found. Recommend a **stack** instead of one PR when any of these holds:

- Complexity **4–5** — more than one package, a proto / contract change, a data migration,
  concurrency or ordering semantics;
- the item needs **more than one kind** of change (a restructure or bug fix under the feature) —
  one diff with two families has the wrong boundary (`pr-stack` skill § *Node kinds*);
- its sub-tasks ship independently, or a ⚠️ *claimed, not found* dependency has to be built first.

**Step 4 — Confirm scope with the user.** When 4a recommends a stack, the scope question offers it
as the first option, with the reason and the slices it would cut — *a) a stack:
`/plan-pr-stack <stash-url> <item>`* · *b) one PR, as this command plans it*. **The developer
decides**; a one-PR answer is recorded in `## Decisions & Trade-offs` with the size that was
accepted. On *a)* this command stops before writing anything — no changeset, no tests, no publish —
and the summary gives the `/plan-pr-stack` invocation. Then one paragraph: what this item implements, what it builds
on (with evidence, not page status), the ⚠️ claims, the open comment threads and which ones this PR
addresses, the mode and what will be published (or advised) at Plan and Wrap. Ask the user to
confirm or correct before writing any documents.

### Phase 2: Documentation

**Step 5 — Create the changeset** per the `pr-lifecycle` skill § *Start a changeset*, slug
`{package}-{item-slug}`, with the **stash** preset and row 1 ⏳ until Phase 5 closes it. Mandatory
for `/roadmap-red` changesets:

- **`## Stash Tracker`** — the whole policy, `roadmap-driven-development` § *Write the changeset's
  `## Stash Tracker`*: page, item, *Read at*, mode, what each publish writes, comment threads with
  their disposition, *Claims vs code*.
- **The Stash TODOs**, concrete — URL, item text verbatim, marker text (the ready publish is not
  one: `/pr-wrap` step 9 makes it from the `## Stash Tracker` policy once the PR is ready):
  - under row 1: the Plan publish (`planned · branch <branch>`) or its manual advice;
  - under **Wrap**, always: `Verification executed — result recorded`, the package release note
    `{package}/docs/changesets/YYYY-MM-DD-short-description.md`, and the optional `/pr-wrap` steps
    this change needs.
- **Green-row TODOs** — the implementation milestones, one per sub-task copied verbatim from the
  page.

**Step 6 — Tick** `Record initial discovery`, `Create/update PRD documentation`, `Create changeset`,
`Scope confirmed with the developer`.

### Phase 3: Failing acceptance tests (Step 7)

For each acceptance criterion on the page (or its linked spec): write the test fully, run it,
confirm it fails for the right reason (missing implementation, not a test bug), capture the
failure. Use the tiers the package's `README.md` and the rhombus rule
(`docs/architecture.md`) call for. Record titles, paths and failure reasons for
**Decided without review**.

### Phase 4: Failing unit/integration tests (Step 8)

Comprehensive failing lower-tier tests for the item's behaviour. Every assertion implemented — no
stubs, no placeholders. Run each and confirm the right failure.

### Phase 5: Publish, commit, close the row, summarise (Step 9)

1. Execute the row-1 Stash TODO: § *Publish* (editable) or put the advice in the summary (manual).
2. Commit the tests with the changeset; close row 1 ✅.

```
Page:      <service-url>   →  "<item>"
Mode:      editable (publisher, static status) | manual — <reason>
Published: planned · branch <branch>  (deployment <id>) | — advice below
Changeset: docs/<area>/1-WIP/YYYY-MM-DD-{package}-{slug}.md
Stash TODOs: Plan ✅ · <row> ⬜ (PR #N · ready for review, resolves <k> threads)

Claims vs code:
  ⚠️ <item> — page: done · code: <missing at …>

Comment threads: <a> addressed · <o> out of scope

Acceptance tests ({N} failing):
  <path>
    ✗  {test title}  —  {failure reason}

Integration tests ({N} failing):
  <path>
    ✗  {test title}  —  {failure reason}

Needs the developer: (manual mode) on <url>, next to "<item>", set "planned · branch <branch>"

Row 1 Plan and red ✅ — next row: <2> <step> — `<Run with>` (the skill's next-row grep)
```

## Rules

- Never plan from the page's status markers — verify in code (Rule 1)
- Never publish without the mode check, never `--anonymous`, never to another slug (Rule 2)
- An edit writes PR references and PR state only, and reconciles every PR marker on the page (Rule 3)
- Copy item and sub-task text verbatim from the page
- Every publish the PR will make is a TODO in the changeset — no step decides one on its own
- Confirm scope with the user before writing documents; recommend a stack for a big item, and let the developer choose
- Tests fully implement their assertions; no item ids (F-N) in test `describe` blocks or file names
- Every test is **fluent** (`fluent-tests` skill, ≥ 8 on `.agents/skills/testing/references/fluent-style.md`),
  even in a suite that is not

## Related

**Skills**: `roadmap-driven-development`, `story-red`, `plan-red`
**References**: the `pr-lifecycle` skill (the stash preset), `pr-lifecycle/references/changeset.md` (`## Stash Tracker`, Wrap TODOs)
