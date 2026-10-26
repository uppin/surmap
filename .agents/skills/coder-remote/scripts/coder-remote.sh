#!/usr/bin/env bash
# Local driver for a Coder workspace's lifecycle: list, provision, start, worktrees. What runs in a
# worktree there (the Muse agent, by default) is the composer-subagent skill's composer-agent.sh.
# Usage: coder-remote.sh <command> [args]   (see `coder-remote.sh help`)
#
# Output contract for agents: one KEY=VALUE line per fact on stdout, diagnostics on stderr, and a
# distinct exit code for each failure the caller must act on.
set -euo pipefail

# shellcheck source=coder-transport.sh
source "$(dirname "${BASH_SOURCE[0]}")/coder-transport.sh"

EXIT_USAGE=2
EXIT_GH_NOT_LOGGED_IN=11
EXIT_WORKSPACE=12       # workspace failed to start, or a provisioning step failed
EXIT_BUSY=14            # a process still runs in the worktree — removing it would kill that process
EXIT_PINNED=15          # the branch is checked out in another remote worktree
EXIT_NOT_SET_UP=17      # the workspace lacks the repo checkout or tools — run `setup`
EXIT_GITHUB_SSH=18      # GitHub rejects the workspace's Coder SSH key — the user must add it

REMOTE_REPO="${CODER_REMOTE_REPO:-~/Code/this repo}"
REMOTE_WORKTREES="${CODER_REMOTE_WORKTREES:-~/Code/this repo/.worktrees}"

cmd_list() {
  coder list -o json | jq -r '
    ["WORKSPACE", "TEMPLATE", "STATUS", "TRANSITION", "LAST_USED"],
    (.[] | [.name, .template_name, .latest_build.status, .latest_build.transition, .last_used_at[0:16]])
    | @tsv' | column -t
}

start_workspace() {
  local ws="$1" status
  status="$(workspace_status "$ws")"
  [[ -n "$status" ]] || die $EXIT_USAGE "no workspace named '$ws' (coder-remote.sh list)"
  echo "WORKSPACE_STATUS_BEFORE=$status"
  case "$status" in
    running|starting) ;;
    # A failed last build is usually a failed autostop; starting cleans it up and rebuilds.
    stopping|stopped|failed|canceled) coder start "$ws" --yes >&2 || die $EXIT_WORKSPACE "coder start $ws failed" ;;
    *) die $EXIT_WORKSPACE "workspace '$ws' is '$status' — not startable from here" ;;
  esac
}

