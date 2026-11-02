#!/usr/bin/env bash
# Deploy the station SAM server over SSH and restart its systemd service.
#
# Usage: scripts/deploy-station.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@station.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         survey port (default 8081)
#   ssh-port     SSH port (default 22)
#
# Deployed default: SAM 3.1 (PyTorch) on the station GPU.
#   --detector MODE        memory | sam3 | sam31-torch
#                          (default sam31-torch)
#   --sam31-model MODEL    SAM 3.1 checkpoint: HF id, local .pt, or
#                          local directory (default facebook/sam3.1;
#                          a local directory needs no HF download)
#   --sam31-device DEV     torch device (default cuda:0)
#   --sam31-label LABEL    concept prompt per frame (default object)
#   --sam3-model PATH      SAM 3.1 ONNX export (for --detector sam3)
#   --no-provision         skip installing the torch/sam3 stack into
#                          the station venv before the restart
set -eu

SOURCE_DIR="${1:-}"
SSH_TARGET="${2:-}"
if [ -z "$SOURCE_DIR" ] || [ -z "$SSH_TARGET" ]; then
    echo "usage: $0 <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]" >&2
    exit 2
fi
REMOTE_DIR="${3:-/opt/surmap}"
PORT="${4:-8081}"
SSH_PORT="${5:-22}"
shift $(( $# < 5 ? $# : 5 ))

DETECTOR="sam31-torch"
SAM31_MODEL="facebook/sam3.1"
SAM31_DEVICE="cuda:0"
SAM31_LABEL="object"
SAM3_MODEL=""
PROVISION=1
while [ $# -gt 0 ]; do
    case "$1" in
        --detector)
            DETECTOR="${2:-}"
            if [ -z "$DETECTOR" ]; then
                echo "deploy: --detector requires a mode" >&2
                exit 2
            fi
            shift 2
            ;;
        --detector=*)
            DETECTOR="${1#--detector=}"
            shift
            ;;
        --sam31-model)
            SAM31_MODEL="${2:-}"
            shift 2
            ;;
        --sam31-model=*)
            SAM31_MODEL="${1#--sam31-model=}"
            shift
            ;;
        --sam31-device)
            SAM31_DEVICE="${2:-cuda:0}"
            shift 2
            ;;
        --sam31-device=*)
            SAM31_DEVICE="${1#--sam31-device=}"
            shift
            ;;
        --sam31-label)
            SAM31_LABEL="${2:-object}"
            shift 2
            ;;
        --sam31-label=*)
            SAM31_LABEL="${1#--sam31-label=}"
            shift
            ;;
        --sam3-model)
            SAM3_MODEL="${2:-}"
            shift 2
            ;;
        --sam3-model=*)
            SAM3_MODEL="${1#--sam3-model=}"
            shift
            ;;
        --no-provision)
            PROVISION=0
            shift
            ;;
        *)
            echo "deploy: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

SERVER_ARGS=""
PRE_RESTART_CMD=""
case "$DETECTOR" in
    memory)
        SERVER_ARGS="--detector memory"
        ;;
    sam3)
        if [ -z "$SAM3_MODEL" ]; then
            echo "deploy: --detector sam3 requires --sam3-model" >&2
            exit 2
        fi
        SERVER_ARGS="--detector sam3 --sam3-model $SAM3_MODEL --sam3-device cuda"
        ;;
    sam31-torch)
        SERVER_ARGS="--detector sam31-torch --sam31-model $SAM31_MODEL --sam31-device $SAM31_DEVICE --sam31-label $SAM31_LABEL"
        if [ "$PROVISION" -eq 1 ]; then
            PRE_RESTART_CMD="bash scripts/provision_sam31.sh"
        fi
        ;;
    *)
        echo "deploy: unknown detector: $DETECTOR" >&2
        echo "deploy: choose memory, sam3, or sam31-torch" >&2
        exit 2
        ;;
esac

cd "$(dirname "$0")"
# shellcheck source=deploy-lib.sh
. ./deploy-lib.sh
deploy_component surmap-station surmap.survey.station_main \
    "$SOURCE_DIR" "$SSH_TARGET" "$REMOTE_DIR" "$PORT" "$SSH_PORT" "$SERVER_ARGS" "$PRE_RESTART_CMD"
