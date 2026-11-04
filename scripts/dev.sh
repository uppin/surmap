#!/usr/bin/env bash
# Local dev stack: CM5 server, station server, survey agent and the agent chat UI.
# Each service runs in its own process group with its output prefixed by its name.
# Ctrl-C, SIGTERM or SIGHUP stops every service (and whatever it spawned); so does any
# one service exiting, in which case the script exits with that service's status.
# A SIGKILL of this script cannot be trapped: stop the groups by hand then.
#
# Usage: scripts/dev.sh [--model <id>] [--with-sam] [--bridge] [--dry-run]
#
#   --with-sam  the station serves SAM 3.1 on the Mac GPU (MPS) instead of the in-memory
#               detector; torch and sam3 are layered on by `uv run --with` (the project's
#               .venv and uv.lock stay as they are). facebook/sam3.1 is gated: HF_TOKEN in
#               .env or the shell. The agent keeps its fake SAM: it has no real-SAM option yet.
#   --bridge    the agent serves the stereo bridge, so the chat's simulation preview streams
#               its drone's camera to RTAB-Map and draws the keypoints it tracks; the
#               streaming RTAB-Map image is made ready first (Docker; built once per source)
#   --dry-run   print each service's command and exit
#
# The agent keeps its state (conversations, map scenes, runs, scenarios, tool outputs) in
# the gitignored <repo>/tmp/agent, so a restart brings the chat back as it was; downloaded
# datasets stay in the shared cache (~/.cache/surmap).
#
# Environment:
#   SURMAP_DEV_MODEL         agent model id (default: the agent's own default)
#   SURMAP_DEV_CM5_PORT      CM5 server port (default 8080)
#   SURMAP_DEV_STATION_PORT  station server port (default 8081)
#   SURMAP_DEV_SIM_DIST      sim page build the agent serves at /sim/ (default:
#                            examples/bevy-sitl-poc/dist; built for /sim/ when missing,
#                            built for another prefix or older than the sim's source —
#                            needs `trunk`)
#   SURMAP_DEV_SIM_FETCH_CMD fetches the sim's pinned assets (default:
#                            `uv run python scripts/fetch_sim_assets.py`)
#   SURMAP_DEV_BRIDGE_PORT   stereo bridge port with --bridge (default 8782)
#   SURMAP_DEV_RTABMAP_INIT_CMD makes the streaming RTAB-Map image ready with --bridge
#                            (default: `uv run python scripts/build_rtabmap_stream.py`)
#   SURMAP_DEV_STOP_TIMEOUT  seconds a service gets to stop before SIGKILL (default 5)
#   SURMAP_DEV_<NAME>_CMD    replaces a service's command (NAME: CM5, STATION, AGENT, CHAT)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'
}

MODEL="${SURMAP_DEV_MODEL:-}"
WITH_SAM=0
BRIDGE=0
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --model) MODEL="${2:?--model needs a model id}"; shift 2 ;;
    --with-sam) WITH_SAM=1; shift ;;
    --bridge) BRIDGE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "dev.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

CM5_PORT="${SURMAP_DEV_CM5_PORT:-8080}"
STATION_PORT="${SURMAP_DEV_STATION_PORT:-8081}"
SIM_DIST="${SURMAP_DEV_SIM_DIST:-$ROOT/examples/bevy-sitl-poc/dist}"
SIM_FETCH_CMD="${SURMAP_DEV_SIM_FETCH_CMD:-uv run python scripts/fetch_sim_assets.py}"
SIM_ASSETS="$ROOT/examples/bevy-sitl-poc/assets"
STOP_TIMEOUT="${SURMAP_DEV_STOP_TIMEOUT:-5}"
BRIDGE_PORT="${SURMAP_DEV_BRIDGE_PORT:-8782}"
RTABMAP_INIT_CMD="${SURMAP_DEV_RTABMAP_INIT_CMD:-uv run python scripts/build_rtabmap_stream.py}"

AGENT_ARGS="--sam-fake --state-dir $ROOT/tmp/agent"
[ -n "$MODEL" ] && AGENT_ARGS="$AGENT_ARGS --model $MODEL"
CHAT_ENV=""
if [ "$BRIDGE" = 1 ]; then
  AGENT_ARGS="$AGENT_ARGS --bevy-bridge-port $BRIDGE_PORT"
  CHAT_ENV="VITE_SURMAP_BRIDGE_URL=ws://127.0.0.1:$BRIDGE_PORT "
