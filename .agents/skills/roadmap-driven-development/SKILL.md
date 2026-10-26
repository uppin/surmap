---
name: roadmap-driven-development
description: "Explains Roadmap-driven development: a Roadmap tracker page (<service-host>/stash/<slug>) is the plan and progress view that /roadmap-red, /plan-pr-stack and /yolo-pr-stack plan from, and that the Plan and Wrap rows publish PR references and PR state back to. Owns the shared procedures — read the page, verify its claims in code, decide whether the agent may edit it, write the changeset's ## Stash Tracker policy, publish, or tell the developer what to mark by hand. Use when a Roadmap URL is the input to planning, when a changeset carries a ## Stash Tracker section, or when troubleshooting the workflow."
---

# Stash-Driven Development

This pattern keeps a feature's roadmap on a **Roadmap tracker page** — a hosted HTML or Markdown
artifact at `<service-url>` that the team already reads and comments on. For SurMap an epic is,
for example, "static/moving object layers end to end": on-board tracks in, merged static layer
and timestamped moving tracks out, proven on a recorded session. The page is an **input** to
planning and a **progress view** the workflow keeps current; it is never the record of what shipped.

| | Roadmap pattern |
|---|---|
| Plan input | the Roadmap page (any HTML / Markdown artifact) |
| Start | `/plan-roadmap-epic <what>` — interviews, checks the code, picks the slug, publishes the page |
| Single PR | `/roadmap-red <stash-url> <item>` — recommends a stack when the item is big; the developer chooses |
| Stack | `/plan-pr-stack <stash-url> [<item>]` · `/yolo-pr-stack <stash-url> [<item>]` |
| Preset | **stash** (`.agents/skills/pr-lifecycle/SKILL.md` § *Presets*) |
| Who updates the tracker | the TODOs the planner wrote under the Plan row, and the ready publish `/pr-wrap` step 9 makes once the PR is ready (a closing act, not a TODO), as the changeset's `## Stash Tracker` policy says; the merge flows reconcile after landing |
| Feedback | Roadmap review comments, read at planning, resolved when the PR addresses them |

**The changeset carries the policy.** Everything a later step needs — the URL, the item, whether
the agent may publish, what exactly it writes, which comment threads it resolves — is written into
the changeset's `## Stash Tracker` section and the concrete TODOs nested under its rows at planning
time. No step command has Stash-specific logic: each row's command works through the TODOs under
it like any other, and each TODO points at a procedure in this skill. The one exception is § *Reconcile
after landing*, which the merge flows run because no row exists after a merge.

**The CLI, pinned.** Every call is `roadmap-cli … --json` — written `stash …` below.
The version is exact, never `@latest`: an agent runs it with the developer's Stash session and
filesystem, so a new release is adopted by editing this line in a reviewed PR. It is not the
repo's `node_modules/.bin/stash` (2.41.0, a `product-qa` dependency), which predates `permissions`,
the access flags and `--resolve`. Read a subcommand's `--help` before using a flag this skill does
not show; never guess one.

---

## Starting a page

`/plan-roadmap-epic <what>` (`.agents/commands/plan-roadmap-epic.md`) creates the page: it
interviews the developer, checks the code for what already exists, derives the slug from the
settled intent, and publishes one Markdown file
whose **Status** and **PR** cells are plain text — so every later publish is in **editable** mode
for a publisher. Any existing page works too; one made elsewhere is simply read as it is.

## Rule 1 — the page's progress is a claim, the code is the evidence

A Roadmap page is edited by people and by other agents, and part of it may be rendered from Stash DB
state nobody in this repo controls. **Never plan from its status markers.** For every item the
plan touches (and, for a stack, every item on the page), check the code and GitHub:

