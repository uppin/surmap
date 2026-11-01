#!/usr/bin/env bash
# Deploy the CM5 survey server over SSH and restart its systemd service.
#
# Usage: scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@cm5.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         survey port (default 8080)
#   ssh-port     SSH port (default 22)
#
# Deployed default: RTAB-Map (streaming) + CoralAI, and nothing else.
# Every other computation is enabled only by its option below.
#   --model PROFILE        Coral detector profile
#                          (efficientdet-lite0 | ssd-mobilenet-v2 |
#                          ssdlite-mobiledet; default efficientdet-lite0).
#                          The artifacts are fetched locally by
#                          scripts/fetch_coral_model.py and rsynced with
#                          the source; the server uses the Edge-TPU one.
#   --no-model             deploy without the Coral detector
#   --coral-cpu            run the model's CPU twin instead of Edge TPU
#   --slam MODE            SLAM backend: streaming (default) | sidecar |
#                          inmemory
#   --calibration-dir DIR  remote EuRoC calibration dir for RTAB-Map
#                          (default <remote-dir>/tests/fixtures/euroc_v101_rtabmap)
#   --rtabmap-native BIN   remote path of a natively built
#                          surmap-rtabmap-stream binary (no Docker;
#                          build: scripts/build_rtabmap_native.sh).
#                          Default: the target-side build cache at
#                          ~/.cache/surmap-rtabmap/stream-build/,
#                          built by the deploy only when missing.
#   --rtabmap-docker       use the Docker streaming image instead of
#                          the native binary
#   --object-tracking      enable Coral object tracking / object points
#   --moving-areas         enable the StreamMovingAreas computation
#   --region-points        enable the StreamRegionPoints computation
set -eu

SOURCE_DIR="${1:-}"
SSH_TARGET="${2:-}"
if [ -z "$SOURCE_DIR" ] || [ -z "$SSH_TARGET" ]; then
    echo "usage: $0 <source-dir> <ssh-target> [remote-dir] [port] [ssh-port] [options]" >&2
    exit 2
fi
REMOTE_DIR="${3:-/opt/surmap}"
PORT="${4:-8080}"
SSH_PORT="${5:-22}"
shift $(( $# < 5 ? $# : 5 ))

MODEL="efficientdet-lite0"
CORAL_CPU=0
SLAM="streaming"
CALIBRATION_DIR=""
RTABMAP_NATIVE=""
RTABMAP_DOCKER=0
EXTRA_ARGS=""
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
        --no-model)
            MODEL=""
            shift
            ;;
        --coral-cpu)
            CORAL_CPU=1
            shift
            ;;
        --slam)
            SLAM="${2:-}"
            if [ -z "$SLAM" ]; then
                echo "deploy: --slam requires a backend name" >&2
                exit 2
            fi
            shift 2
            ;;
        --slam=*)
            SLAM="${1#--slam=}"
            shift
            ;;
        --calibration-dir)
            CALIBRATION_DIR="${2:-}"
            if [ -z "$CALIBRATION_DIR" ]; then
                echo "deploy: --calibration-dir requires a path" >&2
                exit 2
            fi
            shift 2
            ;;
        --calibration-dir=*)
            CALIBRATION_DIR="${1#--calibration-dir=}"
            shift
            ;;
        --rtabmap-native)
            RTABMAP_NATIVE="${2:-}"
            if [ -z "$RTABMAP_NATIVE" ]; then
                echo "deploy: --rtabmap-native requires a binary path" >&2
                exit 2
            fi
            shift 2
            ;;
        --rtabmap-native=*)
            RTABMAP_NATIVE="${1#--rtabmap-native=}"
            shift
            ;;
        --rtabmap-docker)
            RTABMAP_DOCKER=1
            shift
            ;;
        --object-tracking)
            EXTRA_ARGS="$EXTRA_ARGS --object-tracking"
            shift
            ;;
        --moving-areas)
            EXTRA_ARGS="$EXTRA_ARGS --moving-areas"
            shift
            ;;
        --region-points)
            EXTRA_ARGS="$EXTRA_ARGS --region-points"
            shift
            ;;
        *)
            echo "deploy: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

