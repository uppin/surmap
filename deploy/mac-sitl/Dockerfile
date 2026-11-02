# SurMap disaster SITL for Apple Silicon Macs: Gazebo Harmonic + PX4 SITL
# + ROS 2 Jazzy in one Ubuntu 24.04 ARM64 container, GUI over VNC.
# The WSL runbook (docs/simulation/px4-sitl.md) commands run unchanged
# inside. SurMap stays passive: PX4 is flown from its own tmux console.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV RUNS_IN_DOCKER=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git gnupg lsb-release sudo tmux \
    python3 python3-pip python3-venv \
    fluxbox tigervnc-standalone-server xterm \
    && rm -rf /var/lib/apt/lists/*

# Gazebo Harmonic (gz-sim8) from the OSRF repo.
RUN curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" \
      > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update && apt-get install -y --no-install-recommends gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

# ROS 2 Jazzy from the ROS repo (bridge + message types for the dump).
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
      -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" \
      > /etc/apt/sources.list.d/ros2.list \
    && apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-ros-base ros-jazzy-ros-gz-bridge ros-jazzy-sensor-msgs \
      python3-colcon-common-extensions python3-rosdep python3-pillow \
    && rm -rf /var/lib/apt/lists/*

# PX4 SITL + its Gazebo models. Built once at image build time.
ARG PX4_REF=main
RUN git clone --depth 1 -b ${PX4_REF} https://github.com/PX4/PX4-Autopilot.git /opt/PX4-Autopilot \
    && git clone --depth 1 https://github.com/PX4/PX4-gazebo-models.git /opt/PX4-gazebo-models

# pip cannot uninstall Debian-managed packages (numpy, pluggy, ...), so
# numpy is pre-installed pip-managed and PX4's test-only requirements
# (pytest stack, not needed to build SITL) are dropped before its setup.
RUN python3 -m pip install --break-system-packages --ignore-installed numpy \
    && rm -f /opt/PX4-Autopilot/Tools/setup/test-requirements.txt \
    && cd /opt/PX4-Autopilot && bash Tools/setup/ubuntu.sh --no-nuttx \
    && git submodule update --init --recursive --depth 1

RUN cd /opt/PX4-Autopilot && make px4_sitl_default -j4

RUN useradd -m -s /bin/bash sitl && echo "sitl ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/sitl \
    && mkdir -p /workspace/surmap /captures && chown -R sitl:sitl /workspace /captures /opt/PX4-Autopilot /opt/PX4-gazebo-models

# vncpasswd lives in tigervnc-tools; late layer so the PX4 build cache holds.
RUN apt-get update && apt-get install -y --no-install-recommends tigervnc-tools \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER sitl
WORKDIR /workspace/surmap
EXPOSE 5901
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