| Page says | Code / GitHub says | Classification | What planning does |
|---|---|---|---|
| done / shipped | implemented, tests cover it, the PR it names is merged | ✅ consistent | builds on it |
| done / shipped | missing, stubbed, or its PR is open / closed unmerged | ⚠️ **claimed, not found** | never builds on it; it is a prerequisite or in scope — the scope confirmation names it |
| not started / planned | implemented already | ⚠️ **implemented, unmarked** | never re-implements it; the summary tells the developer, and the next publish marks it (when editable) |
| in progress · PR #N | PR #N is draft / ready / merged / closed | refresh the state | the next publish rewrites the marker |
| no status | — | read from code | — |

Evidence is a file path and symbol, a test name, or `gh pr view <N> --json state,isDraft,mergedAt`.
"The page says so" is not evidence. Every ⚠️ row goes into the changeset's `## Stash Tracker`
(*Claims vs code*) and into the step's summary.

## Rule 2 — edit only when the agent can, otherwise tell the developer what to mark

The page is **editable** only when all of these hold — anything else is **manual**:

1. `stash auth status --json` is authenticated (never publish `--anonymous`).
2. `stash permissions query <url> --json` returns `{"role":"publisher"}`.
3. The status of the target item lives in the **downloaded static files** — its text and its status
   marker are both in the HTML/Markdown, not fetched at runtime (`stash.db.collection(…)`,
   `stash.files`, a connector) by the page's script. Grep the download for the item text and its
   marker; a page that renders the item list from JS state is manual for status, even for a
   publisher.

| Mode | What the Plan / Wrap TODOs do |
|---|---|
| **editable** | publish the PR marker (Rule 3) by download → edit → redeploy (§ *Publish*) |
| **manual** | no deploy. The TODO is *"Advise the developer to mark …"* with the exact edit — page URL, item, marker text, PR link — and the step's summary carries it under **Needs the developer**. Ticked once the advice is in the summary |

When the developer has asked for no publishing, the mode is **manual** with that reason.

## Rule 3 — what an edit writes: PR references and PR state, nothing else

An edit adds or refreshes a **PR marker** next to the item, in the page's own idiom (a status pill
it already uses, a table cell, a list suffix). Its content:

```
PR #<N> · <draft | ready for review | merged | closed>   → https://github.com/<owner>/<repo>/pull/<N>
```

- Before a PR exists the marker names the branch instead: `` planned · branch `<branch>` ``.
- Where the item has its own status field, it mirrors the PR state: draft → *in progress*,
  ready → *in review*, merged → *done*. It never says *done* before the merge.
- **Every publish reconciles every PR marker on the page**, not just this item's. Each marker's
  state is re-read with `gh pr view`. A merge reaches the page through § *Reconcile after landing*;
  a PR closed unmerged, through the next publish of anything on the page.
- Never rewrite the page's prose, scope, ordering or other people's content. A ⚠️ *claimed, not
  found* item is reported, not edited.

## Rule 4 — review comments are planning input

`stash comments get <url> --json` at planning time. Every **open** root thread that is about the
target item(s) — anchored to it, quoting it, or naming it — is read like a requirement: it goes into
the scope confirmation (`/roadmap-red` Step 4, `/plan-pr-stack` Step 1), and its root id goes into
`## Stash Tracker` as *addressed by this PR* or *out of scope* with a reason. Comment attachments are
downloaded to a local path — open them; a screenshot is often the whole point.

The ready publish resolves the threads marked *addressed* (`deploy --resolve <root-id>`, editable)
or with `stash comments resolve <url> <root-id> --json` (manual mode, when the session allows it;
otherwise it is part of the advice). Never resolve an *out of scope* thread.

---

## Procedures

### Read the page

Normalize the argument first: `download` and `comments` take only a full URL (a bare slug fails
with `Invalid Roadmap URL`). A bare slug becomes `<service-url>`; a URL gives the
slug from its `/stash/<slug>/` path.

```bash
case "$ARG" in https://*) URL="${ARG%/}/" ;; *) URL="<service-url>" ;; esac
SLUG=$(printf '%s' "$URL" | sed -E 's#^https://[^/]+/stash/([a-z0-9-]+)/.*#\1#')
stash auth status --json
stash permissions query "$URL" --json
stash artifacts get "$URL" --json        # publisher only: entryPath, visibility
stash download "$URL" "tmp/stash/$SLUG/read" --force --json
stash comments get "$URL" --json
```