case "$SLAM" in
    streaming|sidecar|inmemory) ;;
    *)
        echo "deploy: unknown slam backend: $SLAM" >&2
        echo "deploy: choose streaming, sidecar, or inmemory" >&2
        exit 2
        ;;
esac
if [ -z "$CALIBRATION_DIR" ]; then
    CALIBRATION_DIR="$REMOTE_DIR/tests/fixtures/euroc_v101_rtabmap"
fi
if [ -n "$MODEL" ]; then
    case "$MODEL" in
        efficientdet-lite0|ssd-mobilenet-v2|ssdlite-mobiledet) ;;
        *)
            echo "deploy: unknown model profile: $MODEL" >&2
            echo "deploy: choose efficientdet-lite0, ssd-mobilenet-v2, or ssdlite-mobiledet" >&2
            exit 2
            ;;
    esac
fi

if [ "$SLAM" = "streaming" ] && [ "$RTABMAP_DOCKER" -eq 0 ]; then
    # Cached native build: the target-side build directory is the
    # cache, and the build script exits at once when the stream
    # binary already exists there. Runs before the main sync so the
    # service never starts against a binary that is not there yet.
    echo "deploy: ensuring native RTAB-Map stream binary on $SSH_TARGET (cached)"
    REMOTE_HOME="$(ssh -p "$SSH_PORT" "$SSH_TARGET" 'echo $HOME')"
    if [ -z "$RTABMAP_NATIVE" ]; then
        RTABMAP_NATIVE="$REMOTE_HOME/.cache/surmap-rtabmap/stream-build/surmap-rtabmap-stream"
    fi
    ssh -p "$SSH_PORT" "$SSH_TARGET" \
        "mkdir -p '$REMOTE_DIR/scripts' '$REMOTE_DIR/deploy/rtabmap-stream' 2>/dev/null || sudo mkdir -p '$REMOTE_DIR/scripts' '$REMOTE_DIR/deploy/rtabmap-stream'"
    rsync -az -e "ssh -p $SSH_PORT" \
        "$SOURCE_DIR/scripts/build_rtabmap_native.sh" "$SSH_TARGET:$REMOTE_DIR/scripts/"
    rsync -az -e "ssh -p $SSH_PORT" \
        "$SOURCE_DIR/deploy/rtabmap-stream/" "$SSH_TARGET:$REMOTE_DIR/deploy/rtabmap-stream/"
    ssh -p "$SSH_PORT" "$SSH_TARGET" \
        "RTABMAP_WORK='$REMOTE_HOME/.cache/surmap-rtabmap' '$REMOTE_DIR/scripts/build_rtabmap_native.sh'"
fi

SERVER_ARGS="--slam-backend $SLAM"
if [ "$SLAM" != "inmemory" ]; then
    SERVER_ARGS="$SERVER_ARGS --calibration-dir $CALIBRATION_DIR"
fi
if [ -n "$RTABMAP_NATIVE" ]; then
    SERVER_ARGS="$SERVER_ARGS --rtabmap-native $RTABMAP_NATIVE"
fi
SERVER_ARGS="$SERVER_ARGS$EXTRA_ARGS"
if [ -n "$MODEL" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    echo "deploy: fetching Coral model artifacts (profile $MODEL)"
    python3 "$SCRIPT_DIR/fetch_coral_model.py" --output "$SOURCE_DIR/tests/fixtures/coral_model"
    SERVER_ARGS="$SERVER_ARGS --detector coral --coral-model $MODEL --coral-model-dir $REMOTE_DIR/tests/fixtures/coral_model"
    if [ "$CORAL_CPU" -eq 0 ]; then
        SERVER_ARGS="$SERVER_ARGS --coral-edgetpu"
    fi
fi

cd "$(dirname "$0")"
# shellcheck source=deploy-lib.sh
. ./deploy-lib.sh
deploy_component surmap-cm5 surmap.survey.cm5_main \
    "$SOURCE_DIR" "$SSH_TARGET" "$REMOTE_DIR" "$PORT" "$SSH_PORT" "$SERVER_ARGS"
