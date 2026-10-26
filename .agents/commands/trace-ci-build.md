---
description: Trace a  CI build — poll while it runs, or on failure explain logs vs the PR diff (including flake vs the 15-minute per-target timeout, and CI standards / CI standards). Requires Developer Portal, GitHub, and -standards MCPs.
---

# Trace CI Build

Trace the CI build for a GitHub PR or a Dev Portal build URL. While the check is running, poll status. When it has failed, pull CI logs, map them to the PR diff, and decide whether the failure is change-caused, flaky, a CI standards break, or a per-target timeout.

Users almost always paste:

- a PR: `<service-url>`
- a build: `<service-url>`

The build URL is resolvable from **GitHub PR checks** or **CI build status**. CI uses **TeamCity** to run the builds; the Dev Portal UUID is the Developer Portal `buildId`.

`$ARGUMENTS` is optional: that URL plus an optional question. No args → current branch's PR.

```
/trace-ci-build [prUrl | buildUrl] [question]
```

Examples:

- `/trace-ci-build <service-url>`
- `/trace-ci-build <service-url> why did wasm fail?`

Peer of **`/trace-request`**: that command starts from a Request ID; this one starts from a CI build / PR check.

## Mandatory first step

Read and execute the skill (source of truth for MCP gate, polling vs forensics, and the report template):

- `.agents/skills/trace-ci-build/SKILL.md`

Also read `.agents/skills/ci-build/SKILL.md` before interpreting a failure in this repo.

Do not improvise a parallel procedure. Follow the skill's phases in order.

## Execution contract

1. If Developer Portal, GitHub, or -standards MCPs are not connected (Slack optional), **ask the user to connect them** before querying CI.
2. Parse a GitHub PR URL or Dev Portal build URL from `$ARGUMENTS` (current branch PR if empty). From a PR, resolve the build link via PR checks or CI status — do not ask the user for it.
3. If the CI check is queued or running — **poll with `scripts/poll-ci-pr-check.sh`** (45s × 40; `block_until_ms` 2100000). Do not reimplement the loop. Timeout for each target is 15 minutes. CI comments final status in PR comments when the build finishes.
4. If the build failed — logs (`get_failures_from_log` / `tail_log` / `search_log`) + PR diff + `ci-build` patterns. If it looks like **CI standards / CI standards**, use the **-standards** MCP (`get_results` / `describe_rule`). Verdict: change-caused vs standards vs flaky vs timeout vs infra.
5. Do not retrigger, cancel, or start a flakiness build unless the user explicitly asks.

## Catalog pointers

- Skill: [.agents/skills/trace-ci-build/SKILL.md](../skills/trace-ci-build/SKILL.md)
- Poll script: [`scripts/poll-ci-pr-check.sh`](../../scripts/poll-ci-pr-check.sh)
- Known CI/Nx/WASM failures: [.agents/skills/ci-build/SKILL.md](../skills/ci-build/SKILL.md)
- CI standards / CI standards: [.agents/skills/ci-standards/SKILL.md](../skills/ci-standards/SKILL.md)