fi

STATION_RUN="uv run"
STATION_ARGS="--host 127.0.0.1 --port $STATION_PORT"
if [ "$WITH_SAM" = 1 ]; then
  STATION_RUN="uv run --with torch --with torchvision --with 'setuptools<81' --with git+https://github.com/facebookresearch/sam3.git"
  STATION_ARGS="$STATION_ARGS --detector sam31-torch --sam31-device mps"
fi

SERVICES="cm5 station agent chat"
CMD_cm5="${SURMAP_DEV_CM5_CMD:-exec uv run python -m surmap.survey.cm5_main --host 127.0.0.1 --port $CM5_PORT}"
CMD_station="${SURMAP_DEV_STATION_CMD:-exec $STATION_RUN python -m surmap.survey.station_main $STATION_ARGS}"
CMD_agent="${SURMAP_DEV_AGENT_CMD:-exec uv run python -m surmap.agent $AGENT_ARGS --sim-dist $SIM_DIST}"
CMD_chat="${SURMAP_DEV_CHAT_CMD:-cd web/agent-chat && ${CHAT_ENV}exec yarn dev}"

if [ "$DRY_RUN" = 1 ]; then
  for name in $SERVICES; do
    eval "echo \"$name: \$CMD_$name\""
  done
  exit 0
fi

if [ "$WITH_SAM" = 1 ] && [ -z "${HF_TOKEN:-}" ] && ! grep -qs '^HF_TOKEN=' .env \
  && [ ! -s "${HF_HOME:-$HOME/.cache/huggingface}/token" ]; then
  echo "dev.sh: warning: no HF_TOKEN (shell, .env or huggingface-cli login); facebook/sam3.1 is gated" >&2
fi

if [ -z "${SURMAP_DEV_CM5_CMD:-}" ] || [ -z "${SURMAP_DEV_STATION_CMD:-}" ] || [ -z "${SURMAP_DEV_AGENT_CMD:-}" ]; then
  command -v uv >/dev/null 2>&1 || {
    echo "dev.sh: uv not found on PATH; install it (https://docs.astral.sh/uv/) first" >&2
    exit 1
  }
fi

if [ -z "${SURMAP_DEV_CHAT_CMD:-}" ]; then
  command -v yarn >/dev/null 2>&1 || {
    echo "dev.sh: yarn not found on PATH; install Node.js and yarn first" >&2
    exit 1
  }
  if [ ! -d web/agent-chat/node_modules ]; then
    echo "dev.sh: web/agent-chat has no node_modules; run 'yarn local-install' there first" >&2
    exit 1
  fi
fi

if [ ! -d "$SIM_ASSETS" ]; then
  echo "dev.sh: simulation assets missing: $SIM_ASSETS (the agent serves them under /sim/assets)" >&2
  exit 1
fi
# The page's textures, models and HDRI are pinned in assets.lock.json and fetched,
# never committed; without them the scene loads untextured (asset 404s in the console).
echo "dev.sh: ensuring the simulation's pinned assets (fetch_sim_assets.py)" >&2
if ! bash -c "$SIM_FETCH_CMD"; then
  echo "dev.sh: could not fetch the simulation's pinned assets; check the network and re-run" >&2
  exit 1
fi
# The bridge hands each drone's frames to a streaming RTAB-Map sidecar; its image is
# derived from the pinned one and tagged by source hash, so this builds it at most once.
if [ "$BRIDGE" = 1 ]; then
  echo "dev.sh: ensuring the streaming RTAB-Map image (build_rtabmap_stream.py)" >&2
  if ! bash -c "$RTABMAP_INIT_CMD"; then
    echo "dev.sh: could not make the streaming RTAB-Map image ready; start Docker and re-run" >&2
    exit 1
  fi
fi
# The agent serves the Bevy simulation at /sim/ from $SIM_DIST. A page built without
# `--public-url /sim/` addresses its JS/WASM from the server root, which 404s under
# /sim/ and leaves a black canvas — so a missing or foreign-prefix build is (re)built,
# and so is one older than the simulation's source (it would serve yesterday's page).
SIM_SRC="$ROOT/examples/bevy-sitl-poc"
sim_page_stale() {
  [ -n "$(find "$SIM_SRC/src" "$SIM_SRC/index.html" "$SIM_SRC/Cargo.toml" "$SIM_SRC/Cargo.lock" \
    -newer "$SIM_DIST/index.html" -print -quit 2>/dev/null)" ]
}
if [ ! -f "$SIM_DIST/index.html" ] || ! grep -q "/sim/" "$SIM_DIST/index.html" || sim_page_stale; then
  echo "dev.sh: building the simulation page for /sim/ (trunk build --public-url /sim/, incremental dev profile)" >&2
  if ! (cd "$ROOT/examples/bevy-sitl-poc" && trunk build index.html --public-url /sim/ --dist "$SIM_DIST"); then
    echo "dev.sh: could not build the simulation page; install trunk (cargo install trunk) and re-run" >&2
    exit 1
  fi
