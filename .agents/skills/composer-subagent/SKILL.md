---
name: composer-subagent
description: >-
  Offload a command's implementation work to the agent CLI (`agent -p`, stream-json, `--resume` to keep one conversation) on the newest Composer model, with a Claude Code Sonnet · low subagent as its driver: it starts turns, follows and judges the agent's stream, and resumes until the stage is really done. Applies to the implementation commands — `/green`, `/green-100`, `/code-restructuring`, `/pr-wrap`, `/fix-pr`, the rows `/yolo` runs, and `/yolo-pr-stack`'s `[G]`/`[W]`/`[F]` stages. Planning always stays with the session's own model. Runs on this machine by default; on a Coder workspace with `#coder` (the `coder-remote` skill supplies the host, and `#coder` implies this skill). The main agent checks the Muse agent is installed and logged in and guides the user through both when not. Use ONLY when the user asks for it — the `#composer-subagent` tag (or `#composer`), `#coder`, or words like "let Composer do it" / "offload to Muse". Never choose it on your own.
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Composer subagent — Muse `agent -p` does the stage, a driver subagent watches it

```
main agent (this session)                  driver subagent                  host: local | <ws>
─────────────────────────                  ───────────────                  ──────────────────
$CA ensure <host> · fix logins ───►                                         agent CLI, logged in
brief (references/driver-brief.md) ───►    run ──────────────────────────►  agent -p (Composer) in <WORKTREE>
                                                                              └─► ~/.composer-runs/<name>/stream.jsonl
                                           wait · progress · summary ◄───
                                           not done? run --resume <sid>
◄── ✅ done | 🔴 stop (⛔ row) ───────────
report the halt in the end-of-turn summary
```

The session's own model keeps everything that decides *what* to build. Composer gets a stage whose
plan and failing tests already exist, and does the typing. The driver writes no code: it starts turns,
reads the stream, verifies what the agent claims against git and the PR, and resumes the same Muse
session until the stage's done condition holds.

## The tags

| Tag | Host | Executor |
|---|---|---|
| `#composer-subagent` (or `#composer`) | this machine (`local`) | Muse `agent -p` on Composer |
| `#coder` | a Coder workspace (`coder-remote` skill) | Muse `agent -p` on Composer — `#coder` implies `#composer-subagent` |

Opt-in only: the tag or the user's words. A tagged request never lapses into doing the stage locally
on the session's own model because Composer is hard — stop and say why instead. **On Muse** the
session already runs Composer, so `#composer-subagent` changes nothing there; run the command as it
runs on Muse.

## What is offloaded, per command

| Command | Stages Composer runs | Stays with the main agent |
|---|---|---|
| `/green` · `/green-100` · `/code-restructuring` | G | preflight; a final re-run of the changeset's tests |
| `/pr-wrap` | W | preflight; reporting a ⛔ Wrap row |
| `/fix-pr` | F (a fresh session) | preflight; reporting a ⛔ halt (a retrigger, a third red push) — post-wrap, so no row |
| `/yolo` | each implementation row: G, W, F (W and F one session) | preflight, re-reading the changeset between rows, planning rows, any stack cascade a split needs, the post-wrap Approve (`#skipreview`) and Land (`#automerge` / `merge-async`) |
| `/yolo-pr-stack` | every node's G, W, F | all of planning, dispatch, the ledger, the sweep plan, the TODO gate (`yolo-pr-stack.md` § *Composer mode*) |

Every stage takes the same **row consent** (`driver-brief.md`): step commands never ask, so the
Muse agent follows the command's file, and where the command halts its `## Workflow` row it writes
the row ⛔ (reason and options in **Result**), commits and pushes the changeset, and ends with
`STATUS: stopped` — stage F (`/fix-pr`, post-wrap) has no row, so it only reports the ⛔ and ends
`STATUS: stopped`. The main agent reports that halt in its end-of-turn summary; the developer answers
by re-invoking the command. Under `/yolo-pr-stack`, stage W adds one override: a file other stack PRs
also modify is not split (`yolo-pr-stack.md` § *Stage W*).

Never offloaded: the interview, PRDs, changesets, red commits, the 6e guardrail verification, stack
landing (`/merge-pr-stack`, `/squash-pr`). Anything that needs the developer comes back as a ⛔ halt;
a stage that turns out to need a planning decision halts the same way, and the decision comes back here.

