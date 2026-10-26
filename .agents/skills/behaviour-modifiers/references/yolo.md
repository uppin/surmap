# `#yolo` and `#ask` — running without the developer

`#yolo` is for a run the developer means to leave alone: `/yolo`, `/yolo-pr-stack` once its
interview is accepted, or any flow tagged `#yolo`. Nobody is watching, so **anything that waits for
the developer stalls the run**. That includes a question, and it also includes a permission prompt.
This page says what changes. Everything it does not mention runs exactly as the command's own file
says.

## 1. No questions — deferred answers instead

Under `#yolo` the agent **never asks the developer a question**. No `AskUserQuestion`, no "which do
you prefer?" at the end of a message, no requirements interview. Where it would have asked:

1. **Write the question down** as a deferred-answer record
   (`.agents/skills/deferred-work/references/deferred-answer-record.md`). Record the question, the
   options it would have offered with the consequence of each, its recommendation, and why.
2. **With a supervisor, relay it** (§ 2). Without one, **pick its own recommendation**.
3. **Carry on** with the pick. Under the record's *What was built on it*, list the files and commits
   that depend on the pick, so an override knows what to redo. Add the record's row to the
   changeset's `## Deferred Answers` section (`pr-lifecycle/references/changeset.md` §13.5) in the
   same commit. When the change wraps, that row is carried into the changelog or history entry.
4. **List it** in the end-of-turn summary (§ 4) and in the PR body.

**Ask everything you can ahead of time.** A flow that has a planned interactive moment — the
`/yolo-pr-stack` opening interview — uses it for every question the run can foresee, not only the
ones its interview script lists. Think ahead to choices that pass 1 and pass 2, green and wrap would
otherwise record as deferred answers: naming visible to users, an API shape, a library, how a slice
is split, which of two behaviours wins. A deferred answer is the fallback for questions nobody could
have foreseen. It is not a way to postpone an interview.

### What becomes a deferred answer, and what stays a halt

A ⛔ halt ends the row and does not ask mid-turn, so it is compatible with `#yolo`. What changes is
which halts still happen:

| The moment | Under `#yolo` |
|---|---|
| A requirements interview, a clarifying question, a choice between designs, names, libraries or behaviours | **Deferred answer** — pick and carry on |
| A ⛔ whose options are all actions the agent may take itself: which changeset to use when two resolve, sweeping a partial stack now or waiting, which of two valid fixes to apply | **Deferred answer** |
| A ⛔ that asks for the developer's **word** — a deferral of planned scope, the `/yolo-pr-stack` TODO gate (*continue / defer*), V4 manual-verification consent | **Stays a halt.** A blanket `#yolo` is not that word, just as `/yolo` is not (`yolo.md` § *Halts no invocation can pre-approve*) |
| A safety stop — nothing red, a broken build, an ancestor stub, a leak, the same check red on a third push | **Stays a halt** |
| An action the repo reserves for the developer — a new dependency, deleting a file the plan did not name, a retrigger, a merge without `#automerge` | **Stays a halt**, unless one of the options avoids the action. Then picking that option is a deferred answer, and the record says which option was set aside because it needed the developer |

Every `NEVER` in `README.md` stands. A deferred answer never picks a fallback, a test-only branch
in production code, a suppression or anything else the repo forbids, even when that is the cheapest
option.

**Product or Technical.** A question about *what* the product does — a requirement, the visible
behaviour, copy, a name the user sees, the scope of a slice — is **Product**. A question about
*how* it is built — a design, a structure, a library, a test seam — is **Technical**. The kind
decides where the record lives (the record reference § *Where it lives*).

## 2. A supervisor — relay before you act

A **supervisor** is the agent that started you and owns the plan: the `/yolo-pr-stack` orchestrator
for its `[G]` / `[W]` / `[F]` stages, any orchestrator for the subagents it briefs. A
`composer-subagent` **driver is not a supervisor.** It is a transport, so it passes the Muse
agent's question up to the orchestrator unchanged and never answers it itself.

**The asker** — the subagent with the question:

1. Writes the record with the *Question* and *Options as asked* sections, its recommendation
   included, and `**Status:** Awaiting supervisor`.
2. **Does not act on the question.** It finishes any work that does not depend on the answer, and
   commits and pushes as its brief requires. It then ends its turn with the report status
   `❓ question`, naming the record path and nothing else.

**The supervisor**, on a `❓ question` report:

1. Reads the record, and decides from what it knows that the asker does not: the plan, the other
   nodes, the developer's interview answers.
   - **Answered** — one of the asker's options, with why.
   - **Refined** — the options rewritten (one merged, one dropped, one added), its own
     recommendation, and that recommendation as the pick.
2. Sends the review to the **same** agent (`SendMessage`), so the asker keeps its context and its
   model and effort. The message carries the *Supervisor review* section verbatim.
3. Is itself under `#yolo`. Its verdict is still a deferred answer for the developer to review,
   **not** the developer's word. It may not use the relay to settle anything § 1 keeps as a halt.

**The asker, resumed**, pastes the *Supervisor review* section into the record verbatim, sets
`**Decision:**` to the supervisor's pick and `**Status:** Awaiting review`, commits the record with
the work that follows from it, and carries on.

