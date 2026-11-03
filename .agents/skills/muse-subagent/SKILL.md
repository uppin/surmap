---
name: muse-subagent
description: >-
  `#muse` — offload a command's implementation stages to Muse Code run headless (`muse exec --json`, one session continued across turns by `--session-id`), with a Claude Code Sonnet · low subagent as its driver: it starts turns, follows and judges the JSONL stream, and resumes the same Muse session until the stage is really done. Built for `/yolo-pr-stack` (every node's `[G]`/`[W]`/`[F]`), and applies equally to `/green`, `/green-100`, `/code-restructuring`, `/pr-wrap`, `/fix-pr` and the rows `/yolo` runs. Planning stays with the session's own model. Runs on this machine only. Uses composer-subagent's driver brief and stage prompts unchanged — only the script and the model differ. Use ONLY when the user asks for it — the `#muse` tag, or words like "let Muse do it" / "offload to Muse Code". Never choose it on your own.
---

# Muse subagent — `muse exec` does the stage, a driver subagent watches it

```
main agent (this session)                  driver subagent                  this machine
─────────────────────────                  ───────────────                  ────────────
$MA ensure local · guide login ───►                                         muse, logged in
brief (composer-subagent
  references/driver-brief.md) ───►         run ──────────────────────────►  muse exec --json --yolo
                                                                              --session-id <uuid> in <WORKTREE>
                                                                              └─► ~/.muse-runs/<name>/stream.jsonl
                                           wait · progress · summary ◄───
                                           not done? run --resume <sid>
◄── ✅ done | 🔴 stop (⛔ row) ───────────
report the halt in the end-of-turn summary
```

`#muse` is the [`composer-subagent`](../composer-subagent/SKILL.md) flow with a different
executor. Everything that skill says about **what is offloaded**, **preflight**, **only the user's
own work**, **one agent per worktree**, **owning restarts**, **verify, don't trust** and **kill only
what you started** applies here word for word. Read it first; this file lists only what differs.

## What differs from `#composer`