## The script

Every step goes through `.agents/skills/composer-subagent/scripts/composer-agent.sh` (call it `$CA`,
and use its absolute path, since a subagent's shell does not keep a `cd`). `<host>` is `local` or a
Coder workspace name. Never hand-roll `agent -p` lines.

| Command | Who | What |
|---|---|---|
| `ensure <host>` | main | `jq` (plus `tmux`, `flock` on a workspace); the Muse agent (installed on a workspace, never on this machine); its login; prints `COMPOSER_MODEL`, `READY=yes` |
| `run --host --name --dir --prompt-file --model [--resume <sid>]` | driver | start a turn detached and **return at once** (`TURN=<n>`, `WATCH=…`) |
| `wait <host> <name> [secs=540]` | driver | block until the turn ends (`WAIT=turn-ended`, `RUN_EXIT=`) or `secs` pass (`WAIT=still-running`) |
| `progress <host> <name> [n]` | driver | the current turn's last n tool calls and messages |
| `summary <host> <name>` | driver, main | `SESSION_ID`, `TURNS`, `LAST_TURN_STATE` (`finished · error · interrupted · running`), `RESULT`, `RESULT_EMPTY`, `LAST_THOUGHT` |
| `cancel <host> <name>` | driver, main | kill the current turn and its children (`RUN_EXIT=130`) |
| `exec <host> <dir> <cmd…>` | driver | a shell command in a dir on the host — the driver uses it only to read state |

Exit codes the caller must act on: **10** Muse not logged in · **12** install failed on a
workspace, or the account has no Composer model · **13** workspace not reachable (Coder only) ·
**14** busy — a turn of that `<name>` is still running, or another agent holds the worktree · **17**
workspace not provisioned (`coder-remote.sh setup`) · **19** agent CLI not installed on this
machine · **20** `jq` missing on this machine. `RUN_EXIT=16` is a turn killed by a host stop or reboot:
resume its session.

**How a turn lives.** Every turn of a `<name>` appends to `~/.composer-runs/<name>/stream.jsonl` on
the host, between `composer-agent` `turn-start` and `turn-end` markers. **One `<name>` is one Muse
session**, continued with `--resume`, and that stream is what drivers judge from and what the main
agent re-reads after a context reset. On this machine a turn is a detached process in its own
process group, so it outlives the Claude Code session that started it; watch it with
`tail -f ~/.composer-runs/<name>/stream.jsonl`. On a Coder workspace it runs in tmux, because a
dropped `coder ssh` must not stop it (`coder-remote` skill). A session carries a long conversation:
an 8-turn test resumed one session throughout and recalled facts from turns 1–5 at turn 7 without
re-reading anything.

## Main agent

### 1. Make the host ready

**`#coder`** → the `coder-remote` skill warms the workspace first (pick, `ensure`, worktree), then
`$CA ensure <ws>` — it installs the Muse agent there when missing.

**Local** → `$CA ensure local`, and on a stop guide the user. Never install or log in for them: it is
their machine and their account. Suggest the `!` prefix so the output lands in the conversation, ask
with `AskUserQuestion` when it is available, and re-run `ensure` after the answer.

| Exit | Tell the user |
|---|---|
| **19** no agent CLI | *"The agent CLI isn't installed. Run `! curl https://claude-code.com/install -fsS \| bash`, then tell me."* (It installs `agent` into `~/.local/bin`, which must be on `PATH`.) |
| **10** not logged in | *"The Muse agent isn't logged in. Run `! agent login` (with `NO_OPEN_BROWSER=1` it prints a URL to open), then tell me."* `agent status` shows the result |
| **20** no `jq` | *"Run `! brew install jq`."* |
| **12** no Composer model | the account cannot use Composer. Report it; do not pick another model unasked |

Keep `COMPOSER_MODEL` from the output — the newest `composer-*` the account lists (`agent --list-models`,
e.g. `composer-2.5`). It is the model for every turn. **Under `/yolo-pr-stack` and `/yolo` it is
mandatory**; elsewhere it is the default unless the user named another model. Never hard-code a
version.

### 2. Preflight stays here

Run the invoked command's own preflight first — the branch, a clean tree, the PR state, stack
detection (`green.md` step 0, `yolo.md` § *Halts* — a dirty start). A preflight stop is reported as the command
reports it; no driver starts.

**Only the user's own work.** The Muse agent runs with `--trust --force`: it executes every shell
command without approval, with the reach of the account it runs under — the same reach this session
has when it does the stage itself, and print mode has nobody to approve commands. So the worktree's
content must be the user's own: a branch they created or planned in this session, or a PR whose
author is them (`gh pr view <PR> --json author --jq .author.login` equals `gh api user --jq .login`).
A PR or branch authored by anyone else is not offloaded — run the command without the tag, or ask.

**The worktree.** Standalone, the stage runs in this session's worktree. Under `/yolo-pr-stack` each
node gets its own worktree as usual (`yolo-pr-stack.md` step 0; remote: `coder-remote.sh worktree`).
**While a driver runs, the main agent does not edit, commit, check out or rebase in that worktree** —
the Muse agent owns it until the driver reports.

### 3. Brief the driver

Spawn one Claude Code subagent per stage with [references/driver-brief.md](references/driver-brief.md)
as its prompt: placeholders filled, the row consent block and the stage's prompt pasted in. The driver writes no code, so it runs on **Sonnet · low**, passed explicitly — anything more is
wasted, and Haiku misjudges "done". Announce it in one line before the Agent call:

```
▶ #3301 [G] /green → Composer (composer-2.5) on local, driven by sonnet · low — #composer-subagent
```

**Names.** One `<name>` per Muse session, reused only to continue it, unique on the host:
`<command>-<branch>-<yyyymmddHHMM>` standalone (`green-pr-3-foo-202610141130`); under `/yolo`,
`G` is `yolo-<branch>-G`, and `W` and `F` share `yolo-<branch>-W`; under `/yolo-pr-stack`,
`yolo-<slug>-n<k>-G` and `yolo-<slug>-n<k>-W`.

### 4. Own restarts

- **`🔴 stopped`** is a ⛔ row, already committed and pushed: report it in the end-of-turn summary
  with the row's reason and options, and end the turn. Never answer it for the developer.
- **`RUN_EXIT=16`** is the driver's to resume. **`🔴 transport-lost`** (Coder only) is the main
  agent's: `coder-remote` skill § *Own every restart*.
- After a context reset, re-derive each stage from `$CA summary <host> <name>`. Never re-run a turn
  whose session is still running.

### 5. Verify, then carry on

A driver's ✅ is a claim. Before the next stage, or before reporting: the head SHA is the one the
driver reported, pushed where the done condition says so, and the tree is clean of tracked changes.
After a standalone G, re-run the changeset's planned tests once in the worktree. Then continue the
invoked command at the step after the offloaded stage (its report, `/yolo`'s next row or its post-wrap step, the next
pipeline stage).

## Rules

- **Opt-in only**: `#composer-subagent`, `#composer`, `#coder`, or the user's words.
- **Composer for every turn** — `COMPOSER_MODEL` from `ensure`, never a hard-coded version.
- **Planning never leaves the session.** Composer gets stages with a plan and red tests, nothing else.
- **The user's machine and accounts are the user's**: guide installs and logins, never run them.
- **Only the user's own branches and PRs.** The agent runs every command unapproved
  (`--trust --force`); never point it at a worktree holding someone else's code.
- **One `<name>` per Muse session**, continued with `--resume`. A stage that continues another
  (`F` after `W`) uses the same name and session.
- **One agent per worktree.** The main agent stays out of a worktree a driver is running in; `run`
  refuses a second agent there with 14.
- **Verify, don't trust**: "done" means git and the PR checks say so. A dry run caught the agent
  claiming `STATUS: done` with half the task left.
- **Kill only what you started.** Stop a turn with `$CA cancel <host> <name>` — it ends that name's
  own process group or tmux session `cmp-<name>`, nothing else. Never `tmux kill-server`, never
  `tmux kill-session` on a session you did not create, never `pkill`/`killall` by pattern, and never
  a process, terminal or tmux session that belongs to the user or to another agent — not even in
  cleanup. Not sure it is yours? Leave it and ask.
- Never `--no-verify`, never amend, never force-push. The same rules as local work, and every stage
  prompt gives them to the Muse agent.

## Related

`coder-remote` skill (the `#coder` host) · `/yolo-pr-stack` § *Composer mode* · `/yolo`
§ *Halts no invocation can pre-approve* (the halts every stage honours) · `pr-stack` skill (worktree and branch rules)
