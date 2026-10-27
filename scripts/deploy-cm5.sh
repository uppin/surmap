#!/usr/bin/env bash
# Deploy the CM5 survey server over SSH and restart its systemd service.
#
# Usage: scripts/deploy-cm5.sh <source-dir> <ssh-target> [remote-dir] [port] [ssh-port]
#   source-dir   local path to the SurMap checkout to deploy
#   ssh-target   SSH destination, e.g. user@cm5.local
#   remote-dir   install path on the target (default /opt/surmap)
#   port         survey port (default 8080)
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
deploy_component surmap-cm5 surmap.survey.cm5_main \
    "$SOURCE_DIR" "$SSH_TARGET" "${3:-/opt/surmap}" "${4:-8080}" "${5:-22}"