**Both versions are kept.** *Options as asked* is never edited after the relay. The developer
reviews both the asker's question and the supervisor's reading of it, and the difference between
them is often the most useful thing in the record.

If the asker can no longer be resumed (context exhausted, harness restarted), start a fresh agent
on the same brief, the same model and the same effort. Give it the record path, say the supervisor
review is already decided, and say so in the ledger. A supervisor that is itself a subagent relays
up the same way. The top of the chain has no supervisor and picks.

## 3. No permission prompts — bound every tool output

A harness may move an oversized tool result into a file outside the workspace. Claude Code writes
it under `~/.claude/projects/<project>/<session>/tool-results/` and hands back only a preview.
Reading that file then raises a permission prompt. A settings allow rule does not reliably stop
that prompt, and in an unattended run it waits on a *Yes* nobody will click. So under `#yolo`
**no tool call may produce a result large enough to be moved into a file**:

- **Bound every command.** Filter for the lines that matter (`grep`, `--jq`, `--json <fields>`,
  `--name-only`, `--stat`, `-q` / `--quiet`, `--reporter=dot`), then cap what remains
  (`| tail -n 80`, `| head -n 120`, `| head -c 8000`). A test run's useful part is its failures and
  its totals. A log's useful part is the lines around the error.
- **Send long output to a file in the workspace**, then read slices of it. Use the session's
  scratchpad when the harness gives one, else the repo's git-ignored `tmp/`. For example
  `uv run pytest -q`, then
  `grep -n` or `sed -n 'a,bp'` for more.
- **Read files in ranges.** Use `Read` with `offset` / `limit`, or `sed -n`, on anything long. Never
  read a whole generated file, lockfile, bundle or JSON dump.
- **Never read a moved tool result.** When a preview says the full output was saved to a path under
  the harness's own directory, do not open that path. Run the command again, bounded.
- **MCP and `gh api` calls select fields.** Use `--jq`, `--paginate --jq` with a projection, or the
  tool's own filter or limit parameter. Never take a whole paginated listing or a raw log.

The same holds for subagents: the `#yolo` line in their brief carries the rule.

## 4. The summary — every deferred answer, listed

Every end-of-turn summary under `#yolo` carries a **Deferred answers** section, after **Decided
without review** (`pr-lifecycle` skill § *Summary*). It has one row for each record written or
reviewed this turn:

```markdown
### Deferred answers  (#yolo — awaiting your review)
| Record | Kind | Question | Asker's pick | Supervisor | Decision |
|--------|------|----------|--------------|------------|----------|
| `src/surmap/surmap-server/docs/deferred-answers/2026-10-23-caption-store.md` | Technical | Where do user captions persist? | b) dataset row | Refined → c) sidecar file | c) |
| `docs/src/surmap/deferred-answers/2026-10-23-captions-empty-state.md` | Product | What does an empty captions list show? | a) hint text | — | a) |
```

When nothing was deferred, one line: *"No deferred answers."* The same rows live in the changeset's
`## Deferred Answers` section while the change is in flight, and in its changelog / history entries
after the wrap (`/wrap-context-docs` step 7c). An orchestrator's final report merges
its subagents' rows, one table for the whole run. The same table goes into the PR description as a
`## Deferred answers` section, kept in sync like `## Workflow` (`pr-lifecycle` skill § *PR
description*). A reviewer sees the open decisions on the PR page, and so does the developer after a
merge.

**The developer answers them later, when asked.** `/review-deferred-answers` asks the open
records in any scope, during the PR or after the wrap and the merge. It deletes each one the
developer answers, and turns an override that needs code into a TODO.

**Open deferred answers do not gate Approve or Land.** `#skipreview` and `#automerge` go ahead when
their own gates hold. The records stay in the package or area docs after the merge, so a merged
decision is still waiting for the developer. The summary table is not the only copy.

## `#ask` — YOLO, but the developer may be asked

`#ask` keeps everything `#yolo` changes except § 1's first rule. Where `#yolo` would record a
deferred answer, the **top of the chain** asks the developer live, with the same options and the
same recommendation. Then:

- **The developer answers** → act on the answer. Nothing is recorded as a deferred answer, because
  it is not deferred. The summary lists it under **Decided without review**, as *asked: … → …*.
- **A subagent's question** is still relayed to its supervisor (§ 2). The supervisor answers it
  when it can. When it cannot, it asks the developer and sends the developer's answer back, and the
  record is deleted before it is committed.
- **Ask in batches.** Collect the questions that are open at the same moment into one ask rather
  than one each. Stages that do not depend on the answer keep running while it is pending.
- **Halts stay halts.** `#ask` permits questions. It does not turn a halt that asks for the
  developer's word into a mid-turn question.

## Rules

- **Under `#yolo`, never ask.** Record, relay if there is a supervisor, pick, carry on, list it.
- **Ask ahead.** A planned interactive moment asks every question the run can foresee.
- **Halts that ask for the developer's word stay halts.** A deferred answer only picks among
  options the agent may carry out itself.
- **Both versions are kept** — *Options as asked* is never rewritten after a supervisor's review.
- **Bound every tool output.** Under `#yolo`, a result big enough to be moved into a file is a
  stalled run.
- **List every deferred answer** in the summary and in the PR body. They never gate Approve or Land.
