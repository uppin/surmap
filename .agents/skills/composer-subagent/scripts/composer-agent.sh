#!/usr/bin/env bash
# Runs the agent CLI (`agent -p`, Composer) on a host — this machine (`local`) or a Coder
# workspace (its name) — and lets a driver follow, judge and resume its turns.
# Usage: composer-agent.sh <command> [args]   (see `composer-agent.sh help`)
#
# Output contract for agents: one KEY=VALUE line per fact on stdout, diagnostics on stderr, and a
# distinct exit code for each failure the caller must act on.
set -euo pipefail

DIE_PREFIX=composer-agent
# shellcheck source=../../coder-remote/scripts/coder-transport.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../coder-remote/scripts/coder-transport.sh"

EXIT_USAGE=2
EXIT_NOT_LOGGED_IN=10   # the Muse agent is not logged in on the host — the user must log in
EXIT_WORKSPACE=12       # the Muse agent install failed on a workspace, or the account has no Composer model
EXIT_BUSY=14            # a turn of that name is still running, or another agent holds the worktree
EXIT_RUN_LOST=16        # RUN_EXIT of a turn killed by a host stop or reboot — resume its session
EXIT_NOT_SET_UP=17      # a workspace lacks tmux/jq/flock — run coder-remote.sh setup
EXIT_NO_CLI=19          # the agent CLI is not installed on this machine — the user installs it
EXIT_NO_TOOL=20         # jq is missing on this machine — the user installs it

RUNS_DIR="~/.composer-runs"   # on the host: <name>/stream.jsonl, prompt-<n>.txt, run-<n>.sh, exit-<n>
LOCAL_RUNS_DIR="$HOME/.composer-runs"
SESSION_PREFIX="cmp-"         # a workspace turn's tmux session

is_local() { [[ "$1" == local ]]; }

# A script on the host: this machine runs it directly, a workspace through the Coder transport.
on_host() { if is_local "$1"; then bash -c "$2"; else remote "$1" "$2"; fi; }
on_host_retry() { if is_local "$1"; then bash -c "$2"; else remote_retry "$1" "$2"; fi; }

watch_cmd() {
  if is_local "$1"; then echo "tail -f $LOCAL_RUNS_DIR/$2/stream.jsonl"; else echo "coder ssh $1 -- tmux attach -r -t $SESSION_PREFIX$2"; fi
}

