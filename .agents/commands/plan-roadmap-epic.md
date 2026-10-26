---
description: Start a Roadmap-driven epic - interview the developer, check the code for what already exists, write the epic's roadmap page (why, scope, items with acceptance criteria, dependencies, and an editable status + PR cell per item) and publish it to Roadmap tracker under a new slug, so /plan-pr-stack or /roadmap-red can plan from it and publish PR state back to it
---
## Plan Stash Epic — the page every later Stash step plans from

Creates the **Roadmap page** of the `roadmap-driven-development` skill
(`.agents/skills/roadmap-driven-development/SKILL.md`) — load it first. The page is the epic's shared
plan and progress view: product, design and engineering read and comment on it, `/plan-pr-stack`
and `/roadmap-red` plan from it, and their changesets publish PR references and PR state back to it.

This command writes **no code, no branch, no changeset and no PR**. Its output is one published
Roadmap page and its URL. "Epic" here is that page; the GitHub epic issue of a stack is opened later by
`/plan-pr-stack` and links back to the page.

```
/plan-roadmap-epic <what the epic delivers>
```

`what` is free text, a PRD path, a feature doc, an issue — whatever describes the epic. The agent
picks the slug (Step 4).

## Step 1 — Preflight: the session can publish

```bash
roadmap-cli auth status --json
```

Not authenticated → stop and ask the developer to run `! roadmap-cli auth login`.
Never publish `--anonymous`.

## Step 2 — Interview

Run `.agents/skills/planning/references/planning-phase.md` **Step 1** (What / Why / Where /
Constraints / UX / Scope), then the epic-specific questions:

1. **Items.** The independently shippable pieces of the epic, each stated as what it delivers once
   shipped — not a task list. Each item gets an id (`E-1`, `E-2`, …) that never changes once
   published; a dropped item stays on the page as *dropped*, its id is never reused.
2. **Acceptance per item.** Two to six criteria a reviewer can check — they become `/roadmap-red`'s
   acceptance checklist, copied verbatim.
3. **Dependencies.** Which items need which. They become the first draft of a stack's edges.
4. **Packages.** Where each item lands — read each package's `README.md`.
5. **Audience and visibility.** Who reads the page: listed in Stash Explorer (default) or
   `--no-discoverable`; private to an ownership tag or emails (`--view-access-ownership-tag`,
   `--view-access-email`); an `--ownership-tag` so the team, not only the developer, can publish.

These are questions that gather input; ask them all before writing the page.

## Step 3 — Check the code before writing a status

For every item, look for what already exists (`roadmap-driven-development` Rule 1, applied to the
draft): a symbol, a test, a merged PR (`gh pr list --state merged --search "<terms>"`). An item the
code already delivers is written **done** with its evidence, or left off the page if the developer
prefers; a partly delivered one says what is there. Nothing is written *planned* that is already
shipped, and nothing *done* without evidence.

## Step 4 — Pick the slug

Derive it from the settled intent, not from the raw argument: `<product>-<what it delivers>`,
kebab-case, 3–64 chars of `[a-z0-9-]`, starting with `[a-z0-9]` — e.g. `mapping-pipeline-form-signing`,
`product-offline-reading`. The product is the owning area (`docs/<area>/`); the rest is the epic's
outcome in two to four words — never a date, a ticket number or `epic`/`roadmap` filler, because
the slug is the page's permanent URL.

Check it is free:

```bash
roadmap-cli permissions query "<slug>" --json
```

Only a `not-found` error means free. A returned role means **the slug is taken** — a deploy would
replace that page and share its Stash DB state (`roadmap-driven-development` § *Publish*). Read the
taken page (`download`): when it is this same epic, stop and offer to plan from it
(`/plan-pr-stack <url>` · `/roadmap-red <url> <item>`); otherwise pick a more specific slug and check
again. Never append `-2` — a reader cannot tell two such pages apart.

## Step 5 — Write the page

One Markdown file, `tmp/stash/<slug>/<slug>.md` (`tmp/` is gitignored — the page lives on Stash,
not in the repo). Use this structure; the **Status** and **PR** cells are the static markers later
publishes edit (`roadmap-driven-development` Rule 2 and Rule 3), so they are plain text in both the
table and each item:

```markdown
# <Epic title>

**Owner**: <name / team> · **Created**: YYYY-MM-DD · **Plan with**: `/plan-pr-stack <service-url>` or `/roadmap-red <service-url> <item>`

## Why

<the problem and who has it — two or three sentences>

## Scope

**In:** … · **Out:** …

## Progress at a glance

| ID | Item | Depends on | Status | PR |
|---|---|---|---|---|
| E-1 | <what it delivers> | — | planned | — |
| E-2 | <what it delivers> | E-1 | planned | — |

---

## E-1 — <what it delivers>

<final-state prose: what the user / system can do once this ships>

**Packages:** `<group>/<package>` · **Depends on:** —

**Acceptance:**
- <criterion>
- <criterion>

**Status:** planned · **PR:** —
```

Status values: `planned` · `in progress` · `in review` · `done` · `dropped`. A PR cell holds
`PR #<N> · <draft | ready for review | merged | closed>` linking to the PR, one per line when an
item spans several PRs. Write no `- [ ]` checkboxes: Stash renders them as static text, and the
progress they would imply is the page's claim, not its record.

## Step 6 — Publish

Show the developer the slug, the **Progress at a glance** table and the audience settings as the
last interview answer to correct. Then deploy the single file; it is a first publish, so the
visibility flags apply:

```bash
roadmap-cli deploy "tmp/stash/<slug>/<slug>.md" --name "<slug>" --category spec \
  --deployment-workflow using--stash [--no-discoverable] [--ownership-tag <tag>] \
  [--view-access-ownership-tag <tag> …] [--view-access-email <email> …] --json
```

Verify: `download` it back into `tmp/stash/<slug>/check` — a Markdown page comes back as the
service's `index.html` plus `content.md`, the source — and confirm every item id and Status cell is
present in `content.md`; `permissions query` now returns `publisher` for this session.

## Step 7 — Summary

```
Page:       <service-url>   (<listed | unlisted | private to …>)
Items:      <n> — <p> planned · <d> done (evidence) · <x> left off
Waves:      E-1 · E-2, E-3 · E-4   (from the dependencies)

Where the epic goes from here:
  a whole stack   →  /plan-pr-stack <service-url>   (or /yolo-pr-stack)
  one item        →  /roadmap-red <service-url> E-<k>
  feedback first  →  share the URL; review comments become planning input
```

## Rules

- Never deploy to a slug that already resolves — a redeploy replaces someone's page
- Never publish anonymously
- Every Status is backed by the code check in Step 3
- The slug comes from the settled intent (Step 4) and is never reused, suffixed or overwritten
- Item ids are permanent; a dropped item stays, marked `dropped`
- Status and PR cells stay plain text in the Markdown, so later publishes can edit them
- No branch, changeset or PR — the stack and its changesets come from the commands that plan from the page

## Related

**Skills**: `roadmap-driven-development`, `roadmap-red`, `planning`
**Commands**: `/plan-pr-stack`, `/yolo-pr-stack`
