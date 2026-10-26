# All Skills Guide

This guide explains how the repo's current `.agents` setup works in Codex.

Use it when:
- the user asks which skill to use
- the user refers to an old Muse command or subagent
- you want to map an intent to the right skill quickly

## Mental Model

In this repo:

- `skills` are the primary reusable workflows
- `prompts` are supporting playbooks and source material
- Muse `subagents` remain in `.muse/agents/`; broader skills carry the same behaviour elsewhere

If the user mentions an old Muse slash command, do not assume slash commands exist. Suggest the closest skill and show how to invoke it explicitly.

## Active Skills

### Core Workflow Skills

- `planning`
  Use for general feature planning, requirement changes, and turning informal planning into formal docs.
  Persist Explore / Discovery dumps in `docs/<area>/1-WIP/{slug}-initial-discovery.md`; the changeset
  opens with `## Initial Discovery` linking to that companion; wrap deletes it.
  **Last Revised**: 2026-08-26

- `tdd`
  Use for one-shot TDD planning, test-first implementation, acceptance-test-first delivery, red/green work, bug reproduction, and exploratory green investigations.
  **Last Revised**: 2026-03-16

- `plan-tdd-one-shot`
  Use for one-shot TDD planning (PRD, `{slug}-initial-discovery.md`, changeset, acceptance-test-first milestones).
  **Last Revised**: 2026-08-26

- `testing`
  Use for fixing failing tests, validating test quality, acceptance-test review, and last-resort test skipping.
  **Last Revised**: 2026-03-16

- `coding`
  Use for production-readiness checks, change-risk validation, and code quality review before PRs.
  **Last Revised**: 2026-03-16

- `code-cleaning`
  Use for refinement, cleanup, progress-doc updates, and PR-wrap style finishing work.
  **Last Revised**: 2026-08-26

- `analyze-code-issues`
  Use before `code-restructuring` to run tool-backed targeting: CRAP scoring, coverage gaps, and git hot-files via `surmap`. Persists one file per verified finding in `<package-dir>/docs/code-issues/`, which planning then reads. Invoke `/analyze-code-issues`.
  **Last Revised**: 2026-09-09

- `deferred-work`
  Use when planning a changeset or stack, when something cannot be finished, when a `#yolo` run would have asked a question, or when landing a stack. Owns the file-per-item records for work not done and decisions not reviewed — changeset TODOs in `<package-dir>/docs/todo/`, code issues in `<package-dir>/docs/code-issues/`, and deferred answers in `<package-dir>/docs/deferred-answers/` (Technical) / `docs/<area>/deferred-answers/` (Product) — the bar for deferring planned scope at all (named blocker, refuted alternatives, recorded consent), planning Step 2b, `/pr-wrap` step 7.6 (list what this PR added and wait), and `/fix-pr-stack` / `/merge-pr-stack` reckoning.
  **Last Revised**: 2026-10-23

- `behaviour-modifiers`
  Use when an invocation, a `[wf]` row or the user's words carry a `#tag`, when briefing a subagent, or when asked what a tag does. The one registry: `#yolo` (never ask — record a deferred answer, relay it to the supervisor first, pick, list it; bound every tool output so no permission prompt stalls an unattended run; `references/yolo.md`), `#ask` (YOLO that may ask), `#automerge`, `#composer-subagent`/`#composer`, `#coder`; `/yolo` implies `#yolo`, `/yolo-pr-stack` after its accepted interview.
  **Last Revised**: 2026-10-23

- `code-restructuring`
  Use for a pure restructure — split an oversized file, extract a method, move a symbol, rename across a codebase — driven by a reviewable plan of refactoring intents rather than by hand. Invoke `/code-restructuring`.
  **Last Revised**: 2026-09-09

- `pr`
  Use for PR creation, PR updates, merges, branch splitting, splitting a PR into a stacked sequence (`/split-pr-to-stack`), adding a new draft PR on top of a registered stack (`/add-to-pr-stack`), preparing a stack to land (`/fix-pr-stack`), landing it (`/merge-pr-stack`), addressing review threads (`/fix-pr`), and branch cleanup.
  **Last Revised**: 2026-09-12

- `pr-stack`
  Use for any stacked-PR work: planning a stack (`/plan-pr-stack` — every PR it opens is a stack
  member, including ground-softening nodes), adding an ad-hoc draft PR at the tail (`/add-to-pr-stack`),
  splitting an existing PR into stacked slices (`A→B→C` → `A→B1→B2→C`), rebasing one stack branch,
  preparing a stack to land (`/fix-pr-stack`), landing it (`/merge-pr-stack`), or a follow-up off an
  open PR. Requires the `gh stack` extension.
  **Last Revised**: 2026-09-12