**Record the page's source kind** — it decides what § *Publish* deploys, and a folder can hold any
file, so the presence of a `content.md` alone proves nothing:

| Download holds | `index.html` | Source kind |
|---|---|---|
| exactly `index.html` + `content.md` | names `htmdx` (the service's Markdown wrapper) | **markdown** — `content.md` is the source |
| exactly `index.html` + `content.md` | no `htmdx` | **ambiguous** → **manual** mode, with that reason |
| anything else | — | **folder** (pass `--entry` when `artifacts get` names a non-default `entryPath`) |

A page `/plan-roadmap-epic` created is **markdown** by construction; its Stash Tracker says so.

`tmp/` is gitignored; the download never enters a commit. Record `deploymentId` (from
`artifacts get`) or, for a viewer, `shasum -a 256` of the entry file — the *Read at* fingerprint the
publish checks against. A failed auth is not a reason to stop planning: read what the session can,
plan in **manual** mode, and say so.

### Write the changeset's `## Stash Tracker`

Placed after `## Related Feature Documentation` (`pr-lifecycle/references/changeset.md`):

```markdown
## Stash Tracker

- **Page**: <service-url> — source `markdown | folder (entry <entryPath>)` · item: <item text, verbatim>
- **Read at**: YYYY-MM-DD · fingerprint `<deploymentId | sha256:…>`
- **Mode**: editable — publisher, status is static in `<file>` | manual — <reason>
- **Publishes**: Plan row → `planned · branch <branch>` (or `PR #N · draft`) · `/pr-wrap` step 9 → `PR #N · ready for review`, once GitHub shows the PR ready · after landing → `merged` (§ *Reconcile after landing*); every publish reconciles all PR markers on the page (roadmap-driven-development Rule 3)
- **Comment threads**:
  - `<root-id>` — "<excerpt>" → addressed by this PR
  - `<root-id>` — "<excerpt>" → out of scope: <reason>
- **Claims vs code**:
  | Item | Page says | Evidence | Classification |
  |---|---|---|---|
  | <item> | done | `src/…:symbol`, PR #N merged | ✅ consistent |
```

And the TODOs, concrete for this change (one each; the planner adapts the wording to the mode):

```markdown
- [wf 1] ⏳ `/roadmap-red` Plan and red — changeset with the Stash publish TODOs, failing tests ·
  - [ ] Stash: publish `planned · branch <branch>` next to "<item>" on <url>; reconcile all PR markers (roadmap-driven-development § Publish)
- [wf 3] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded
```

In **manual** mode the same TODOs read *"Stash (manual): advise the developer to set … next to
"<item>" on <url> …"*. The ready publish has no TODO: it is post-wrap (`pr-lifecycle` skill
§ *Post-wrap*). `/pr-wrap` step 9 makes it right after it opens or readies the PR, from the
`## Stash Tracker` policy it captured before the wrap deleted the changeset — `PR #<N> · ready for
review`, the reconcile, and the `--resolve` ids of the threads marked *addressed* — re-checking
`gh pr view <N> --json isDraft` first, so the page never shows *ready* while GitHub shows a draft.
A still-draft PR halts the Wrap row ⛔ instead. In manual mode the wrap's summary carries the
advice.

### Publish

1. **Fresh copy.** `download "$URL" "tmp/stash/$SLUG/publish" --force --json`. Compare its
   fingerprint with *Read at*: when the page changed since planning, apply the edit to the **fresh**
   copy, never to the planning copy — deployment is last-writer-wins and an older copy erases
   other people's edits. Note the change in the summary.
2. **Edit** the marker(s) per Rule 3 — the item's, and every other PR marker whose state moved.
   Keep the diff minimal: `diff -r tmp/stash/$SLUG/read tmp/stash/$SLUG/publish` should show only
   marker lines.
3. **Deploy** under the same slug, keeping the entry file; a redeploy preserves visibility and
   access, so no visibility flag is passed:
   ```bash
   # the source kind recorded in ## Stash Tracker decides the input — never the mere presence of
   # content.md; re-check it on the fresh copy (§ Read the page) and halt if it changed
   case "$SOURCE_KIND" in
     markdown) cp "tmp/stash/$SLUG/publish/content.md" "tmp/stash/$SLUG/$SLUG.md"
               INPUT="tmp/stash/$SLUG/$SLUG.md" ;;     # one .md file, never the wrapper folder
     folder)   INPUT="tmp/stash/$SLUG/publish" ;;      # with --entry <entryPath> when not index.html
   esac
   stash deploy "$INPUT" --name "$SLUG" \
     [--entry <entryPath>] --deployment-workflow using--stash \
     [--resolve <root-id> …] --json
   ```
4. **Verify the threads.** With `--resolve`, the JSON carries `openCommentIds`: an empty list means
   every requested thread resolved; anything else means the publish succeeded and those threads did
   not. Retry each with `stash comments resolve "$URL" <id> --json`; a thread still open after that
   is reported under **Needs the developer** and its TODO stays open. Exit 0 alone never means the
   threads resolved.
5. **Verify the page**: download again and grep the marker; record the new fingerprint in *Read at*.
6. **Halt** the row ⛔ (never retry anonymously, never fork to a new slug) when the deploy is
   refused, the role dropped to viewer, or the item text is no longer on the page — options:
   *switch to manual*, *re-plan against the current page*, *skip the publish*.

The planning invocation is the developer's consent to the publishes its changeset lists. A publish
the changeset does not list is not made.

### Reconcile after landing

No `[wf]` row runs after a merge, so the merge flows run this: `/yolo`'s **Land** row once the PR
is `MERGED`, and `/merge-pr-stack` Wave 4 after the last merge. It applies when the PR description's
`## Workflow` carries a `Stash:` TODO (the changeset is gone by then; the description is its copy).
Take the page URL from that TODO and run § *Publish* steps 1–3 and 5 with only the reconcile — every
PR marker re-read with `gh pr view` — so this PR and any other merged or closed one on the page show
their final state. No `--resolve`; nothing new is written. In manual mode, or when the publish
fails, the merge flow's report says what to mark instead — a merged PR is never blocked or undone by
its page.