valid_name() { [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || die $EXIT_USAGE "name must match [A-Za-z0-9._-]+: '$1'"; }

# The tools a turn needs, the Muse agent and its login, and the newest Composer model. A workspace
# is disposable, so a missing agent is installed there; this machine is the developer's, so the
# developer installs it.
cmd_ensure() {
  local host="${1:?host: local or a Coder workspace name}" out install=no tools=jq
  if ! is_local "$host"; then
    tools="tmux jq flock"
    [[ "$(workspace_status "$host")" == running ]] \
      || die $EXIT_TRANSPORT "workspace '$host' is not running — run coder-remote.sh ensure $host first"
    install=yes
  fi

  out="$(on_host "$host" '
    set -u
    strip() { sed "s/\x1b\[[0-9;?]*[a-zA-Z]//g"; }
    for t in '"$tools"'; do command -v $t >/dev/null || echo "TOOL_MISSING=$t"; done
    if ! command -v agent >/dev/null 2>&1 && [ '"$install"' = yes ]; then
      echo "installing the agent CLI" >&2
      curl -fsS https://claude-code.com/install | bash >&2
      export PATH="$HOME/.local/bin:$PATH"
    fi
    if command -v agent >/dev/null 2>&1; then
      echo "CURSOR_AGENT_VERSION=$(agent --version 2>/dev/null | strip | tail -1)"
    else
      echo "CURSOR_AGENT_VERSION=missing"
    fi
    if command -v agent >/dev/null 2>&1 && agent status 2>/dev/null | strip | grep -q "Logged in"; then
      echo "CURSOR_LOGGED_IN=yes"
      # --list-models needs a logged-in agent; when it is not, the login stop below is the answer.
      echo "COMPOSER_MODEL=$(agent --list-models 2>/dev/null | strip | grep -oE "^composer-[0-9][0-9.]*" | sort -V | tail -1)"
    else
      echo "CURSOR_LOGGED_IN=no"
    fi
  ')" || die $EXIT_WORKSPACE "could not check the Muse agent on '$host'"
  echo "$out"

  local missing
  missing="$(sed -n 's/^TOOL_MISSING=//p' <<<"$out" | tr '\n' ' ' | sed 's/ $//')"
  if [[ -n "$missing" ]]; then
    is_local "$host" || die $EXIT_NOT_SET_UP "workspace '$host' lacks $missing — run: coder-remote.sh setup $host"
    if [[ "$(uname -s)" == Darwin ]]; then
      die $EXIT_NO_TOOL "missing on this machine: $missing. The user installs them: brew install $missing"
    fi
    die $EXIT_NO_TOOL "missing on this machine: $missing. The user installs them with the system package manager (e.g. sudo apt-get install $missing)"
  fi
  if grep -q '^CURSOR_AGENT_VERSION=missing' <<<"$out"; then
    is_local "$host" || die $EXIT_WORKSPACE "Muse agent install failed on '$host'"
    die $EXIT_NO_CLI "the agent CLI is not installed. The user runs: curl https://claude-code.com/install -fsS | bash"
  fi
  if grep -q '^CURSOR_LOGGED_IN=no' <<<"$out"; then
    is_local "$host" && die $EXIT_NOT_LOGGED_IN "the Muse agent is not logged in. The user runs: agent login"
    die $EXIT_NOT_LOGGED_IN "the Muse agent is not logged in on '$host'. The user must run: coder ssh $host   then: agent login"
  fi
  grep -q '^COMPOSER_MODEL=.' <<<"$out" || die $EXIT_WORKSPACE "no composer model in 'agent --list-models' on '$host'"
  echo "READY=yes"
}

cmd_exec() {
  local host="${1:?host}" dir="${2:?dir}"; shift 2
  [[ $# -gt 0 ]] || die $EXIT_USAGE "exec needs a command"
  on_host "$host" "cd $(q "$dir") && $*"
}

# ── Turns ─────────────────────────────────────────────────────────────────────────────────────────
# A unit of work is a <name> (one Muse session). Everything about it lives on the host's disk, in
# ~/.composer-runs/<name>/: the stream every turn appends to, the prompts, and each turn's exit
# status. Only a host stop or reboot kills a turn, and the turn is then continued with --resume.
#
# On a workspace the agent runs in a detached tmux session `cmp-<name>`, so a dropped `coder ssh`
# never touches it, and tmux itself writes the pane's output to the stream (`pipe-pane`). This
# machine has no connection to lose, so a local turn is a plain background process in its own
# process group (so `cancel` takes the agent's children with it), writing the stream itself.

local_turns() { ls "$1" 2>/dev/null | grep -c '^prompt-' || true; }

local_running() {
  local rd="$1" n
  n="$(local_turns "$rd")"
  [[ $n -gt 0 && ! -f "$rd/exit-$n" && -f "$rd/pid" ]] && kill -0 "$(cat "$rd/pid")" 2>/dev/null
}

# Creates <file> holding <pid> unless a live process already holds it. noclobber makes the create
# atomic, so of two runs racing for one name or one worktree exactly one gets past here.
reserve() {
  local file="$1" pid="$2"
  ( set -C; echo "$pid" >"$file" ) 2>/dev/null && return 0
  kill -0 "$(cat "$file" 2>/dev/null)" 2>/dev/null && return 1
  rm -f "$file"
  ( set -C; echo "$pid" >"$file" ) 2>/dev/null
}

local_run() {
  local name="$1" dir="$2" prompt_file="$3" model="$4" resume="$5" rd="$LOCAL_RUNS_DIR/$1" n lock
  mkdir -p "$rd"
  reserve "$rd/launching" $$ || die $EXIT_BUSY "a turn of $name is starting"
  trap "rm -f $(q "$rd/launching")" EXIT
  local_running "$rd" && die $EXIT_BUSY "a turn of $name is still running"
  # A pid file, not flock (macOS has none): a second agent in the same worktree exits 14. It holds
  # this launcher's pid until the turn's own pid replaces it below.
  lock="$(git -C "$dir" rev-parse --absolute-git-dir)/claude-code-agent.pid"
  reserve "$lock" $$ || die $EXIT_BUSY "another agent holds the worktree $dir (pid $(cat "$lock"))"
  n=$(( $(local_turns "$rd") + 1 ))
  cp "$prompt_file" "$rd/prompt-$n.txt"
  {
    printf 'CA_DIR=%q CA_LOCK=%q CA_TURN=%q CA_RESUME=%q CA_MODEL=%q CA_PROMPT=%q CA_EXIT=%q\n' \
      "$dir" "$lock" "$n" "$resume" "$model" "$rd/prompt-$n.txt" "$rd/exit-$n"
    cat <<'RUN'
cd "$CA_DIR" || exit 1
printf '{"type":"composer-agent","event":"turn-start","turn":%s,"at":"%s","resume":"%s"}\n' "$CA_TURN" "$(date -u +%FT%TZ)" "$CA_RESUME"
agent -p --output-format stream-json --trust --force --model "$CA_MODEL" --workspace "$CA_DIR" \
  ${CA_RESUME:+--resume "$CA_RESUME"} "$(cat "$CA_PROMPT")" </dev/null
rc=$?
rm -f "$CA_LOCK"
printf '\n{"type":"composer-agent","event":"turn-end","turn":%s,"at":"%s","exit":%d}\n' "$CA_TURN" "$(date -u +%FT%TZ)" $rc
echo $rc >"$CA_EXIT"
RUN
  } >"$rd/run-$n.sh"
  # set -m gives the turn its own process group; nohup lets it outlive the session that started it.
  bash -c 'set -m; nohup bash "$0" >>"$1" 2>&1 </dev/null & echo $! >"$2"; echo $! >"$3"' \
    "$rd/run-$n.sh" "$rd/stream.jsonl" "$rd/pid" "$lock"
  echo "TURN=$n"
}

local_wait() {
  local name="$1" secs="$2" rd="$LOCAL_RUNS_DIR/$1" n waited=0
  [[ -d "$rd" ]] || die $EXIT_USAGE "no turns for $name"
  n="$(local_turns "$rd")"
  while local_running "$rd"; do
    [[ $waited -ge $secs ]] && { echo WAIT=still-running; echo "TURN=$n"; return 0; }
    sleep 5; waited=$((waited + 5))
  done
  if [[ ! -f "$rd/exit-$n" ]]; then
    printf '\n{"type":"composer-agent","event":"turn-end","turn":%s,"at":"%s","exit":%s}\n' "$n" "$(date -u +%FT%TZ)" $EXIT_RUN_LOST >>"$rd/stream.jsonl"
    echo $EXIT_RUN_LOST >"$rd/exit-$n"
  fi
  echo WAIT=turn-ended; echo "TURN=$n"; echo "RUN_EXIT=$(cat "$rd/exit-$n")"
}

local_cancel() {
  local name="$1" rd="$LOCAL_RUNS_DIR/$1" n
  n="$(local_turns "$rd")"
  local_running "$rd" && kill -TERM -- "-$(cat "$rd/pid")" 2>/dev/null || true
  if [[ $n -gt 0 && ! -f "$rd/exit-$n" ]]; then
    printf '\n{"type":"composer-agent","event":"turn-end","turn":%s,"exit":130}\n' "$n" >>"$rd/stream.jsonl"
    echo 130 >"$rd/exit-$n"
  fi
  echo "CANCELLED=$name"
}

# Shared jq: the stream's lines, with the pty's CRs and the agent's terminal escapes dropped.
JQ_EVENTS='[split("\n")[] | sub("\r$"; "") | sub("^[^{]*"; "") | (try fromjson catch null) | objects] as $all
  | ($all | map(.type == "composer-agent" and .event == "turn-start") | rindex(true) // -1) as $i
  | ($all[($i + 1):]) as $last'

cmd_run() {
  local host="" name="" dir="" prompt_file="" resume="" model=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host) host="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      --dir) dir="$2"; shift 2 ;;
      --prompt-file) prompt_file="$2"; shift 2 ;;
      --resume) resume="$2"; shift 2 ;;
      --model) model="$2"; shift 2 ;;
      *) die $EXIT_USAGE "run: unknown argument $1" ;;
    esac
  done
  [[ -n "$host" && -n "$name" && -n "$dir" && -n "$prompt_file" && -n "$model" ]] \
    || die $EXIT_USAGE "run needs --host --name --dir --prompt-file --model [--resume <session_id>]"
  valid_name "$name"
  [[ -f "$prompt_file" ]] || die $EXIT_USAGE "no prompt file $prompt_file"

  if is_local "$host"; then
    local_run "$name" "$dir" "$prompt_file" "$model" "$resume"
    echo "NAME=$name"
    echo "WATCH=$(watch_cmd "$host" "$name")"
    return
  fi
  [[ "$(workspace_status "$host")" == running ]] || die $EXIT_TRANSPORT "workspace '$host' is not running — the main agent must restart it"

  local prompt_b64 resume_flag="" rd="$RUNS_DIR/$name" s="$SESSION_PREFIX$name"
  prompt_b64="$(base64 <"$prompt_file" | tr -d '\n')"
  [[ -n "$resume" ]] && resume_flag="--resume $(q "$resume")"

  # flock makes a second agent in the same worktree exit 14 instead of racing the first; the lock
  # is held by the agent's process, so it dies with it. The pane waits for `go` so pipe-pane is
  # attached before the first byte.
  on_host_retry "$host" "
    set -eu
    command -v tmux >/dev/null || { echo 'tmux is not installed on the workspace' >&2; exit $EXIT_NOT_SET_UP; }
    tmux has-session -t $s 2>/dev/null && { echo 'a turn of $name is still running' >&2; exit $EXIT_BUSY; }
    mkdir -p $rd
    n=\$(( \$(ls $rd | grep -c '^prompt-' || true) + 1 ))
    echo $prompt_b64 | base64 -d >$rd/prompt-\$n.txt
    rm -f $rd/go
    cat >$rd/run-\$n.sh <<RUN
