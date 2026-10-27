#!/usr/bin/env bash
# Deploy the station SAM server over SSH and restart its systemd service.
#
# Usage: scripts/deploy-station.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@station.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         survey port (default 8081)
#   ssh-port     SSH port (default 22)
set -eu

SOURCE_DIR="${1:-}"
SSH_TARGET="${2:-}"
if [ -z "$SOURCE_DIR" ] || [ -z "$SSH_TARGET" ]; then
    echo "usage: $0 <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]" >&2
    exit 2
fi

cd "$(dirname "$0")"
# shellcheck source=deploy-lib.sh
. ./deploy-lib.sh
deploy_component surmap-station surmap.survey.station_main \
    "$SOURCE_DIR" "$SSH_TARGET" "${3:-/opt/surmap}" "${4:-8081}" "${5:-22}"
