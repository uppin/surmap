# Sourced, not run: the transport to a Coder workspace, shared by coder-remote.sh (the workspace's
# lifecycle) and composer-subagent's composer-agent.sh (Muse agent turns on a workspace host).

EXIT_TRANSPORT=13       # workspace not reachable after retries (it stopped) — the main agent restarts it

die() { local code="$1"; shift; echo "${DIE_PREFIX:-coder-remote}: $*" >&2; exit "$code"; }

q() { printf '%q' "$1"; }

# Runs a bash script on the workspace in a login environment. The script travels base64-encoded in argv
# because `coder ssh` does not close a piped stdin, so `bash -s` would hang forever.
# `coder ssh` reports every remote failure as its own exit 1, so the remote status is recovered
# from its "Process exited with status N" line; a failure without that line is a lost transport.
# It also turns every LF into CRLF, so stdout is stripped of CRs before the caller sees it.
remote() {
  local ws="$1" script="$2" b64 out err rc=0 remote_rc
  # `coder ssh` gives the command a terminal (and has no option not to), so git and jq would page
  # and colour their output.
  b64="$(printf 'export PAGER=cat GIT_PAGER=cat NO_COLOR=1 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=color.ui GIT_CONFIG_VALUE_0=never\njq() { command jq -M "$@"; }\n%s' "$script" | base64 | tr -d '\n')"
  out="$(mktemp)"; err="$(mktemp)"
  # The login shell only sets up the environment, then execs a plain bash for the script: a login
  # shell runs ~/.bash_logout on exit, and under the script's `set -e` that rewrites its status to 1.
  # --disable-autostart: `coder ssh` would otherwise start a stopped workspace by itself, and only
  # `ensure` (the main agent) may start one.
  coder ssh "$ws" --wait=yes --disable-autostart -- bash -lc "'exec bash -c \"\$(echo $b64 | base64 -d)\"'" >"$out" 2>"$err" || rc=$?
  tr -d '\r' <"$out"
  remote_rc="$(tr -d '\r' <"$err" | grep -oE 'Process exited with status [0-9]+' | grep -oE '[0-9]+$' | tail -1 || true)"
  tr -d '\r' <"$err" | grep -vE '^20[0-9]{2}-|Process exited with status|Encountered an error running "coder ssh"' >&2 || true
  rm -f "$out" "$err"
  [[ $rc -eq 0 ]] && return 0
  [[ -n "$remote_rc" ]] && return "$remote_rc"
  return $EXIT_TRANSPORT
}

workspace_status() {
  coder list -o json | jq -r --arg ws "$1" '.[] | select(.name == $ws) | .latest_build.status'
}

# Short reads retry through a dropped connection while the workspace is up; once it is not, 13.
remote_retry() {
  local ws="$1" script="$2" rc attempt
  for attempt in 1 2 3 4 5 6; do
    rc=0; remote "$ws" "$script" || rc=$?
    [[ $rc -eq $EXIT_TRANSPORT ]] || return $rc
    [[ "$(workspace_status "$ws")" == running ]] || break
    echo "${DIE_PREFIX:-coder-remote}: connection dropped, retrying ($attempt/6)" >&2; sleep 10
  done
  die $EXIT_TRANSPORT "workspace '$ws' is not reachable — the main agent must restart it"
}