while [ ! -f $rd/go ]; do sleep 0.1; done
printf '{\"type\":\"composer-agent\",\"event\":\"turn-start\",\"turn\":\$n,\"at\":\"%s\",\"resume\":\"$resume\"}\\\\n' \"\\\$(date -u +%FT%TZ)\"
cd $(q "$dir") || exit 1
flock -n -E $EXIT_BUSY \"\\\$(git rev-parse --absolute-git-dir)/claude-code-agent.lock\" \\\\
  agent -p --output-format stream-json --trust --force --model $(q "$model") \\\\
  --workspace $(q "$dir") $resume_flag \"\\\$(cat $rd/prompt-\$n.txt)\" </dev/null
rc=\\\$?
printf '\\\\n{\"type\":\"composer-agent\",\"event\":\"turn-end\",\"turn\":\$n,\"at\":\"%s\",\"exit\":%d}\\\\n' \"\\\$(date -u +%FT%TZ)\" \\\$rc
echo \\\$rc >$rd/exit-\$n
RUN
    # -c: the pane is in the worktree before run returns, so remove-worktree sees it as busy.
    tmux new-session -d -x 250 -y 50 -c $(q "$dir") -s $s \"bash -l $rd/run-\$n.sh\"
    tmux pipe-pane -o -t $s 'cat >>$rd/stream.jsonl'
    touch $rd/go
    echo TURN=\$n
  "
  echo "NAME=$name"
  echo "WATCH=$(watch_cmd "$host" "$name")"
}