### Support Skills

- `debugging`
  Use for structured investigation and root-cause analysis.
  **Last Revised**: 2026-03-15

- `analyze-third-party`
  Use for studying an external repo or unfamiliar vendor codebase.
  **Last Revised**: 2026-03-16

- `tech-stack`
  Use for internal stack guidance, package conventions, and Rust/WASM-specific patterns.
  **Last Revised**: 2026-03-16

- `repo-maintenance`
  Use for repo-wide upkeep, KB docs, MCP/tooling checks, backlog maintenance, and system-level guidance.
  **Last Revised**: 2026-03-16

### Domain Skills

- `hexagon-testable-architecture`
  **Last Revised**: 2026-03-15
- `add-e2e-test`
  **Last Revised**: 2026-03-15
- `ci-build`
  Use when debugging CI/Nx/WASM CI failures or changing the WASM target graph. Timeout for each target is 15 minutes; CI comments final status in PR comments when the build finishes.
  **Last Revised**: 2026-08-18
- `analyze-code-issues`
  Use before restructuring to score CRAP, coverage gaps, and git churn via `surmap`. Mandatory prerequisite to `code-restructuring` step 1.5; step 7 persists each verified finding to `<package-dir>/docs/code-issues/`. Invoke `/analyze-code-issues`.
  **Last Revised**: 2026-09-09
- `deferred-work`
  Use when planning, deferring, wrapping, or landing a stack. The `<package-dir>/docs/todo/` and `<package-dir>/docs/code-issues/` records, the deferral bar, planning Step 2b, `/pr-wrap` step 7.6, and `/fix-pr-stack` / `/merge-pr-stack` reckoning.
  **Last Revised**: 2026-09-12
- `trace-ci-build`
  Use to poll a running CI PR build or, on failure, explain logs vs the PR diff (flake vs timeout vs real breakage vs CI standards). Invoke `/trace-ci-build`. Requires Developer Portal + GitHub + -standards MCPs (Slack optional).
  **Last Revised**: 2026-08-18
- `analyze-build-issues`
  Use for fleet-level CI health rather than one build: which builds breach 10 minutes and why (including whether CI over-selected packages the diff cannot explain), why master is red, which targets are flaky vs genuinely broken, and which merged PRs were `#forcemerge`d past a red build. Invoke `/analyze-build-issues`. Writes a report to `tmp/build-analysis/`. Requires Developer Portal MCP + `gh`.
  **Last Revised**: 2026-08-26
- `trace-request`
  Use when the user gives a Request ID and a question about what the request did.
  **Last Revised**: 2026-08-18
- `product-overview`
  Use to answer what SurMap is and whether it can do a given thing: derive the answer from the named source of truth (`README.md` scope, `docs/architecture.md`, the contracts in `src/surmap/types.py`, the tests), quote it with path and date, and say whether it ships, is in progress or is a documented limit; designed is not the same as implemented.
  **Last Revised**: 2026-10-20
- `product-reports`
  Use to triage new Product reports from the product-reports Slack channel (`C0C99TBM4J3`) through `@mcp-s/cli`'s `slack` server: a ledger outside the repo says what is new, fields are parsed only above the untrusted note, reports are classified and routed. Invoke `/product-reports`; Slack actions follow the [shared posting rule](../../product-reports/SKILL.md#slack-posting-rule).
  **Last Revised**: 2026-10-16
