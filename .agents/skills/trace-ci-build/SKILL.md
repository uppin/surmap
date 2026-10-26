---
name: trace-ci-build
description: Trace a  CI build from a GitHub PR URL or a the CI host Dev Portal build URL. Connects Developer Portal, GitHub, and -standards MCPs if needed (Slack optional), then polls the build while diagnosing each failure the moment it surfaces — failures are readable mid-build, so it does not wait for the run to finish — pulls logs, maps them to the PR diff, and judges flake vs real breakage (including CI standards / CI standards and the 15-minute per-target timeout). Fixes are written to the working tree during the run and committed only AFTER the build completes, because pushing mid-build abandons the in-flight run and loses every failure that had not yet surfaced. Use when the user invokes /trace-ci-build, pastes a github.com/.../pull/N or the CI host/dev/repo/.../build/<uuid> link, asks why CI/CI failed, or wants to watch PR build status.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, Agent
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Trace CI Build

Peer of `trace-request`. That skill reconstructs a live request from a Request ID. **This skill traces a CI build** — poll while it is running, diagnosing each failure as it surfaces rather than waiting for the run to end, and explain *why* from logs + the PR diff, including whether the target looks flaky.

**The loop in one line:** poll → a failure appears → diagnose and fix it in the working tree → keep polling → the build completes → commit every fix in one go and push once.

Always read [`.agents/skills/ci-build/SKILL.md`](../ci-build/SKILL.md) before interpreting a failure in this monorepo. That skill is the catalog of known CI/Nx/WASM failure patterns here.

## Invocation

```
/trace-ci-build [prUrl | buildUrl] [question]
```

Users almost always paste one of these:

| What they paste | Example |
|---|---|
| **GitHub PR** | `<service-url>` |
| **Dev Portal build** | `<service-url>` |

The build URL's last path segment is the Developer Portal `buildId` (UUID). CI **uses TeamCity to run the builds**; the Dev Portal page is the CI/Developer Portal view over that TeamCity run.

The Dev Portal build link is resolvable from **GitHub PR checks** or from **CI build status** (CI PR comments). If the user only gives a PR, pull the build URL from checks / CI status — do not ask them to go find it.