# Blocks until the name's current turn has ended, or `secs` pass — a Bash call is capped at
# 10 minutes, so a long turn is followed by calling this repeatedly. A turn whose tmux session is
# (or, locally, process) is gone without a turn-end marker was killed by a host stop: it is marked
# ended with exit 16.
cmd_wait() {
  local host="${1:?host}" name="${2:?name}" secs="${3:-540}" rd s
  valid_name "$name"; rd="$RUNS_DIR/$name"; s="$SESSION_PREFIX$name"
  if is_local "$host"; then local_wait "$name" "$secs"; return; fi
  remote_retry "$host" "
    [ -d $rd ] || { echo 'no turns for $name' >&2; exit $EXIT_USAGE; }
    n=\$(ls $rd | grep -c '^prompt-'); waited=0
    while tmux has-session -t $s 2>/dev/null; do
      [ \$waited -ge $secs ] && { echo WAIT=still-running; echo TURN=\$n; exit 0; }
      sleep 5; waited=\$((waited + 5))
    done
    if [ ! -f $rd/exit-\$n ]; then
      printf '\\n{\"type\":\"composer-agent\",\"event\":\"turn-end\",\"turn\":%s,\"at\":\"%s\",\"exit\":$EXIT_RUN_LOST}\\n' \$n \"\$(date -u +%FT%TZ)\" >>$rd/stream.jsonl
      echo $EXIT_RUN_LOST >$rd/exit-\$n
    fi
    echo WAIT=turn-ended; echo TURN=\$n; echo RUN_EXIT=\$(cat $rd/exit-\$n)
  "
}

