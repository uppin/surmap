"""Mac Docker SITL launcher contract. No Docker daemon is touched."""

from pathlib import Path

import pytest

from surmap.simulation.mac_sitl import (
    MIN_FREE_BYTES,
    HostProbe,
    MacSitlError,
    build_plan,
    validate_host,
)

_ROOT = Path(__file__).resolve().parent.parent
_GIB = 1024**3


def a_mac_host(
    arch: str = "arm64",
    docker: bool = True,
    free_bytes: int = 64 * _GIB,
) -> HostProbe:
    return HostProbe(
        arch=arch,
        docker=docker,
        free_bytes=free_bytes,
        repo_root=Path("/repo/surmap"),
        capture_dir=Path("/tmp/sitl-runs/disaster-mac"),
    )


def test_the_launcher_rejects_a_host_without_docker() -> None:
    # Given a Mac with no Docker on PATH
    host = a_mac_host(docker=False)

    # When the host is validated
    with pytest.raises(MacSitlError, match="Docker"):
        validate_host(host)


def test_the_launcher_rejects_a_non_arm64_host() -> None:
    # Given an Intel Mac, where the ARM64 PX4/Gazebo build does not apply
    host = a_mac_host(arch="x86_64")

    # When the host is validated
    with pytest.raises(MacSitlError, match="arm64"):
        validate_host(host)


def test_the_launcher_rejects_a_host_without_room_for_the_simulator_build() -> None:
    # Given less free disk than the PX4 + Gazebo build needs
    host = a_mac_host(free_bytes=MIN_FREE_BYTES - 1)

    # When the host is validated
    with pytest.raises(MacSitlError, match="free disk"):
        validate_host(host)


def test_the_plan_builds_the_image_then_starts_the_vnc_container() -> None:
    # Given a valid Mac host
    host = a_mac_host()

    # When the launch plan is built
    plan = build_plan(host)

    # Then the image builds first, and the container publishes VNC and
    # mounts the repo and the capture directory
    assert plan[0][:3] == ("docker", "build", "-t")
    run = next(step for step in plan if step[:2] == ("docker", "run"))
    assert "5901:5901" in run
    assert "/repo/surmap:/workspace/surmap" in run
    assert "/tmp/sitl-runs/disaster-mac:/captures/disaster-mac" in run


def test_the_plan_never_publishes_a_flight_command() -> None:
    # Given a launch plan for a passive survey payload
    plan = build_plan(a_mac_host())

    # Then no step publishes to PX4: no topic pub, no offboard, no mission upload
    joined = " ".join(" ".join(step) for step in plan)
    assert "topic pub" not in joined
    assert "offboard" not in joined.lower()
    assert "mission upload" not in joined.lower()


def test_the_container_definition_installs_the_whole_sitl_stack() -> None:
    # Given the Mac SITL container definition in the repo
    dockerfile = (_ROOT / "deploy/mac-sitl/Dockerfile").read_text(encoding="utf-8")

    # Then it carries Gazebo Harmonic, ROS 2 Jazzy, PX4, and a VNC server
    # on Ubuntu 24.04, so the WSL runbook commands work unchanged inside
    assert "ubuntu:24.04" in dockerfile
    assert "gz-sim8" in dockerfile
    assert "ros-jazzy" in dockerfile
    assert "PX4-Autopilot" in dockerfile
    assert "tigervnc" in dockerfile.lower()


def test_the_mac_launcher_script_is_executable_and_parses() -> None:
    # Given the operator-facing Mac launcher
    import subprocess

    script = _ROOT / "scripts/launch_mac_sitl.sh"

    # Then it exists, is executable, and parses as bash
    assert script.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")
    assert "launch_disaster_sitl.sh" not in text  # the WSL script stays untouched
    assert "docker" in text