| | `#composer` | `#muse` |
|---|---|---|
| Executor | `agent -p --output-format stream-json --trust --force` | `muse exec --json --yolo` (no approval, no sandbox, workspace trusted, no `request_user_input`) |
| Script (`$CA` in the brief) | `composer-subagent/scripts/composer-agent.sh` | **`muse-subagent/scripts/muse-agent.sh`** — same commands, same `KEY=VALUE` output, same exit codes |
| Host | `local`, or a Coder workspace with `#coder` | **`local` only**; `#muse` and `#coder` do not combine (`run --host <ws>` exits 2) |
| Model | `COMPOSER_MODEL` from `ensure`, mandatory | `MUSE_MODEL` from `ensure` (the account's default), or a model the user named; `--model` is optional |
| Effort | none | `--effort <minimal…ultra>` → `--reasoning-effort`. Under `/yolo-pr-stack`, from the node's complexity score (§ *Muse mode* there); standalone **medium**, unless the user named one |
| Session | `--resume <sid>` | the script mints a UUID on a name's first turn and passes it back as `--session-id` on every `--resume` — verified to continue the same conversation |
| Stream | `~/.composer-runs/<name>/stream.jsonl` | `~/.muse-runs/<name>/stream.jsonl`; Muse diagnostics go to `stderr-<n>.log` beside it |

`#muse` and `#composer-subagent` are alternatives: one executor per run. If both are given, stop
and ask which one (or, under `#yolo`, record a deferred answer and take `#muse`, the more specific
request).

## The script

`.agents/skills/muse-subagent/scripts/muse-agent.sh` (call it `$MA`; use its absolute path — a
subagent's shell does not keep a `cd`). Never hand-roll `muse exec` lines.

| Command | Who | What |
|---|---|---|
| `ensure local` | main | `muse`, `jq`, `uuidgen` on PATH; one cheap probe turn proves the login (Muse Code has no status command); prints `MUSE_VERSION`, `MUSE_MODEL`, `READY=yes` |
| `run --host local --name --dir --prompt-file [--model] [--effort] [--resume <sid>]` | driver | start a turn detached and **return at once** (`TURN=`, `SESSION_ID=`, `WATCH=`) |
| `wait local <name> [secs=540]` | driver | block until the turn ends (`WAIT=turn-ended`, `RUN_EXIT=`) or `secs` pass (`WAIT=still-running`) |
| `progress local <name> [n]` | driver | the current turn's last n tool calls (command, exit code) and its final message |
| `summary local <name>` | driver, main | `SESSION_ID`, `TURNS`, `LAST_TURN_STATE` (`finished · error · interrupted · running`), `LAST_TURN_TERMINAL`, `RESULT`, `RESULT_EMPTY`, `STDERR` when a turn did not finish |
| `cancel local <name>` | driver, main | TERM the turn's process group, KILL after 10 s (`RUN_EXIT=130`) |
| `exec local <dir> <cmd…>` | driver | a shell command in a dir — the driver uses it only to read state |

Exit codes: **2** usage (including a non-local host, or a `--resume` that is not the name's
session) · **10** the probe turn did not complete — not logged in · **14** busy: a turn of that name
is running, or another agent (Muse or Composer — they share the worktree lock) holds the worktree ·
**19** `muse` not on PATH · **20** `jq`/`uuidgen` missing. `RUN_EXIT=16` is a turn killed by a machine
stop or reboot: resume its session.

**The wire format** the script reads (Muse Code 1.4.x, `muse exec --json`): one JSON record per
line with a `payload_type`. The turn's final message is the `run.terminal.<state>` record's
`.payload.text` (`.payload.terminal` is `completed` on success; anything else is `error`); tool
calls are `tool.result` records whose `.payload.text` is a JSON object with `command` and
`exit_code`; `run.model.configured` names the model. The script wraps each turn in
`{"type":"muse-agent","event":"turn-start|turn-end"}` markers. If a Muse upgrade changes these,
fix the script, not the driver.

## Main agent

1. **Make the host ready.** `$MA ensure local`. Never install or log in for the user:

   | Exit | Tell the user |
   |---|---|
   | **19** | *"Muse Code isn't installed (`muse` is not on PATH). Install it, then tell me."* |
   | **10** | *"Muse Code isn't logged in. Run `! muse login` (or set `META_API_KEY`), then tell me."* |
   | **20** | *"Run `! brew install jq`."* |

   Keep `MUSE_MODEL` for the announcement line and the ledger.
2. **Preflight, worktree, ownership** — exactly as `composer-subagent` § *Main agent* 2.
3. **Brief the driver** with [`composer-subagent/references/driver-brief.md`](../composer-subagent/references/driver-brief.md),
   placeholders filled, and these substitutions stated at the top of the brief:
   - `CA` = the absolute path of **`muse-agent.sh`**; `<host>` = `local`; "Muse agent" = Muse Code;
   - `--model <COMPOSER_MODEL>` → `--model <MUSE_MODEL> --effort <effort>`;
   - prompt files go in `<scratchpad>/muse/`;
   - ignore exit 13 and `🔴 transport-lost` (no remote host); there is no `LAST_THOUGHT` — a
     `RESULT_EMPTY=yes` turn is resumed with the brief's *"ended without a final message"* prompt.

   The row consent block, the stage prompts and their done conditions are pasted in unchanged.
   The driver runs on **Sonnet · low**, passed explicitly. Announce it in one line:

   ```
   ▶ n3 #3301 [G] /green → Muse Code (muse-wonder-1.0 · medium) on local, driven by sonnet · low — #muse
   ```

   **Names** follow `composer-subagent` § *Names* (`yolo-<slug>-n<k>-G`, `yolo-<slug>-n<k>-W`, …);
   a name is one Muse session and is never reused for another.
4. **Own restarts, verify, carry on** — `composer-subagent` § *Main agent* 4–5. After a context reset,
   `$MA summary local <name>` re-derives a stage's state.

## Rules

- **Opt-in only**: `#muse`, or the user's words. Never chosen on the agent's own initiative.
- **Planning never leaves the session.** Muse Code gets stages with a plan and red tests, nothing else.
- **Only the user's own branches and PRs** — `--yolo` runs every command unapproved and unsandboxed.
- **One name per Muse session**; `F` continues `W`'s name and session.
- **Kill only what you started**: `$MA cancel local <name>`, nothing else.
- Never `--no-verify`, never amend, never force-push — every stage prompt says so to Muse Code.

## Related

`composer-subagent` skill (the flow, driver brief and stage prompts this reuses) ·
`behaviour-modifiers` skill (the `#muse` registry row) · `/yolo-pr-stack` § *Muse mode* · `/yolo`
§ *Halts no invocation can pre-approve*
