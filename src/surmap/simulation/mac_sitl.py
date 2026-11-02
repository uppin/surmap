"""Mac (Apple Silicon) Docker SITL launcher plan.

The simulator stack (Gazebo Harmonic, PX4 SITL, ROS 2 Jazzy) runs in an
Ubuntu 24.04 ARM64 container; this module only validates the host and
emits the Docker commands. It never publishes a flight command: PX4 is
flown from its own console inside the container, and SurMap only dumps
and scores the capture afterwards.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_FREE_BYTES = 20 * 1024**3
IMAGE = "surmap/mac-sitl:latest"
CONTAINER = "surmap-mac-sitl"
VNC_PORT = 5901


class MacSitlError(RuntimeError):
    """The Mac host cannot run the Docker SITL stack as configured."""


@dataclass(frozen=True)
class HostProbe:
    """Facts about the host the launcher was asked to run on."""

    arch: str
    docker: bool
    free_bytes: int
    repo_root: Path
    capture_dir: Path


def validate_host(host: HostProbe) -> None:
    """Reject hosts the ARM64 container build cannot serve, by name."""
    if not host.docker:
        raise MacSitlError("Docker is not on PATH. Start Rancher Desktop or Docker Desktop first.")
    if host.arch != "arm64":
        raise MacSitlError(f"expected an arm64 (Apple Silicon) host, got {host.arch}")
    if host.free_bytes < MIN_FREE_BYTES:
        raise MacSitlError(
            f"not enough free disk for the PX4 + Gazebo build: "
            f"{host.free_bytes / 1024**3:.1f} GiB free, need {MIN_FREE_BYTES / 1024**3:.0f} GiB"
        )


def build_plan(host: HostProbe) -> tuple[tuple[str, ...], ...]:
    """Docker steps: build the image, then run the VNC simulator container."""
    dockerfile = host.repo_root / "deploy/mac-sitl/Dockerfile"
    context = host.repo_root / "deploy/mac-sitl"
    return (
        ("docker", "build", "-t", IMAGE, "-f", str(dockerfile), str(context)),
        (
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-p",
            f"{VNC_PORT}:{VNC_PORT}",
            "-v",
            f"{host.repo_root}:/workspace/surmap",
            "-v",
            f"{host.capture_dir}:/captures/{host.capture_dir.name}",
            IMAGE,
        ),
    )


def probe_host(repo_root: Path, capture_dir: Path) -> HostProbe:
    """Read the real host facts the validator checks."""
    return HostProbe(
        arch=platform.machine(),
        docker=shutil.which("docker") is not None,
        free_bytes=shutil.disk_usage(repo_root).free,
        repo_root=repo_root,
        capture_dir=capture_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=Path.home() / "sitl-runs/disaster-mac")
    parser.add_argument("--plan-only", action="store_true", help="print the Docker steps, run none")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]
    host = probe_host(repo_root, args.capture.expanduser())
    try:
        validate_host(host)
    except MacSitlError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for step in build_plan(host):
        print("+ " + " ".join(step))
        if not args.plan_only:
            subprocess.run(step, check=True)
    if not args.plan_only:
        print(f"Gazebo GUI: vnc://127.0.0.1:{VNC_PORT} (password: surmap-vnc)")
        print(f"PX4 console: docker exec -it {CONTAINER} tmux attach -t px4")
        print("Then type at the pxh> prompt: commander takeoff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
