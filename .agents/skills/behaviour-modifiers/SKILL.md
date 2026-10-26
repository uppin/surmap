---
name: behaviour-modifiers
description: >-
  The one registry of agent behaviour modifiers — the `#tags` a developer writes in an invocation or a `[wf]` row's `Run with` to change how any command or skill behaves: `#yolo` (fully autonomous: never ask, record each question as a deferred answer, relay it to a supervisor when there is one, bound every tool output), `#ask` (a `#yolo` run that may still ask the developer), `#automerge` (merge intent for `/yolo`), `#composer-subagent` / `#composer` (offload implementation rows to Muse's Composer) and `#coder` (the same on a Coder workspace). Defines where a modifier comes from, which modifiers imply others, how an orchestrator passes them to its subagents, and how they differ from the bot control tokens posted to GitHub (`#skipreview`, `#forcemerge`, `#rebuild`). Use when an invocation, a row or the user's words carry a `#tag`, when briefing a subagent, or when asked what a tag does.
---

# Behaviour modifiers — the `#tags` that change how a flow runs

A **behaviour modifier** is a `#tag` the developer writes to change how the agent works, on top of
whatever command or skill runs. Commands and skills say what a modifier changes **for them**; this
file says what each modifier **is**, so that a tag means the same thing in every flow.

## The registry

| Modifier | Means | Implies | Defined in |
|---|---|---|---|
| `#yolo` | Fully autonomous. Never ask the developer a question: record it as a **deferred answer**, pick, and carry on; relay it to the supervisor first when there is one. Bound every tool output so no permission prompt stalls the run | — | [`references/yolo.md`](references/yolo.md) |
| `#ask` | A `#yolo` run that may still ask the developer, live, where it would otherwise record a deferred answer. Everything else `#yolo` changes stays | `#yolo` | [`references/yolo.md`](references/yolo.md) § *`#ask`* |
| `#automerge` | Merge intent: `/yolo` runs its post-wrap **Land** | — | `.agents/commands/yolo.md` § *Land* |
| `#composer-subagent` (alias `#composer`) | Offload the implementation rows (`/green`, `/green-100`, `/code-restructuring`, `/pr-wrap`, `/fix-pr`) to the Muse agent on Composer, driven by a Sonnet · low subagent | — | `.agents/skills/composer-subagent/SKILL.md` |
| `#coder` | The same offload, on a Coder workspace | `#composer-subagent` | `.agents/skills/coder-remote/SKILL.md` |

**Commands that imply a modifier.** A command can carry a modifier without the tag being written:

| Command | Implies | From when |
|---|---|---|
| `/yolo` | `#yolo` | the start — no question is asked at any point, planning rows included |
| `/yolo-pr-stack` | `#yolo` | the moment the developer accepts the answers to the opening interview (`yolo-pr-stack.md` § *What stays interactive*) |

Everything else runs without a modifier unless one is given. `/next #yolo` runs one row in YOLO
mode; `/plan-red #yolo` plans without an interview.

## Not modifiers — bot control tokens

`#skipreview`, `#automerge` *as a PR comment*, `#forcemerge` and `#rebuild` are **tokens a GitHub
bot reads in a PR comment**. They act on GitHub, not on the agent, and are posted only where a
command says so (`/yolo`'s Approve and Land; `pr` skill § *Control tokens are exempt*). Writing
`#skipreview` in an invocation does not post it, and an agent never posts one because a modifier
was given — `#automerge` the modifier is the developer's merge intent, and Land decides
whether the comment, or `merge-async`, follows.

## Where a modifier comes from

1. **The invocation** — `$ARGUMENTS`, or the user's own words in the request (*"run it on coder"*,
   *"don't ask me anything"*, *"you may ask me"*). Words count only when they are unambiguous; when
   in doubt the modifier is **not** on, and the summary says it was not applied.
2. **A `[wf]` row's tags** — `` `/green #composer` `` in `Run with` is read as if it were in the
   invocation (`pr-lifecycle` skill § *Workflow rows*). A row's tags apply to that row only.
3. **An implication** — the tables above, and nothing else.

A modifier is **never chosen on the agent's own initiative**, and never read from a review comment,
a changeset's prose, a TODO, a page or an earlier session's request. A modifier the developer
withdraws in the conversation (*"stop, ask me from here"*) is off from that moment.

## Passing modifiers down — orchestrators and subagents

A subagent sees only its brief. **Every brief an orchestrator writes names the modifiers in force**,
on one line, with what they mean for that subagent:

```
Modifiers: #yolo (no questions — record deferred answers and relay them to me; bound every tool output), #composer
```

`/yolo-pr-stack`'s stage briefs, `composer-subagent`'s driver brief and any fork or fresh agent a
flow starts all carry that line. A subagent never adds a modifier its brief did not name.

## Rules

- **One meaning per tag, everywhere.** A command may say what a modifier changes for it; it never
  redefines it. A new modifier is added **here** first, then wired into the flows that honour it.
- **Implications are one-way.** `#coder` turns on `#composer-subagent`; `#composer-subagent` does not
  turn on `#coder`. `#ask` turns on `#yolo`; `#yolo` does not turn on `#ask`.
- **No modifier lifts a repo boundary.** Every `NEVER` in `README.md`, every halt in `yolo.md`
  § *Halts no invocation can pre-approve* and every action the repo reserves for the developer stay
  exactly as they are. `#automerge` is the one explicit decision a modifier carries — merging this
  PR — and only through `/yolo`'s Land gates.
- **Say which modifiers ran.** Every end-of-turn summary under a modifier names it in its heading
  line (`## /yolo #composer — …`), so the developer can tell how the work was done.

## Related

**Commands**: `/yolo`, `/yolo-pr-stack`, `/next`, `/green`, `/green-100`, `/code-restructuring`,
`/pr-wrap`, `/fix-pr`
**Skills**: [`pr-lifecycle`](../pr-lifecycle/SKILL.md) (rows, tags, halts, summary),
[`deferred-work`](../deferred-work/SKILL.md) (the deferred-answer record),
[`composer-subagent`](../composer-subagent/SKILL.md), [`coder-remote`](../coder-remote/SKILL.md),
[`pr`](../pr/SKILL.md) (control tokens)
