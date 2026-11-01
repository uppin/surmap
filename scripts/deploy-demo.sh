#!/usr/bin/env bash
# Deploy the demo page over SSH and restart its systemd service.
#
# Usage: scripts/deploy-demo.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@station.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         demo HTTP port (default 8765)
#   ssh-port     SSH port (default 22)
#
# The demo talks to the deployed survey servers; each host's reported
# capabilities decide which panes the page shows.
#   --cm5-host HOST:PORT       CM5 survey server (default 10.88.77.14:8080,
#                              the Radxa CM5)
#   --station-host HOST:PORT   station SAM server (default 127.0.0.1:8081)
set -eu

SOURCE_DIR="${1:-}"
SSH_TARGET="${2:-}"
if [ -z "$SOURCE_DIR" ] || [ -z "$SSH_TARGET" ]; then
    echo "usage: $0 <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]" >&2
    exit 2
fi
REMOTE_DIR="${3:-/opt/surmap}"
PORT="${4:-8765}"
SSH_PORT="${5:-22}"
shift $(( $# < 5 ? $# : 5 ))

CM5_HOST="10.88.77.14:8080"
STATION_HOST="127.0.0.1:8081"
while [ $# -gt 0 ]; do
    case "$1" in
        --cm5-host)
            CM5_HOST="${2:-}"
            if [ -z "$CM5_HOST" ]; then
                echo "deploy: --cm5-host requires HOST:PORT" >&2
                exit 2
            fi
            shift 2
            ;;
        --cm5-host=*)
            CM5_HOST="${1#--cm5-host=}"
            shift
            ;;
        --station-host)
            STATION_HOST="${2:-}"
            if [ -z "$STATION_HOST" ]; then
                echo "deploy: --station-host requires HOST:PORT" >&2
                exit 2
            fi
            shift 2
            ;;
        --station-host=*)
            STATION_HOST="${1#--station-host=}"
            shift
            ;;
        *)
            echo "deploy: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

SERVER_ARGS="--cm5-host $CM5_HOST --station-host $STATION_HOST"

cd "$(dirname "$0")"
# shellcheck source=deploy-lib.sh
. ./deploy-lib.sh
deploy_component surmap-demo scripts.demo \
    "$SOURCE_DIR" "$SSH_TARGET" "$REMOTE_DIR" "$PORT" "$SSH_PORT" "$SERVER_ARGS" ""