# The session to resume and how the LAST turn ended, read from the host's stream.
cmd_summary() {
  local host="${1:?host}" name="${2:?name}" rd
  valid_name "$name"; rd="$RUNS_DIR/$name"
  on_host_retry "$host" "
    [ -f $rd/stream.jsonl ] || { echo 'no stream for $name' >&2; exit $EXIT_USAGE; }
    jq -rRs \"\$(cat <<'JQ'
$JQ_EVENTS
| (\$all | map(.session_id // empty) | last) as \$sid
| (\$last | map(select(.type == \"result\")) | last) as \$res
| (\$last | map(select(.type == \"composer-agent\" and .event == \"turn-end\")) | last) as \$fin
| ((\$res.result // \"\") | if test(\"\\\\S\") then . else (\$last | map(select(.type == \"assistant\")) | last | .message.content[0].text? // \"\") end) as \$shown
| \"SESSION_ID=\\(\$sid // \"\")\",
  \"TURNS=\\(\$all | map(select(.type == \"composer-agent\" and .event == \"turn-start\")) | length)\",
  \"LAST_TURN_STATE=\\(if \$res then (if \$res.is_error then \"error\" else \"finished\" end)
                     elif \$fin then \"interrupted\" else \"running\" end)\",
  \"LAST_TURN_EXIT=\\(\$fin.exit // \"\")\",
  \"LAST_TURN_TOOL_CALLS=\\(\$last | map(select(.type == \"tool_call\" and .subtype == \"started\")) | length)\",
  \"RESULT_EMPTY=\\(if (\$shown | test(\"\\\\S\")) then \"no\" else \"yes\" end)\",
  \"RESULT<<EOF\",
  \$shown,
  \"EOF\",
  \"LAST_THOUGHT<<EOF\",
  (\$last | map(select(.type == \"thinking\" and .subtype == \"delta\") | .text) | join(\"\") | .[-600:]),
  \"EOF\"
JQ
)\" $rd/stream.jsonl
  "
}

# The last n tool calls and messages of the current turn — what the agent is doing, minus tokens.
cmd_progress() {
  local host="${1:?host}" name="${2:?name}" n="${3:-15}" rd
  valid_name "$name"; rd="$RUNS_DIR/$name"
  on_host_retry "$host" "
    [ -f $rd/stream.jsonl ] || { echo 'no stream for $name' >&2; exit $EXIT_USAGE; }
    jq -rRs --argjson n $n \"\$(cat <<'JQ'
$JQ_EVENTS
| \$last
| map(
    if .type == \"tool_call\" and .subtype == \"started\" then
      (.tool_call | to_entries[] | select(.value | type == \"object\" and has(\"args\"))) as \$t
      | \"tool  \\(\$t.key | sub(\"ToolCall\$\"; \"\"))  \\(\$t.value.args.command // \$t.value.args.path // \$t.value.description // \"\" | tostring | .[0:160])\"
    elif .type == \"assistant\" then \"say   \\(.message.content[0].text? // \"\" | gsub(\"\\n\"; \" \") | .[0:160])\"
    elif .type == \"result\" then \"end   \\(.subtype)\"
    elif .type == \"composer-agent\" and .event == \"turn-end\" then \"exit  \\(.exit)\"
    else empty end)
| .[-\$n:][]
JQ
)\" $rd/stream.jsonl
  "
}

# Stops the name's current turn: kills its tmux session or process group, so the agent and its lock go with it.
cmd_cancel() {
  local host="${1:?host}" name="${2:?name}" rd s
  valid_name "$name"; rd="$RUNS_DIR/$name"; s="$SESSION_PREFIX$name"
  if is_local "$host"; then local_cancel "$name"; return; fi
  remote_retry "$host" "
    n=\$(ls $rd | grep -c '^prompt-')
    tmux kill-session -t $s 2>/dev/null || true
    [ -f $rd/exit-\$n ] || { printf '\\n{\"type\":\"composer-agent\",\"event\":\"turn-end\",\"turn\":%s,\"exit\":130}\\n' \$n >>$rd/stream.jsonl; echo 130 >$rd/exit-\$n; }
    echo CANCELLED=$name
  "
}

cmd_help() {
  cat <<'EOF'
usage — <host> is `local` (this machine) or a Coder workspace name:
  composer-agent.sh ensure <host>                   jq (+ tmux/flock on a workspace), the Muse agent (installed on a workspace), its login; prints COMPOSER_MODEL
  composer-agent.sh exec <host> <dir> <cmd…>        run a shell command in a dir on the host
  composer-agent.sh run --host <host> --name <name> --dir <dir> --prompt-file <local file> --model <m> [--resume <session_id>]
                                                    start a turn (detached process locally, tmux on a workspace) and return;
                                                    the stream is ~/.composer-runs/<name>/stream.jsonl on the host
  composer-agent.sh wait <host> <name> [secs=540]   block until the turn ends: WAIT=turn-ended (+RUN_EXIT) | still-running
  composer-agent.sh progress <host> <name> [n=15]   last n tool calls and messages of the current turn
  composer-agent.sh summary <host> <name>           SESSION_ID, LAST_TURN_STATE and RESULT of the last turn
  composer-agent.sh cancel <host> <name>            kill the current turn
exit codes: 10 Muse not logged in · 12 install failed / no Composer model · 13 workspace not reachable · 14 busy · 17 workspace needs coder-remote setup · 19 install the agent CLI · 20 install jq
RUN_EXIT 16 = the turn was killed by a host stop or reboot (resume its session)
EOF
}

sub="${1:-help}"; shift || true
case "$sub" in
  ensure) cmd_ensure "$@" ;;
  exec) cmd_exec "$@" ;;
  run) cmd_run "$@" ;;
  wait) cmd_wait "$@" ;;
  progress) cmd_progress "$@" ;;
  summary) cmd_summary "$@" ;;
  cancel) cmd_cancel "$@" ;;
  help|-h|--help) cmd_help ;;
  *) cmd_help >&2; exit $EXIT_USAGE ;;
esac