`$ARGUMENTS` is optional. Also accepted: a bare PR number, a bare UUID, a TeamCity `ci.dev.<service-host>` URL, or no args (current branch's PR).

```
/trace-ci-build <service-url>
/trace-ci-build <service-url> why did wasm fail?
```

If no question is given, default to "report CI status; if failed, explain why."

This repo builds on **CI** (TeamCity underneath), not Bazel/Buildkite. Prefer `buildSystem: "CI"` when a tool asks.

---

## Phase 0 — Parse the invocation

Extract `SELECTOR` (first URL or token) and `QUESTION` (the rest). A PR/build URL may be buried in prose — take the first matching URL.

```bash
ARGS="$ARGUMENTS"
PR_URL="$(printf '%s\n' "$ARGS" | grep -Eo 'https://github.com/[^/]+/[^/]+/pull/[0-9]+' | head -1)"
BUILD_URL="$(printf '%s\n' "$ARGS" | grep -Eo '<service-url>' | head -1)"
TC_URL="$(printf '%s\n' "$ARGS" | grep -Eo '<service-url> ]*' | head -1)"
BUILD_ID="$(printf '%s\n' "$BUILD_URL" | grep -Eo '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' | tail -1)"
# owner/repo/n from PR_URL: github.com/<owner>/<repo>/pull/<n>
# org/repo from BUILD_URL: the CI host/dev/repo/<org>/<repo>/build/<uuid>
```

If `$ARGUMENTS` is empty, resolve the current branch's PR with `gh pr view`.

| Input | Use as |
|---|---|
| `https://github.com/<owner>/<repo>/pull/<n>` | `owner`, `repo`, `prNumber` — then resolve the Dev Portal **build link** from PR checks or CI status (Phase 2) |
| `<service-url>` | Developer Portal `buildId` = `<uuid>`; `org/repo` from the path. Call `devex__get_build` directly |
| bare UUID | Developer Portal `buildId` |
| `<service-url>` | `teamCityUrl` (TeamCity run CI used). Prefer the Dev Portal UUID when both exist |
| empty / current branch | `owner/repo` + `prNumber` from `gh pr view`, then same as a PR URL |
| integer only | `prNumber` on origin's `owner/repo` |

State `owner/repo`, `prNumber`, `buildId` / build URL, and the question before querying.

This repo's origin is usually `-private/<name>`. Short repo name (e.g. `this repo`) is what Developer Portal `repoName` accepts.

---

## Phase 1 — MCP gate (do this before any CI query)

Required MCPs:

| MCP | URL | Why |
|---|---|---|
| **Developer Portal** | `<service-url>` | CI builds, logs, failures, flakiness |
| **GitHub** | `<service-url>` | PR identity, files, CI's **PR comments** (final status) |
| **-standards** | `<service-url>` | CI standards / CI standards — enforced rule failures that break CI |

Optional:

| MCP | URL | Why |
|---|---|---|
| **Slack** | `<service-url>` | CI/CI channel notifications when the PR comment is missing or the user points at Slack |

### Muse / Claude (native MCP)

1. Discover servers (`GetMcpTools` with pattern `developer-portal|github|-standards|slack`, or the IDE MCP list).
2. Server ids vary (`developer-portal` vs `user-developer-portal`). Match on the slug, case-insensitive.
3. If a required server is **missing**, **error**, or not in the user's MCP config — **stop and ask the user to connect it**. Do not improvise around a disconnected Developer Portal/GitHub/-standards.
4. If status is **`needsAuth`**, authenticate that server (`mcp_auth`) and re-inspect. Do not call `mcp_auth` just because the server is listed.
5. Only continue the native-MCP path once Developer Portal, GitHub, and -standards are `ready`.

Ask in one message, naming the missing servers and the URLs above. Slack is optional unless the user is debugging from a Slack thread.

### Codex / fallback (`@mcp-s/cli`)

If the user says to proceed without native MCP, or native MCP cannot be connected, use the same gateway as `trace-request`:

```bash
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 check-auth
```

Exit 0 = good. Exit 4 = run `login` (browser). Then call `devex__<tool>` / `github__<tool>` / `-standards__<tool>`.

Do not mix "native MCP is down" with "the build is missing". If tools cannot run, say so and stop.

---

## Phase 2 — Identify the CI build

CI uses **TeamCity** to run the builds. The Dev Portal URL
`<service-url>` is the CI/Developer Portal handle
for that TeamCity run. Prefer that UUID as `buildId` on every Developer Portal log tool.

**If the user gave a build URL** — skip search. `devex__get_build` with that UUID.
The PR number (if present on the build record) still unlocks GitHub comments and the diff.

**If the user gave a PR URL** — resolve the matching Dev Portal **build link** from:

1. **GitHub PR checks** (`statusCheckRollup` / `gh pr checks`) — details URLs are often `the CI host/dev/repo/.../build/<uuid>` or a TeamCity `ci.dev.<service-host>` log URL.
2. **CI build status** — CI comments on the PR (in-progress and **final** when the build finishes). Those comments carry the build link.

Do not ask the user for a build URL when a PR is enough to resolve it.

**2a. GitHub PR (checks + CI comments).** CI comments final status in PR comments when the build finishes. Read those comments every time — they are the human-facing terminal signal.

Native: `github__get_pull_request`, `github__get_pr_conversation_comments`, `github__list_commits`.

CLI fallback:

```bash
gh pr view <n> --json number,url,title,headRefOid,statusCheckRollup,commits
gh pr checks <n>
gh api repos/<owner>/<repo>/issues/<n>/comments --jq '.[] | {user: .user.login, created: .created_at, body: .body[0:800]}'
```

From checks and comments, extract:

- `<service-url>` → Developer Portal `buildId`
- `<service-url>` → `teamCityUrl` (same run; CI's TeamCity backend)

An in-progress CI comment is not final; wait for the completion comment.

**2b. Developer Portal build record.** If you already have the UUID, `devex__get_build`. Otherwise schema first, then search:

```bash
# schema (once per session)
npx -y --registry "<service-url>" @mcp-s/cli@0.0.21 \
  call devex__get_devex_fqdn '{"fqdn":".developer-portal.v1.build_data"}'
```

Then `devex__search_builds` with camelCase WQL. Typical CI PR filter:

```json
{
  "search": {
    "filter": {
      "repository": { "$contains": "<repo>" },
      "pullRequestNumber": { "$eq": <n> },
      "buildSystem": { "$eq": "CI" }
    },
    "sort": [{ "fieldName": "buildStartDate", "order": "DESC" }],
    "cursorPaging": { "limit": 5 }
  }
}
```

If you only have a TeamCity URL, pass `teamCityUrl` to the log tools — do **not** treat a TeamCity numeric id as a Developer Portal UUID. The Dev Portal UUID and the TeamCity numeric `buildId=` are different identifiers.

Capture: internal `buildId` (UUID), Dev Portal URL, TeamCity URL, result/status, commit, start/end, failed task names if present.

---

## Phase 3 — Branch on status

| State | What to do |
|---|---|
| **Queued / running / no terminal PR comment** | **Poll _and_ probe for failures as they surface** (Phase 3a) — do not wait for the build to finish before diagnosing. Do not treat missing logs as a failure. |
| **Success** (Developer Portal + CI PR comment agree) | Report green. Note duration. Stop unless the question asks for more. |
| **Cancelled** | Report who/what cancelled (`devex__cancel_build` is user-triggered only — do not call it). Stop. |
| **Failed** (or CI PR comment says failed) | **Troubleshoot** (Phase 4). |

If GitHub checks are still pending but CI already commented success/failure, trust the CI comment and the Developer Portal record.

### 3a. Poll — and diagnose each failure the moment it surfaces

**Do not wait for the build to finish before looking at failures.** A CI run here takes ~25–30
minutes, and `devex__get_failures_from_log` returns real data on a **running** build: the failing
`packageId`, the `taskName`, a `fullLogUrl`, and log hints with the actual assertion. Waiting for the
terminal check throws away most of that window.

Two facts drive the loop:

1. **Failures are readable mid-build.** `get_failures_from_log`, `tail_log` and `search_log` all accept
   the in-flight `buildId`.
2. **An empty result mid-build is not success.** It means *nothing has failed yet*. Failures accumulate
   as targets finish, and `tcTestFailures` / `tcBuildProblems` usually stay empty until TeamCity
   resolves the build. Never report green from a mid-build probe.

**The loop**

Run the repo script for the check itself — do **not** reimplement it. It is the proven `gh pr checks`
watch (TSV `CI<TAB>pass|fail|pending`):

```bash
scripts/poll-ci-pr-check.sh <pr-number-or-url> --repo <owner/repo>
```

Run it **in the background** so you can probe while it waits, then:

1. **Probe** `devex__get_failures_from_log` (with the in-flight `buildId`) every couple of minutes.
2. Keep a set of failures already seen, keyed on `(packageId, taskName)`, so the same one is not
   re-diagnosed on every probe.
3. **On each new failure, run Phase 4 for that target immediately** — read `ci-build`, pull the
   log, map it against the PR diff, and judge change-caused vs flake vs timeout.
4. **Fix it now if it is change-caused** — edit the working tree, but **do not commit** (see 3b).
5. **Keep polling.** More targets can still fail, and each one is another fix you can be writing
   instead of waiting.
6. When the check turns terminal, you already hold the full failure set.

- 45s interval, 40 attempts (~30 min). Override with `POLL_SLEEP` / `POLL_ATTEMPTS` if the user asks to
  keep waiting.
- Tell the user you are polling, and report each failure as you find it rather than saving them all for
  the end.
- **block_until_ms** must cover the full wait: **2100000** (35 min), or run in the background. Do not
  kill it at 30s.
- Exit **0** = CI `pass` → summarize and stop (unless the question asks for more).
- Exit **1** = CI `fail` → finish Phase 4 for anything not yet diagnosed.
- Exit **2** = still pending → show the last line, ask whether to keep waiting.

**Fix what is yours; do not silently patch someone else's package.** A failure in a package the PR does
not touch (flake, per-target timeout, infra, a red baseline) is **not** yours to "fix right away" —
record it, keep polling, and surface it in the answer. Patching another team's package to make your PR
go green hides a real breakage and puts an unreviewed change in your diff. Fix it only when the user
asks, or when it is plainly a repo-wide break that blocks everyone.

**Timeout for each target is 15 minutes.** The GitHub CI check stays `pending` until the whole
TeamCity build finishes, not per target — which is exactly why probing beats waiting.

If you only have a Dev Portal UUID and no PR, you cannot use the script — poll `devex__get_build` and
probe `get_failures_from_log` on the same UUID. Prefer resolving the PR first.

After a terminal GitHub result, CI comments final status on the PR. Read that comment (and the Dev
Portal build URL from the check details) before declaring done.

Do **not** call `devex__retry_buildkite_build_step`, `devex__trigger_pr_build`, `devex__cancel_build`,
or `devex__trigger_flakiness_build` unless the user explicitly asks.

### 3b. Commit the fixes only AFTER the build has completed — MANDATORY

Write fixes into the working tree while the build runs. **Do not commit, and above all do not push,
until the build reaches a terminal state.**

Pushing moves the PR head, which **starts a new CI build and abandons the one in flight**. Every
failure that had not yet surfaced is lost with it, so failure #2 is only discovered on the next run —
turning one ~30-minute build into a chain of them, one per failure. It also invalidates the trace: the
build you were reading tested a commit that is no longer the head.

The order is therefore:

```
poll ──▶ failure appears ──▶ diagnose ──▶ fix in the WORKING TREE (uncommitted)
  ▲                                                    │
  └───────────────── keep polling ◀────────────────────┘
                            │
                   build reaches terminal state
                            │
                   commit ALL fixes together ──▶ push once ──▶ one new build validates them all
```

Rules:

- **One commit after completion**, covering every fix from the run — not a commit per failure.
- **Never `git push` mid-build.** Also avoid rebasing, checking out another branch, or stashing while a
  build you are tracing is running: keep the tree stable so the fixes stay attributable to that run.
- If a fix cannot wait (the build is long and someone is blocked), say so and let the user decide to
  push early — that is their call, and it costs the rest of the run's signal.
- If nothing was change-caused, there is nothing to commit. Report the unrelated failures instead.

---

## Phase 4 — Troubleshoot a failed build

Read **`ci-build`** first, then pull evidence in this order.

**4a. Structured failures**

`devex__get_failures_from_log` with `buildSystem: "CI"` and exactly one identifier (`buildId` **or** `repoName`+`prNumber` **or** `teamCityUrl`).

CI payload to use:

- `errorMessages` — summary
- `userFailures` / `systemFailures` — task + `fullLogUrl` + hints
- `violations` — pre-build validation (not a compile/test failure)
- `tcTestFailures` — tests; `flaky: true` is TeamCity's flake flag
- `tcBuildProblems` — build-level problems

**4a-std. CI standards / CI standards**

Enforced Standards rules break the CI build. Treat the failure as Standards-related when logs, CI comments, or task names mention **CI standards**, **CI standards**, `ci-police`, `-standards`, or a rule id (e.g. `no-http-client-below-2`).

Then use **-standards** (do not guess from logs alone):

- `-standards__get_results` with `projectName` **or** `artifactId` (never both) — current breaking / future / passing rules for that package
- `-standards__get_project_report` — same report for one project by name
- `-standards__describe_rule` — remediation for a specific `ruleName`
- `-standards__query_violations` — concrete violation messages behind one rule

Read [`.agents/skills/ci-standards/SKILL.md`](../ci-standards/SKILL.md) for preset/local-check details if the user wants to reproduce locally. For *this* CI run, station results (`get_results`) are the source of truth — a local `ci-police check` validates the working tree, not the build that already failed.

Do **not** call write tools (`add_optouts`, `remove_optouts`, `handle_optout_application_items`, `trigger_bug_fix`, `add_optout_applications`) unless the user explicitly asks.

**4b. Logs**

- `devex__tail_log` — last N lines of the failed task
- `devex__search_log` — regex for the distinctive error, `ENOENT`, `error TS`, wasm-pack, rustc, `killed`, `timeout`

Persist large logs to a file and parse; do not dump them into the reply.

**4c. Code changes that could have caused it**

```bash
gh pr diff <n> --name-only
git log --oneline origin/<base>..HEAD
```

Map each failed CI/Nx target to packages and scripts (task name → `packages/<pkg>/package.json` / `nx` target). A failure is **change-caused** when the error site overlaps the PR diff (or a generated file the diff's codegen/build graph produces).

Then match the error text against `ci-build` sections — especially:

- §1 codegen vs WASM order
- §2–4 rustup / cargo races
- §8 Yarn skipping `pre*`/`post*` hooks
- §9 Nx cache hits masking a structural break (one target fails, others `[local cache]`)
- §11 concurrent duplicate `do:build` across CI package jobs

**4d. Flake vs real vs timeout**

Decide explicitly. Signals:

| Likely | When |
|---|---|
| **Timeout** | Task ran ~**15 minutes** then died with no real compiler/test assertion (killed, inactivity, CI timeout). Timeout for each target is 15 minutes. |
| **Flaky target** | `tcTestFailures[].flaky === true`; or the same task fails with a known race from `ci-build` **and** the PR diff does not touch that package; or infra/`systemFailures` only. |
| **Real breakage** | Deterministic compiler/test error in code the PR changed (or in a generator/graph the PR changed). |
| **CI standards** | Enforced CI standards rule (`severity: ERROR`) on a package the PR touched, confirmed via `get_results` / `describe_rule`. Not a flake. |
| **Masked structural** | One WASM/Nx target fails, siblings are cache hits (`ci-build` §9) — not a one-off flake. |

Offer `devex__trigger_flakiness_build` **only** if the user wants a CI flakiness run. Never trigger it automatically.

**4e. Experimental assistant (optional)**

`devex__why_pr_build_failed_exp` can add a second opinion. Treat it as a hint; **logs + diff + `ci-build` are the source of truth**.

---

## Phase 5 — Answer

Lead with the outcome, then evidence:

```markdown
## CI Trace — <owner>/<repo>#<pr>
**Build:** <uuid / CI URL> · **Commit:** <sha>
**Status:** running | success | failed | cancelled | timed out
**Question:** <question>

### Answer
<1–3 sentences. If failed: real vs flake vs timeout, and the file/target that broke.>

### Targets
| Target / task | Duration | Result | Change-caused? | Note |
|---|---|---|---|---|
| … | … | … | yes / no (unrelated package) | 15 min timeout if relevant |

### Fixes
| Failure | Fixed in this run? | Where |
|---|---|---|
| `<package>` `<task>` | yes — staged in the working tree | `path/to/file` |
| `<package>` `<task>` | no — unrelated package, not ours to patch | — |

Committed after the build completed: yes / no (nothing was change-caused).

### Evidence
- CI PR comment: <quote or "not posted yet">
- Failure: `<error>` → `packages/…` (log)
- Diff overlap: <files> or none
- `ci-build` match: §N or none
- CI standards: `<ruleName>` (`describe_rule`) or none

### Verdict
change-caused | -standards | flaky target | per-target timeout | infra | unknown

### Next
<one concrete next step: fix X, keep polling, or (only if asked) retrigger / flakiness build>
```

---

## Notes

- **Poll and forensics run together, not in sequence.** Failures are readable on a *running* build via
  `get_failures_from_log`, so diagnose each one as it surfaces instead of waiting ~30 minutes for the
  terminal check. An empty mid-build probe means "nothing failed yet", never "green".
- **Commit fixes only after the build completes**, then push once. A mid-build push starts a new build,
  abandons the in-flight one, and loses every failure that had not yet surfaced — turning one run into a
  chain of runs, one per failure.
- **Fix what the PR caused; do not patch unrelated packages** to force a green. Record those and report
  them.
- **Usual inputs are a GitHub PR URL or a Dev Portal build URL** (`the CI host/dev/repo/<org>/<repo>/build/<uuid>`). The build link is resolvable from PR checks or CI build status.
- **Poll CI GitHub status with `scripts/poll-ci-pr-check.sh`**, not a hand-rolled sleep loop.
- **CI uses TeamCity to run the builds.** Dev Portal UUID = Developer Portal `buildId`. TeamCity numeric id ≠ that UUID.
- **CI comments final status in PR comments when the build finishes.** Wait for that comment (or a terminal Developer Portal result) before declaring done.
- **Timeout for each target is 15 minutes.** Do not confuse a 15-minute kill with a flaky test.
- **Do not trigger, cancel, or retrigger CI** unless the user explicitly asks.
- **Do not skip `ci-build`** for WASM/Nx failures in this repo — cache-masked and concurrent-build races look like flakes and are not.
- Native MCP names vary; use discovery. `@mcp-s/cli` tool names are `devex__…`, `github__…`, and `-standards__…`.
- **CI standards failures** go through the **-standards** MCP (`get_results` / `describe_rule`), not CI log archaeology alone. Enforced rules break the build; they are not flakes.