# The repo this script belongs to, as the workspace should clone it: always the SSH form, so a
# token in an HTTPS origin never reaches the workspace's .git/config and the access check really
# tests SSH (through `coder gitssh`).
repo_url() {
  local origin path
  origin="$(git -C "$(dirname "${BASH_SOURCE[0]}")" remote get-url origin 2>/dev/null)" \
    || die $EXIT_USAGE "cannot read the local checkout's origin URL"
  case "$origin" in
    git@github.com:*) path="${origin#git@github.com:}" ;;
    ssh://git@github.com/*) path="${origin#ssh://git@github.com/}" ;;
    https://github.com/*) path="${origin#https://github.com/}" ;;
    https://*@github.com/*) path="${origin#https://*@github.com/}" ;;
    *) die $EXIT_USAGE "origin is not a GitHub URL — cannot derive the SSH clone URL" ;;
  esac
  path="${path%.git}"
  [[ "$path" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || die $EXIT_USAGE "unexpected repo path in origin"
  echo "git@github.com:$path.git"
}

# Provisions a workspace's internals, idempotently: system tools (tmux, jq and flock are what an agent
# turn needs), GitHub SSH access, the repo checkout, the uv run pytest -q, git identity. What only the user
# can do (adding the Coder SSH key to GitHub, logging in to gh) ends it with that code. The Muse
# agent is composer-agent.sh's: its `ensure <ws>` installs it.
cmd_setup() {
  local ws="${1:?workspace}" out url name email
  start_workspace "$ws"
  url="$(repo_url)"; name="$(git config user.name || true)"; email="$(git config user.email || true)"
  out="$(remote "$ws" "
    set -u
    missing=''
    for t in tmux jq flock git curl; do command -v \$t >/dev/null || missing=\"\$missing \$t\"; done
    if [ -n \"\$missing\" ] && sudo -n true 2>/dev/null; then
      echo \"installing:\$missing\" >&2
      sudo apt-get update -qq >&2 && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \$missing >&2
      missing=''
      for t in tmux jq flock git curl; do command -v \$t >/dev/null || missing=\"\$missing \$t\"; done
    fi
    echo \"TOOLS_MISSING=\${missing# }\"
    for t in node corepack gh; do command -v \$t >/dev/null || echo \"TOOLS_MISSING_FROM_TEMPLATE=\$t\"; done

    if git ls-remote --heads $(q "$url") >/dev/null 2>&1; then echo GITHUB_SSH=yes; else echo GITHUB_SSH=no; fi
    if [ ! -d $REMOTE_REPO/.git ] && git ls-remote --heads $(q "$url") >/dev/null 2>&1; then
      echo 'cloning $url into $REMOTE_REPO' >&2
      mkdir -p \"\$(dirname $REMOTE_REPO)\" && git clone --quiet $(q "$url") $REMOTE_REPO >&2
    fi
    if [ -d $REMOTE_REPO/.git ]; then echo \"REPO=\$(cd $REMOTE_REPO && pwd)\"; mkdir -p $REMOTE_WORKTREES; else echo REPO=missing; fi

    if [ -d $REMOTE_REPO ] && ! (cd $REMOTE_REPO && yarn --version) >/dev/null 2>&1; then
      find \"\$HOME/.local/bin\" -maxdepth 1 -xtype l \\( -name 'yarn*' -o -name 'pnp*' \\) -delete 2>/dev/null
      mkdir -p \"\$HOME/.local/bin\" && corepack enable --install-directory \"\$HOME/.local/bin\" >&2
    fi
    echo \"YARN_VERSION=\$(cd $REMOTE_REPO 2>/dev/null && yarn --version 2>/dev/null || echo missing)\"

    [ -n \"\$(git config --global user.name)\" ] || git config --global user.name $(q "$name")
    [ -n \"\$(git config --global user.email)\" ] || git config --global user.email $(q "$email")
    echo \"GIT_IDENTITY=\$(git config --global user.name) <\$(git config --global user.email)>\"

    if gh auth status >/dev/null 2>&1; then echo GH_LOGGED_IN=yes; else echo GH_LOGGED_IN=no; fi
  ")" || die $EXIT_WORKSPACE "could not reach workspace '$ws' over ssh"
  echo "$out"

  grep -q '^TOOLS_MISSING=.' <<<"$out" && die $EXIT_WORKSPACE "missing tools on '$ws' and no passwordless sudo to install them — use a different template"
  grep -q '^TOOLS_MISSING_FROM_TEMPLATE=' <<<"$out" && die $EXIT_WORKSPACE "the workspace's template lacks node/corepack/gh — use an ec2-monorepo workspace"
  grep -q '^GITHUB_SSH=no' <<<"$out" && die $EXIT_GITHUB_SSH \
    "GitHub does not accept the workspace's SSH key. The user must run \`coder publickey\` locally, add the key at https://github.com/settings/ssh/new, and authorize it for the org's SSO; then run setup again"
  grep -q '^YARN_VERSION=missing' <<<"$out" && die $EXIT_WORKSPACE "uv run pytest -q not runnable in $REMOTE_REPO on '$ws'"
  grep -q '^GH_LOGGED_IN=no' <<<"$out" && die $EXIT_GH_NOT_LOGGED_IN \
    "gh is not logged in on '$ws'. The user must run: coder ssh $ws   then: gh auth login"
  echo "SETUP=done"
}

cmd_ensure() {
  local ws="${1:?workspace}" out
  start_workspace "$ws"

  out="$(remote "$ws" '
    set -u
    if [ -d '"$REMOTE_REPO"'/.git ]; then echo "REPO=$(cd '"$REMOTE_REPO"' && pwd)"; else echo "REPO=missing"; fi
    for t in tmux jq flock; do command -v $t >/dev/null || echo "TOOL_MISSING=$t"; done
    # The uv run pytest -q dangles after the node manager changes (fnm -> mise) and corepack refuses to
    # relink over a dangling link, so drop those first.
    if ! (cd '"$REMOTE_REPO"' && yarn --version) >/dev/null 2>&1; then
      find "$HOME/.local/bin" -maxdepth 1 -xtype l \( -name "yarn*" -o -name "pnp*" \) -delete
      corepack enable --install-directory "$HOME/.local/bin" >&2
    fi
    echo "YARN_VERSION=$(cd '"$REMOTE_REPO"' && yarn --version 2>/dev/null || echo missing)"
    if gh auth status >/dev/null 2>&1; then echo "GH_LOGGED_IN=yes"; else echo "GH_LOGGED_IN=no"; fi
  ')" || die $EXIT_WORKSPACE "could not reach workspace '$ws' over ssh"
  echo "$out"

  grep -qE '^(REPO=missing|TOOL_MISSING=)' <<<"$out" && die $EXIT_NOT_SET_UP \
    "workspace '$ws' is not provisioned for coder-remote — run: coder-remote.sh setup $ws"
  grep -q '^YARN_VERSION=missing' <<<"$out" && die $EXIT_WORKSPACE "uv run pytest -q not runnable on '$ws' even after corepack enable"
  grep -q '^GH_LOGGED_IN=no' <<<"$out" && die $EXIT_GH_NOT_LOGGED_IN \
    "gh is not logged in on '$ws'. The user must run: coder ssh $ws   then: gh auth login"
  echo "READY=yes"
}

# An existing branch is checked out tracking its own origin branch. With `--from <base>`, a NEW
# branch is cut from origin/<base> with no upstream, so a bare `git push` can never land on <base>.
cmd_worktree() {
  local ws="${1:?workspace}" branch="${2:?branch}" name="${3:?worktree name}" from="" b n
  [[ "${4:-}" == --from ]] && from="${5:?--from needs a base branch}"
  valid_ref "$branch"; valid_name "$name"; [[ -z "$from" ]] || valid_ref "$from"
  b="$(q "$branch")"; n="$(q "$name")"
  if [[ -n "$from" ]]; then
    remote "$ws" "
      set -eu
      cd $REMOTE_REPO
      git fetch --quiet origin $(q "$from")
      if git show-ref --verify --quiet refs/heads/$b || git ls-remote --exit-code --heads origin $b >/dev/null; then
        echo 'that branch already exists locally or on origin — drop --from to check it out' >&2; exit $EXIT_USAGE
      fi
      git worktree add --quiet --no-track -b $b $REMOTE_WORKTREES/$n origin/$(q "$from")
      cd $REMOTE_WORKTREES/$n
      echo \"WORKTREE=\$(pwd)\"
      echo \"HEAD=\$(git rev-parse HEAD)\"
      echo UPSTREAM=none
    "
    return
  fi
  remote "$ws" "
    set -eu
    cd $REMOTE_REPO
    git fetch --quiet origin $b
    dir=$REMOTE_WORKTREES/$n
    if [ -d \"\$dir\" ]; then
      [ \"\$(git -C \"\$dir\" branch --show-current)\" = $b ] || { echo \"\$dir exists on another branch\" >&2; exit $EXIT_PINNED; }
    else
      if git worktree list --porcelain | grep -qxF -- \"branch refs/heads/\"$b; then
        echo 'the branch is checked out in another worktree:' >&2; git worktree list >&2; exit $EXIT_PINNED
      fi
      mkdir -p $REMOTE_WORKTREES
      if git show-ref --verify --quiet refs/heads/$b; then
        git worktree add --quiet \"\$dir\" $b
      else
        git worktree add --quiet --track -b $b \"\$dir\" origin/$b
      fi
    fi
    cd \"\$dir\"
    git merge --ff-only --quiet origin/$b
    echo \"WORKTREE=\$(pwd)\"
    echo \"HEAD=\$(git rev-parse HEAD)\"
    echo \"UNPUSHED=\$(git rev-list --count origin/$b..HEAD)\"
  "
}

cmd_exec() {
  local ws="${1:?workspace}" dir="${2:?remote dir}"; shift 2
  [[ $# -gt 0 ]] || die $EXIT_USAGE "exec needs a command"
  remote "$ws" "cd $(q "$dir") && $*"
}

cmd_remove_worktree() {
  local ws="${1:?workspace}" dir="${2:?remote worktree dir}" d
  d="$(q "$dir")"
  remote "$ws" "
    set -eu
    # Busy first, from outside the worktree so this script's own cwd does not count: any process
    # whose cwd is in it — a Muse agent turn, the user's shell, another agent — would be killed.
    cd $REMOTE_REPO
    dir=\$(cd $d && pwd -P)
    busy=''
    for p in /proc/[0-9]*; do
      c=\$(readlink \$p/cwd 2>/dev/null) || continue
      case \"\$c\" in \"\$dir\"|\"\$dir\"/*) busy=\"\$busy \${p#/proc/}\" ;; esac
    done
    if [ -n \"\$busy\" ]; then
      echo \"processes still run in \$dir — not removing it:\" >&2; ps -o pid,user,args -p \"\$(echo \$busy | tr ' ' ,)\" >&2 || true; exit $EXIT_BUSY
    fi
    cd $d
    branch=\$(git branch --show-current)
    dirty=\$(git status --porcelain | grep -v '^?? ' || true)
    [ -z \"\$dirty\" ] || { echo \"uncommitted tracked changes in \$PWD:\" >&2; echo \"\$dirty\" >&2; exit 1; }
    # Against every origin ref, not origin/<branch>: a --from branch may never have been pushed.
    git fetch --quiet origin
    [ \"\$(git rev-list --count HEAD --not --remotes=origin)\" = 0 ] || { echo \"unpushed commits on \$branch\" >&2; exit 1; }
    cd $REMOTE_REPO
    git worktree remove --force $d && git worktree prune
    echo REMOVED=$d
  "
}

# Branch names reach generated shell source, so they are held to a plain allowlist on top of git's own rules.
valid_ref() {
  [[ "$1" =~ ^[A-Za-z0-9._/-]+$ ]] && git check-ref-format --branch "$1" >/dev/null 2>&1 \
    || die $EXIT_USAGE "not a plain branch name ([A-Za-z0-9._/-], valid for git): '$1'"
}

valid_name() { [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || die $EXIT_USAGE "name must match [A-Za-z0-9._-]+: '$1'"; }

cmd_help() {
  cat <<'EOF'
usage:
  coder-remote.sh list
  coder-remote.sh setup <ws>                        provision a new workspace: tools, GitHub SSH, repo clone, yarn, git identity, gh login
  coder-remote.sh ensure <ws>                       start if stopped; verify the repo, tools, uv run pytest -q the gh login
  coder-remote.sh worktree <ws> <branch> <name> [--from <base>]
                                                    check out (or fast-forward) <branch> in ~/Code/this repo/.worktrees/<name>;
                                                    --from cuts a NEW <branch> from origin/<base>, with no upstream
  coder-remote.sh exec <ws> <remote-dir> <cmd…>     run a shell command in a remote dir
  coder-remote.sh remove-worktree <ws> <remote-dir> remove once nothing runs in it, nothing tracked is dirty and nothing is unpushed
the Muse agent on a workspace: .agents/skills/composer-subagent/scripts/composer-agent.sh (ensure/run/wait/progress/summary/cancel <ws>)
exit codes: 11 gh not logged in · 12 workspace/provisioning · 13 transport lost · 14 a process runs in the worktree · 15 branch pinned · 17 run setup · 18 add the Coder SSH key to GitHub
EOF
}

sub="${1:-help}"; shift || true
case "$sub" in
  list) cmd_list "$@" ;;
  setup) cmd_setup "$@" ;;
  ensure) cmd_ensure "$@" ;;
  worktree) cmd_worktree "$@" ;;
  exec) cmd_exec "$@" ;;
  remove-worktree) cmd_remove_worktree "$@" ;;
  help|-h|--help) cmd_help ;;
  *) cmd_help >&2; exit $EXIT_USAGE ;;
esac
