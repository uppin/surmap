#!/usr/bin/env bash
# Build RTAB-Map and the surmap-rtabmap-stream tool natively on this
# machine (CM5: arm64, no Docker, no emulation).
#
# Usage: scripts/build_rtabmap_native.sh
#
# The build directory is the cache: everything lives under
# $RTABMAP_WORK (default ~/.cache/surmap-rtabmap) — the RTAB-Map
# clone and build tree, and the stream tool at
# $RTABMAP_WORK/stream-build/surmap-rtabmap-stream. When that binary
# already exists this script exits at once; nothing is copied
# anywhere else. FORCE=1 rebuilds.
#
# RTAB-Map is a system dependency (not on PyPI, not in Debian trixie):
# this script installs its build deps with apt and builds a pinned
# RTAB-Map release into /usr/local, then builds
# deploy/rtabmap-stream against it.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RTABMAP_TAG="${RTABMAP_TAG:-0.23.1}"
WORK="${RTABMAP_WORK:-$HOME/.cache/surmap-rtabmap}"
BINARY="$WORK/stream-build/surmap-rtabmap-stream"
JOBS="${JOBS:-$(nproc)}"

if [ -x "$BINARY" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "native stream binary already present (cached): $BINARY"
    exit 0
fi

echo "installing RTAB-Map build dependencies"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    git cmake g++ \
    libpcl-dev libopencv-dev libsqlite3-dev liboctomap-dev \
    libboost-all-dev libusb-1.0-0-dev libyaml-cpp-dev libjsoncpp-dev

mkdir -p "$WORK"
if [ ! -d "$WORK/rtabmap/.git" ]; then
    git clone --depth 1 --branch "$RTABMAP_TAG" https://github.com/introlab/rtabmap.git "$WORK/rtabmap"
fi

echo "building RTAB-Map $RTABMAP_TAG (jobs=$JOBS)"
cmake -S "$WORK/rtabmap" -B "$WORK/rtabmap/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_APP=OFF -DBUILD_TOOLS=OFF -DBUILD_EXAMPLES=OFF
cmake --build "$WORK/rtabmap/build" -j "$JOBS"
sudo cmake --install "$WORK/rtabmap/build"
sudo ldconfig

echo "building surmap-rtabmap-stream -> $BINARY"
cmake -S "$REPO_ROOT/deploy/rtabmap-stream" -B "$WORK/stream-build" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "$WORK/stream-build" -j "$JOBS"
echo "native stream binary ready: $BINARY"
