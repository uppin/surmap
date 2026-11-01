#!/usr/bin/env bash
# Shared deployment logic for the SurMap survey servers.
# Sourced by deploy-cm5.sh / deploy-station.sh; not run directly.
#
# deploy_component <service> <module> <source-dir> <ssh-target> \
#                  [remote-dir] [port] [ssh-port] [server-args] \
#                  [pre-restart-cmd]
#
# Sequence: rsync the source to the remote dir, install dependencies
# there, run the optional pre-restart hook (e.g. provisioning an
# optional model stack into the venv), render + install the systemd
# unit, then restart the service (always the last step) and require
# it to report active.

deploy_component() {
    service="$1"; module="$2"; source_dir="$3"; ssh_target="$4"
    remote_dir="${5:-/opt/surmap}"; port="$6"; ssh_port="${7:-22}"
    server_args="${8:-}"
    pre_restart_cmd="${9:-}"

    if [ ! -d "$source_dir" ]; then
        echo "deploy: source dir not found: $source_dir" >&2
        return 2
    fi

    echo "deploy: syncing $source_dir -> $ssh_target:$remote_dir"
    rsync -az --delete \
        -e "ssh -p $ssh_port" \
        --exclude '.git/' --exclude '.venv/' --exclude '.muse/' \
        --exclude '__pycache__/' --exclude '.pytest_cache/' \
        "$source_dir/" "$ssh_target:$remote_dir/"

    echo "deploy: installing and restarting $service on $ssh_target"
    ssh -p "$ssh_port" "$ssh_target" \
        "SERVICE='$service' MODULE='$module' REMOTE_DIR='$remote_dir' PORT='$port' SERVER_ARGS='$server_args' PRE_RESTART='$pre_restart_cmd' bash -s" <<'REMOTE'
set -eu
cd "$REMOTE_DIR"
if command -v uv >/dev/null 2>&1; then
    uv sync --no-dev
else
    python3 -m venv .venv
    .venv/bin/pip install -q .
fi
pre_restart="$PRE_RESTART"
if [ -n "$pre_restart" ]; then
    eval "$pre_restart"
fi
sudo useradd --system --home-dir "$REMOTE_DIR" --no-create-home surmap 2>/dev/null || true
sudo chown -R surmap:surmap "$REMOTE_DIR"
sed -e "s|@INSTALL_DIR@|$REMOTE_DIR|g" -e "s|@PORT@|$PORT|g" -e "s|@MODULE@|$MODULE|g" \
    -e "s|@SERVER_ARGS@|$SERVER_ARGS|g" \
    "deploy/systemd/$SERVICE.service" | sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null
sudo systemctl restart "$SERVICE"
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if systemctl is-active --quiet "$SERVICE"; then
        echo "deploy: $SERVICE is active"
        exit 0
    fi
    sleep 1
done
echo "deploy: $SERVICE did not become active" >&2
systemctl status "$SERVICE" --no-pager >&2 || true
exit 1
REMOTE
}
