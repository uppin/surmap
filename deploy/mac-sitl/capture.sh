#!/usr/bin/env bash
# Bridge the stereo cameras (and GPS when present) from Gazebo to ROS 2,
# then dump a standard SurMap capture. Run inside the container while PX4
# is flying. Passive only: this script subscribes; it never publishes.
# Usage: capture.sh [output-dir] [seconds]
set -euo pipefail

OUT="${1:-/captures/disaster-mac}"
SECONDS_TO_RECORD="${2:-15}"

# ROS setup files read unset variables; nounset resumes after sourcing.
set +u
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
set -u

LEFT_GZ="$(gz topic -l | grep 'left_camera/image' | head -n1 || true)"
RIGHT_GZ="$(gz topic -l | grep 'right_camera/image' | head -n1 || true)"
GPS_GZ="$(gz topic -l | grep -iE 'navsat|/gps' | head -n1 || true)"
if [[ -z "$LEFT_GZ" || -z "$RIGHT_GZ" ]]; then
  echo "stereo image topics not found; is PX4 running in the disaster world?" >&2
  gz topic -l >&2 || true
  exit 1
fi
echo "left:  $LEFT_GZ"
echo "right: $RIGHT_GZ"
echo "gps:   ${GPS_GZ:-none}"

BRIDGE_ARGS=(
  "$LEFT_GZ@sensor_msgs/msg/Image@gz.msgs.Image"
  "$RIGHT_GZ@sensor_msgs/msg/Image@gz.msgs.Image"
)
if [[ -n "$GPS_GZ" ]]; then
  BRIDGE_ARGS+=("$GPS_GZ@sensor_msgs/msg/NavSatFix@gz.msgs.NavSat")
fi
ros2 run ros_gz_bridge parameter_bridge "${BRIDGE_ARGS[@]}" &
BRIDGE_PID=$!
trap 'kill $BRIDGE_PID 2>/dev/null || true' EXIT
sleep 3

LEFT_ROS="$(ros2 topic list | grep 'left_camera' | head -n1)"
RIGHT_ROS="$(ros2 topic list | grep 'right_camera' | head -n1)"
GPS_ROS="$(ros2 topic list | grep -iE 'navsat|gps' | head -n1 || true)"

DUMP_ARGS=(
  --left "$LEFT_ROS" --right "$RIGHT_ROS"
  --baseline-m 0.07 --seconds "$SECONDS_TO_RECORD" --output "$OUT"
)
if [[ -n "$GPS_ROS" ]]; then
  DUMP_ARGS+=(--gps "$GPS_ROS")
fi
python3 /workspace/surmap/scripts/ros2/dump_sitl_capture.py "${DUMP_ARGS[@]}"
