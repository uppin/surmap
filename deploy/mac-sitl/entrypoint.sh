#!/usr/bin/env bash
# Start VNC, then PX4 SITL in the disaster world inside tmux session "px4".
# Operator flies from the PX4 console: docker exec -it surmap-mac-sitl tmux attach -t px4
# This script sends no flight command; takeoff is typed at the pxh> prompt.
set -euo pipefail

export DISPLAY=:1
mkdir -p "$HOME/.vnc"
# Password auth (TigerVNC refuses unauthenticated non-localhost serving).
# Local-only demo credential, published on the host loopback by Docker.
printf '%s' "${VNC_PASSWORD:-surmap-vnc}" | vncpasswd -f > "$HOME/.vnc/passwd"
chmod 600 "$HOME/.vnc/passwd"
tigervncserver :1 -geometry 1600x1000 -depth 24 -localhost no -xstartup fluxbox &
sleep 2

ROOT=/workspace/surmap
PX4_ROOT=/opt/PX4-Autopilot
ln -sfn "$ROOT/docs/simulation/gz/x500_surmap_stereo" "$PX4_ROOT/Tools/simulation/gz/models/x500_surmap_stereo"
ln -sfn "$ROOT/docs/simulation/gz/worlds/disaster_block.sdf" "$PX4_ROOT/Tools/simulation/gz/worlds/disaster_block.sdf"
ln -sfn "$ROOT/docs/simulation/gz/worlds/disaster_block_materials" "$PX4_ROOT/Tools/simulation/gz/worlds/disaster_block_materials"
export GZ_SIM_RESOURCE_PATH="$ROOT/docs/simulation/gz:$ROOT/docs/simulation/gz/worlds:/opt/PX4-gazebo-models/models"

# PX4 only starts models that have a matching airframe file
# (NNNN_gz_<model>). Derive one for the SurMap stereo model from the
# stock gz x500 airframe, in PX4's own tree (never in SurMap's repo).
AIRFRAMES="$PX4_ROOT/build/px4_sitl_default/etc/init.d-posix/airframes"
if [[ ! -f "$AIRFRAMES/4022_gz_x500_surmap_stereo" ]]; then
  sed -e 's/@name Gazebo x500/@name Gazebo x500 SurMap stereo/' \
      -e 's/PX4_SIM_MODEL:=x500/PX4_SIM_MODEL:=x500_surmap_stereo/' \
      "$AIRFRAMES/4001_gz_x500" > "$AIRFRAMES/4022_gz_x500_surmap_stereo"
fi

# Run the built px4 binary directly: the generated `make px4_sitl gz_*`
# targets only exist for PX4's own airframes and force PX4_SIM_MODEL to
# the stock model, ignoring the SurMap stereo airframe.
tmux new-session -d -s px4 \
  "cd $PX4_ROOT/build/px4_sitl_default/src/modules/simulation/gz_bridge && PX4_GZ_WORLD=disaster_block PX4_SIM_MODEL=gz_x500_surmap_stereo GZ_IP=127.0.0.1 $PX4_ROOT/build/px4_sitl_default/bin/px4 -i 0 2>&1 | tee /tmp/px4.log; bash"

echo "VNC on :5901, PX4 starting in tmux session 'px4' (log: /tmp/px4.log)"
touch /tmp/px4.log
exec tail -F /tmp/px4.log