fi

STATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/surmap-dev.XXXXXX")"
export PYTHONUNBUFFERED=1

# Starts one service as its own process group: `set -m` gives the background pipeline a
# fresh group, so a stop reaches the service's children too and the terminal's Ctrl-C
# reaches only this script, which then stops the groups in order. Groups and pids live in
# shell variables (PGID_<name>, PID_<name>), read with builtins only: a forked helper could
# itself be killed by the terminal's Ctrl-C half-way through.
start_service() {
  local name="$1" cmd="$2"
  set -m
  { bash -c "$cmd" </dev/null; echo $? >"$STATE_DIR/$name.tmp" && mv "$STATE_DIR/$name.tmp" "$STATE_DIR/$name.status"; } 2>&1 \
    | awk -v prefix="[$name] " '{ print prefix $0; fflush() }' &
  eval "PID_$name=\$!"
  set +m
  jobs -p %+ >"$STATE_DIR/$name.pgid"
  read -r "PGID_$name" <"$STATE_DIR/$name.pgid"
}

# The groups still running, as a list of service names.
alive_services() {
  local name pgid alive=""
  for name in $SERVICES; do
    eval "pgid=\${PGID_$name:-}"
    [ -n "$pgid" ] && kill -0 -- "-$pgid" 2>/dev/null && alive="$alive $name"
  done
  echo "$alive"
}

signal_services() {
  local signal="$1" name pgid
  shift
  for name in "$@"; do
    eval "pgid=\${PGID_$name:-}"
    [ -n "$pgid" ] && kill "-$signal" -- "-$pgid" 2>/dev/null
  done
}

STOPPING=0
stop_all() {
  [ "$STOPPING" = 1 ] && return
  STOPPING=1
  trap '' INT TERM HUP
  local waited=0 alive
  # shellcheck disable=SC2086
  signal_services TERM $SERVICES
  while alive="$(alive_services)"; [ -n "$alive" ]; do
    if [ "$waited" -ge $((STOP_TIMEOUT * 10)) ]; then
      echo "dev.sh: still running after ${STOP_TIMEOUT}s, killing:$alive" >&2
      # shellcheck disable=SC2086
      signal_services KILL $alive
      break
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  wait 2>/dev/null
  rm -rf "$STATE_DIR"
}

# A signal only records itself; the main loop stops the services once every group is known.
SIGNAL_NAME=""
SIGNAL_STATUS=0
trap 'SIGNAL_NAME=interrupted SIGNAL_STATUS=130' INT
trap 'SIGNAL_NAME=terminated SIGNAL_STATUS=143' TERM
trap 'SIGNAL_NAME=hangup SIGNAL_STATUS=129' HUP
trap stop_all EXIT

for name in $SERVICES; do
  eval "cmd=\$CMD_$name"
  start_service "$name" "$cmd"
done
echo "dev.sh: cm5 :$CM5_PORT · station :$STATION_PORT · agent http://127.0.0.1:8780 · chat at the [chat] Local: URL — Ctrl-C stops all" >&2

# Waits for a signal or the first service to end; the short sleep keeps signals responsive.
while :; do
  if [ -n "$SIGNAL_NAME" ]; then
    echo "dev.sh: $SIGNAL_NAME, stopping services" >&2
    stop_all
    exit "$SIGNAL_STATUS"
  fi
  for name in $SERVICES; do
    eval "pid=\$PID_$name"
    if [ -f "$STATE_DIR/$name.status" ] || ! kill -0 "$pid" 2>/dev/null; then
      status=1
      [ -f "$STATE_DIR/$name.status" ] && read -r status <"$STATE_DIR/$name.status"
      echo "dev.sh: $name exited with status $status, stopping services" >&2
      stop_all
      exit "$status"
    fi
  done
  sleep 0.5
done
