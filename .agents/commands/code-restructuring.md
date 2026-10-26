---
description: Restructure code without writing any of it by hand - split an oversized file, extract a method, move a symbol, rename across a codebase, via a reviewable plan of refactoring intents
---
## Code Restructuring

**Mandatory first step**

1. Read the full project skill (source of truth):
   - `.agents/skills/code-restructuring/SKILL.md`

Follow that skill end-to-end. It is the only place the workflow is defined; this file exists so the
workflow is reachable as `/code-restructuring` on every harness, since `.claude/commands`,
`.muse/commands` and Codex all resolve slash commands from `.agents/commands/`.

**Workflow row**: this command follows the step contract in
`.agents/skills/pr-lifecycle/SKILL.md`. It owns both rows of the restructure preset — **Plan**
(skill steps 0–6) and **Restructure** (steps 7–8) — and runs them in order; the skill's *Workflow row*
section says what each records in Result, what halts it, and the **Row TODOs** each seeds.

**The rule that shapes everything**: you never write the moved or extracted code. You write a plan of
*intents*, and `surmap` resolves each one through the language's own engine — the
For Python, `rope` (see the `code-restructuring` skill for the other engines it drives).

Non-negotiables from the skill, so they are visible before you start:

- **Commands share one warm `restructure` instance per checkout.** It exits after 15 idle minutes;
  run `restructure daemon stop` in a worktree you are about to remove, and read its log (path in the
  skill, step 0) before anything else when a run stalls.

- **A green baseline first, and the same green after** (steps 1 and 7). A restructure's claim to
  preserve behaviour is a comparison between two states; without the "before" there is nothing to
  compare. A red baseline **halts the row** — with one carve-out, below.
- **Its own changeset**, `Type: Refactor`, no PRD, no acceptance tests
  (`.agents/skills/pr-lifecycle/references/restructure.md`). It is what a reviewer
  reads instead of a thousand-line diff.
- **Run `/analyze-code-issues` first** (step 1.5) and read the target package's existing
  `<package-dir>/docs/code-issues/` records — some of the seams are already
  written down, with hand-verification notes. Close the ones this run resolves; file the ones it does
  not.
- **Never put code in a plan**, never declare a new file, and treat an unsupported operation as a
  hard error rather than a licence to retype by hand. Check the coverage table in
  `references/plan-schema.md` before planning against Rust or Python.
- **Delete the plan once it is applied** (step 8). It lives at
  `<package-dir>/restructure/<changeset-slug>/plan.jsonl` only until the baseline is green again; a
  spent `plan.jsonl` never goes up for review and never reaches `master`.

### Running as another changeset's restructure prerequisite

When a feature changeset's `## Prerequisites` names this run (see the `deferred-work` skill), it is
invoked by `/green` **step 0.5**, before any implementation. The branch is then red **by design** —
`/plan-red` wrote failing tests — so the baseline is *green except that changeset's own planned red
tests*, listed by name in the restructure changeset's `## Baseline` as known-red. Anything red that
is not on that list still halts — the Green row, since that is the row this run belongs to — and after
the apply each known-red test must still fail **for the same reason**.

## Composer offload (`#composer-subagent`, `#coder`)

With `#composer-subagent` (or `#composer`) in the request, this command's work is done by the Muse
agent (`agent -p`) on the newest Composer model, driven by a Sonnet · low subagent — the
`composer-subagent` skill (`.agents/skills/composer-subagent/SKILL.md`), stage G (with this file in place of `green.md`), with the
skill's **row consent**. `#coder` does the same on a Coder workspace (`coder-remote` skill) and implies
`#composer-subagent`. The main agent readies the host (guiding the user through a missing Muse agent
CLI or login), runs the preflight, briefs the driver, reports a halt — the row's ⛔, written, committed and pushed by the Muse agent — in its
end-of-turn summary, and verifies the result. Every step of this file still runs; only who types changes. Under `/yolo-pr-stack` a Refactor node's `[G]` stage is exactly this.
Only on request — never chosen on the agent's own initiative. Every modifier this command honours,
`#yolo` included, is defined once in the `behaviour-modifiers` skill
(`.agents/skills/behaviour-modifiers/SKILL.md`).

## Related

**Commands**: `/analyze-code-issues` (mandatory targeting pass), `/green` (runs this as a
prerequisite at step 0.5), `/plan-red`, `/plan-pr-stack`, `/wrap-context-docs`
**Skills**: `code-restructuring` (`.agents/skills/code-restructuring/SKILL.md`),
`analyze-code-issues`, `deferred-work` (`.agents/skills/deferred-work/SKILL.md`)