- `product-report-investigation`
  Use to investigate one Product report, run id or failure time: fleet check (worker crashes, Vault boot failures), the run by `runId` in app-logs, one step via `/trace-request` and the access log, the release tag that ran, a synthetic reproduction (test, bench k of N, or a local reproduction), and a five-class diagnosis. Read-only in production; Slack actions follow the [shared posting rule](../../product-reports/SKILL.md#slack-posting-rule).
  **Last Revised**: 2026-10-16
- `product-report-to-pr`
  Use only for a demonstrated, reproduced Product defect: a reproduction-first `/plan-red` brief, then `/yolo` without merge intent (`#skipreview` allowed; no `#automerge`, no merge), a `product-report-origin:` line in the PR body, an SHA-pinned handoff and a report-thread reply under the [shared posting rule](../../product-reports/SKILL.md#slack-posting-rule).
  **Last Revised**: 2026-10-16
- `composer-subagent`
  Use only when the user asks to offload implementation to Muse's Composer (`#composer-subagent`, `#composer`, or `#coder`, which implies it): `scripts/composer-agent.sh <cmd> <host>` (`local` or a Coder workspace) — `ensure` checks jq (+ tmux/flock on a workspace), the agent CLI and its login and prints the newest `COMPOSER_MODEL` (on this machine it never installs or logs in: it tells the user what to run); `run`/`wait`/`progress`/`summary`/`cancel` drive `agent -p` turns whose stream-json lands in `~/.composer-runs/<name>/` on the host (a detached process group locally, tmux on a workspace); `--resume` continues one session. Subagents are Sonnet·low drivers briefed with `references/driver-brief.md` (stage G/W/F prompts, one row consent: a halt comes back as the row's ⛔ with `STATUS: stopped`). Wired into `/green`, `/green-100`, `/code-restructuring`, `/pr-wrap`, `/fix-pr`, the rows `/yolo` runs and `/yolo-pr-stack` § Composer mode. Planning never leaves the session.
- `coder-remote`
  Use only when the user asks for remote work on a Coder workspace (in words or with `#coder`, which implies `composer-subagent`): `scripts/coder-remote.sh` lists/starts workspaces, `setup` provisions a new one (tools, GitHub SSH, repo clone — `references/workspace-setup.md` guides creating it when the developer has none), `ensure` repairs the uv run pytest -q and checks the `gh` login (a missing login is the user's to fix over `coder ssh`), and creates worktrees under `~/Code/this repo/.worktrees/`. `scripts/coder-transport.sh` is the shared `coder ssh` transport (base64 argv, CRLF strip, real exit status, autostart disabled). The main agent owns every restart; turns go through `composer-subagent`'s script with the workspace as host.
  **Last Revised**: 2026-10-13


## Prompt-Only Playbooks

Not every restored prompt should be treated as a first-class skill trigger.

Use prompts directly when you need a narrow playbook without promoting it into a dedicated skill. Examples in the current repo include:

- `plan-tdd-migration.md`
  **Last Revised**: 2026-03-16
- `pr-wrap-offload.md`
  **Last Revised**: 2026-03-16
- `prototype.md`
  **Last Revised**: 2026-03-16
- `update-stubs-n-polyfills.md`
  **Last Revised**: 2026-03-16
- `visual-inspection.md`
  **Last Revised**: 2026-03-16

## How To Invoke A Skill

In this repo, prefer the shortcut style:

```text
$some-skill <intent>
```

You can still use plain language, but the shortcut form is the preferred convention.

Examples:

```text
$planning create the PRD and technical changeset for this feature
```

```text
$tdd drive this feature from failing tests to implementation
```

```text
$testing diagnose and fix the current test failures
```

```text
$coding review whether this branch is production-ready
```

```text
$pr prepare this branch for PR and summarize what should be committed
```

```text
$plan-ft plan this survey feature from the architecture doc
```

## Muse Intent -> Codex Skill

Use this section when the user refers to old Muse habits.

### Planning Intents

- Old Muse intent: `/plan-ft`
  Use: `planning`
  Example:
  `$planning create the product planning docs for this feature`

- Old Muse intent: `/plan-ft-dev`
  Use: `planning`
  Example:
  `$planning create the technical changeset for this feature`

- Old Muse intent: `/plan-pr-stack`
  Use: `planning` (alternative to `/plan-red` when the work spans a stack of dependent PRs)
  Example:
  `$planning plan this as a stack of dependent draft PRs, each with its own PRD, changeset, stub API, and failing tests`

- Old Muse intent: `/plan-tdd-one-shot`
  Use: `tdd`
  Example:
  `$tdd produce the PRD, changeset, and detailed TDD rollout plan`

- Old Muse intent: `/requirements-change`
  Use: `planning`
  Example:
  `$planning update the requirement docs for this scope change`

- Old Muse intent: `/plan-to-context`
  Use: `planning`
  Example:
  `$planning turn this rough plan into proper product and technical docs`

### TDD And Test Intents

- Old Muse intent: `/red`
  Use: `tdd`
  Example:
  `$tdd write the failing tests for this feature first`

- Old Muse intent: `/green`
  Use: `tdd`
  Example:
  `$tdd implement the smallest production-quality fix for the current failing tests`

- Slash command: `/next`
  Runs one `[wf]` row of the changeset (`pr-lifecycle/SKILL.md`) — the next row by its grep, with its command; a ⏳ row resumes at its first open TODO
  Example:
  `/next` — or `$tdd` / `$code-cleaning` / `$pr` for the row's command by hand

- Slash command: `/yolo` (`/yolo #automerge` to land)
  Runs every `[wf]` row in order until all are done or one halts ⛔, then posts `#skipreview`; with `#automerge`, waits for stack predecessors and posts `#automerge`
  Example:
  `/yolo` — ready to merge; `/yolo #automerge` — merged

- Old Muse intent: `/green-attack`
  Use: `tdd`
  Example:
  `$tdd explore multiple implementation approaches without forcing the tests green yet`

- Old Muse intent: `/reproduce`
  Use: `tdd`
  Example:
  `$tdd reproduce this bug with a failing test`

- Old Muse intent: `/fix-tests`
  Use: `testing`
  Example:
  `$testing fix the failing test suite without papering over production issues`

- Old Muse intent: `/fix-tests-focused`
  Use: `testing`
  Example:
  `$testing investigate the failing tests one by one with focused debug output`

- Old Muse intent: `/validate-tests`
  Use: `testing`
  Example:
  `$testing review whether these tests follow the repo's quality standards`

- Old Muse intent: `/skip-tests`
  Use: `testing`
  Example:
  `$testing evaluate whether any of these test skips are justified and document them properly`

### Validation And Cleanup Intents

- Old Muse intent: `/validate-changes`
  Use: `coding`
  Example:
  `$coding review the branch for change risk and unsafe behavior`

- Old Muse intent: `/validate-prod-ready`
  Use: `coding`
  Example:
  `$coding check whether this work is actually production-ready`

- Old Muse intent: `/analyze-clean-code`
  Use: `coding`
  Example:
  `$coding analyze code quality and call out the highest-value cleanup`

- Old Muse intent: `/refine`
  Use: `code-cleaning`
  Example:
  `$code-cleaning refine this implementation based on feedback`

- Old Muse intent: `/update-context-docs`
  Use: `code-cleaning`
  Example:
  `$code-cleaning sync the in-progress docs with the current implementation`

- Old Muse intent: `/wrap-context-docs`
  Use: `code-cleaning`
  Example:
  `$code-cleaning perform the final doc wrap-up for this completed change`

- Old Muse intent: `/pr-wrap`
  Use: `code-cleaning`
  Example:
  `$code-cleaning do the final PR-wrap style cleanup before review`

### PR And Branch Intents

- Old Muse intent: `/pr`
  Use: `pr`
  Example:
  `$pr create, update, or land a PR (/fix-pr for review threads + checks; /fix-pr-stack then /merge-pr-stack for a registered stack)`

- Old Muse intent: `/update-pr`
  Use: `pr`
  Example:
  `$pr update the current PR after these follow-up changes`

- Old Muse intent: `/merge`
  Use: `pr`
  Example:
  `$pr merge this branch up to date with its actual base (not master)`

- Old Muse intent: `/repoint`
  Use: `pr`
  Example:
  `$pr repoint this stacked branch onto origin/master now that its predecessor merged`

- Old Muse intent: `/squash-pr`
  Use: `pr`
  Example:
  `$pr squash-land this PR (or fold it into its base PR)`

- Old Muse intent: `/follow-up-branch`
  Use: `pr`
  Example:
  `$pr start a follow-up branch based on this open PR`

- Old Muse intent: `/add-to-pr-stack`
  Use: `pr` (and the `pr-stack` skill)
  Example:
  `$pr add a new draft PR on top of the current stack`

- Slash command: `/fix-pr-stack`
  Use: `pr-stack`
  Example:
  `$pr-stack wait for CI/review bot, sweep threads, plan TODOs (rescope or add tail PRs), rebase, and push local-gated fixes`

- Slash command: `/merge-pr-stack`
  Use: `pr-stack`
  Example:
  `$pr-stack merge the stack now that /fix-pr-stack has pushed`

- Slash command: `/fix-pr`
  Use: `pr`
  Example:
  `$pr address this PR's review threads (full discussion, including human replies to bots) and failing checks`

- Old Muse intent: `/split-branch`
  Use: `pr`
  Example:
  `$pr split this work into separate branches`

- Old Muse intent: `/split-pr-to-stack`
  Use: `pr` (and the `pr-stack` skill)
  Example:
  `$pr split this PR into a stacked sequence so A→B→C becomes A→B1→B2→C`

- Old Muse intent: `/cleanup-local-branches`
  Use: `pr`
  Example:
  `$pr clean up local branches that are no longer needed`

### Investigation And Repo Intents

- Old Muse intent: `/investigate`
  Use: `debugging`
  Example:
  `$debugging investigate this issue and produce a root-cause summary`

- Slash command: `/trace-ci-build`
  Use: `trace-ci-build`
  Example:
  `$trace-ci-build` or `/trace-ci-build 1234 why did wasm fail?`

- Old Muse intent: `/analyze-third-party`
  Use: `analyze-third-party`
  Example:
  `$analyze-third-party inspect this external repository and summarize integration risks`

- Intent: `/review-deferred-answers`
  Use: `deferred-work` (the deferred-answer record) — asks the open `#yolo` decisions in a scope, deletes each one answered, turns an override that needs code into an `Overridden answer` TODO
  Example:
  `/review-deferred-answers PR #3812`

- Old Muse intent: `/tech-backlog`
  Use: `repo-maintenance`
  Example:
  `$repo-maintenance turn these rough ideas into backlog items`

- Old Muse intent: `/inspect-ide-mcp-servers`
  Use: `repo-maintenance`
  Example:
  `$repo-maintenance inspect the MCP setup and highlight issues`

- Old Muse intent: `/test-mcp`
  Use: `repo-maintenance`
  Example:
  `$repo-maintenance test this MCP server and summarize the result`

- Old Muse intent: `/create-kb`
  Use: `repo-maintenance`
  Example:
  `$repo-maintenance create a knowledge-base article for this topic`

- Old Muse intent: `/update-all-rules`
  Use: `repo-maintenance`
  Example:
  `$repo-maintenance update all rules`

### Technology And Domain Intents

- Old Muse intent: `@tech-stack`
  Use: `tech-stack`
  Example:
  `$tech-stack guide this architecture decision`

- Old Muse intent: `@native-package`
  Use: `tech-stack`
  Example:
  `$tech-stack check whether this native dependency (RTAB-Map pattern) follows repo conventions`

## Subagents

These no longer live as a separate filesystem concept.

- `test-writer` (`.muse/agents/`, Muse) -> `tdd` skill elsewhere
- `tdd-implementer` (`.muse/agents/`, Muse) -> `tdd` skill elsewhere
- `bug-fixer` (`.muse/agents/`, Muse) -> `testing` skill elsewhere
- `refactor` (`.muse/agents/`, Muse) -> `code-cleaning` skill elsewhere

If a user asks for one directly, suggest the owning skill.

Example:

```text
The old `refactor` subagent is now covered by $code-cleaning. $code-cleaning polish this implementation and clean up the docs.
```

## Prompt vs Skill

Prefer a skill when:
- the task is a repeatable workflow
- the user is asking for end-to-end help
- the old Muse command mapped cleanly into a grouped skill

Use a prompt file when:
- you only need one narrow source workflow
- the prompt is still useful as detailed backup material
- no grouped skill should trigger automatically

## Current Drift To Expect

This repo intentionally preserves some legacy Muse prompt material.

- Some prompt files still describe old Muse-only tools or flows.
- Some prompt files are kept as backup playbooks even when the preferred invocation is now a skill.
- Compatibility aliases may exist to help users transition from old names to new skills.

When there is a conflict, prefer:
1. `README.md`
2. the active skill definition
3. this guide
4. legacy prompt text

## Revision Tracking

This guide uses file modification dates as `Last Revised` values, following the same spirit as the old Muse `update-all-rules` workflow.

The maintained playbook for refreshing this guide is:

- `.agents/commands/update-all-rules.md`

Apply these rules when updating this file:

- For skills, use the modification date of `.agents/skills/<skill>/SKILL.md`
- For compatibility aliases, use the modification date of the shim skill's `SKILL.md`
- For prompt-only playbooks, use the modification date of `.agents/commands/<name>.md`
- Update a `Last Revised` value only when the source file is newer than the date currently recorded here
- If a component is removed, remove its entry instead of preserving stale revision data

## If The User Asks "What Should I Use?"

A short answer pattern that works well:

```text
$planning for general planning (or /plan-pr-stack when the work spans a stack of dependent PRs — every PR it opens is a stack member, including ground-softening nodes; /add-to-pr-stack to open a new draft PR at the stack tail), $tdd for one-shot TDD rollout plans and test-first implementation, $testing for broken tests, $coding for readiness review, $code-cleaning for cleanup and PR-wrap style finishing (/pr-wrap lists unresolved TODOs and code issues this PR added and waits), and $pr for PR/merge/stack work (/fix-pr, /fix-pr-stack then /merge-pr-stack, /repoint, /squash-pr, /split-pr-to-stack, /add-to-pr-stack — see .agents/skills/pr-stack/SKILL.md).
```
