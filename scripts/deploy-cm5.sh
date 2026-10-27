#!/usr/bin/env bash
# Deploy the CM5 survey server over SSH and restart its systemd service.
#
# Usage: scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [--model PROFILE] [--coral-cpu]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@cm5.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         survey port (default 8080)
#   ssh-port     SSH port (default 22)
#   --model      detector model profile for the Coral detections stream
#                (efficientdet-lite0 | ssd-mobilenet-v2 | ssdlite-mobiledet;
#                omit for no detector). The model artifacts are fetched
#                locally by scripts/fetch_coral_model.py and rsynced with
#                the source; the server uses the Edge-TPU artifact.
#   --coral-cpu  with --model, run the model's CPU twin instead of the
#                Edge-TPU artifact (targets without a Coral board)
set -eu

SOURCE_DIR="${1:-}"
SSH_TARGET="${2:-}"
if [ -z "$SOURCE_DIR" ] || [ -z "$SSH_TARGET" ]; then
    echo "usage: $0 <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [--model PROFILE] [--coral-cpu]" >&2
    exit 2
fi
REMOTE_DIR="${3:-/opt/surmap}"
PORT="${4:-8080}"
SSH_PORT="${5:-22}"
shift $(( $# < 5 ? $# : 5 ))

MODEL=""
CORAL_CPU=0
while [ $# -gt 0 ]; do
    case "$1" in
        --model)
            MODEL="${2:-}"
            if [ -z "$MODEL" ]; then
                echo "deploy: --model requires a profile name" >&2
                exit 2
            fi
            shift 2
            ;;
        --model=*)
            MODEL="${1#--model=}"
            shift
            ;;
        --coral-cpu)
            CORAL_CPU=1
            shift
            ;;
        *)
            echo "deploy: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

SERVER_ARGS=""
if [ -n "$MODEL" ]; then
    case "$MODEL" in
        efficientdet-lite0|ssd-mobilenet-v2|ssdlite-mobiledet) ;;
        *)
            echo "deploy: unknown model profile: $MODEL" >&2
            echo "deploy: choose efficientdet-lite0, ssd-mobilenet-v2, or ssdlite-mobiledet" >&2
            exit 2
            ;;
    esac
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    echo "deploy: fetching Coral model artifacts (profile $MODEL)"
    python3 "$SCRIPT_DIR/fetch_coral_model.py" --output "$SOURCE_DIR/tests/fixtures/coral_model"
    SERVER_ARGS="--detector coral --coral-model $MODEL --coral-model-dir $REMOTE_DIR/tests/fixtures/coral_model"
    if [ "$CORAL_CPU" -eq 0 ]; then
        SERVER_ARGS="$SERVER_ARGS --coral-edgetpu"
    fi
fi

cd "$(dirname "$0")"
# shellcheck source=deploy-lib.sh
. ./deploy-lib.sh
deploy_component surmap-cm5 surmap.survey.cm5_main \
    "$SOURCE_DIR" "$SSH_TARGET" "$REMOTE_DIR" "$PORT" "$SSH_PORT" "$SERVER_ARGS"
