---
description: Run tool-backed code issue analysis (CRAP, coverage gaps, git hot-files, dead-code vs missing-tests) before restructuring
---
## Analyze Code Issues

**Mandatory first step**

1. Read the full project skill (source of truth):
   - `.agents/skills/analyze-code-issues/SKILL.md`

Follow that skill end-to-end. Two outputs, both required:

1. A **targeting note** for the developer — top CRAP, coverage gaps, hot files, oversized files,
   type escapes, and the intersections.
2. A **reconciled record**, one file per verified finding, in
   `<package-dir>/docs/code-issues/<category>-<slug>.md`. `**Verified by hand**` is mandatory —
   an unverified analyzer row is a lead, not an issue, and must not be filed as one.

**Most runs are not the first run.** Read the existing record before running anything (skill step
1.5), then match every finding against it before writing (step 7a) — **duplicate issue files are the
failure mode this reconciliation exists to prevent**:

- match by **symbol and file stem independently**, not by filename: a rename or a
  `/code-restructuring` run moves all three parts of the identity, and only a filename lookup calls a
  moved issue new (step 7b);
- a **moved** issue is renamed (`git mv`), a **regressed** one (a deleted record's issue returning) gets a new file citing the deleting commit, a
  **re-categorised** one gets a new file and the old one is deleted — one file per symbol (7b/7d/7e);
- **never delete a record because the tool stopped reporting it** — confirm the *code* changed. Fewer
  coverage tiers than last run is *not comparable*, not *clean* (7c);
- an **update overwrites measurements and appends everything else**: `Measurement history` gains a
  row, hand-verification notes are never deleted, and a run that learned nothing writes nothing but a
  history row (7f).

Report what happened to the record — new / updated / unchanged / deleted (resolved) / regressed / renamed / not
comparable — not just the findings (7h).

Those files are then read by planning: `/plan-red` and `/plan-pr-stack` Step 2b give each relevant
issue a verdict in the changeset's `## Prerequisites`, and one marked `Restructure: required` becomes
that changeset's **Restructure Prerequisite** — executed by `/green` before any implementation.

Do not restructure in this command. `code-restructuring` runs this analysis as its step 1.5 and
consumes the targeting note there.

**Related**: `.agents/skills/deferred-work/SKILL.md` (the bar for deferring),
`deferred-work/references/code-issue-record.md` (the issue-file format, identity rules
and the reconciliation contract), `.agents/skills/code-restructuring/SKILL.md`