---

## Using a Roadmap page for a stack

`/plan-pr-stack <stash-url>` and `/yolo-pr-stack <stash-url>` read the page in Step 1 (§ *Read the
page*, Rule 1, Rule 4) and use it as the interview's starting draft: its items propose the slices,
its order and stated dependencies propose the edges, and *Claims vs code* removes slices that are
already implemented. The stack's GitHub epic issue links the page. The interview still asks every question — kind per slice, edges, verification —
because a page is not a plan. Each node's changeset gets its own `## Stash Tracker` naming **its**
item(s); one page item may span nodes, and one node may close several items.

Publishes for a stack:

- **After pass 1** (Step 5, once every draft PR exists): one publish putting `PR #N · draft` next to
  every planned item — a single deploy for the whole stack, not one per node (`/plan-pr-stack`
  Step 5 item 6). Each node's guardrail row carries the TODO that it was listed, ticked in its
  commit 2.
- **Each node's wrap** (`/pr-wrap` step 9, once the PR is ready): `PR #N · ready for review` for its item(s), reconciling
  every marker — so the page catches up with merges of earlier nodes as later nodes go ready.
- **After the last merge**: `/merge-pr-stack` Wave 4 runs § *Reconcile after landing* once for the
  whole stack.

## Related

**Skills**: `roadmap-red`, `pr-lifecycle` (the stash preset)
**Commands**: `/plan-roadmap-epic` (creates the page), `/plan-pr-stack`, `/yolo-pr-stack`, `/pr-wrap` (step 9 makes the ready publish), `/yolo` Land and `/merge-pr-stack` Wave 4 (§ *Reconcile after landing*)
