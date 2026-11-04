"""`scripts/dev.sh`: starts the local stack and takes every service down with it.

The real services are replaced by fake commands through the script's `SURMAP_DEV_*_CMD`
overrides. Each fake records its own pid and the pid of a child it spawned, so the tests can
check that a stop reaches the whole process tree, not only the process the script started.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "dev.sh"
SERVICES = ("cm5", "station", "agent", "chat")
DEADLINE_S = 15.0


@dataclass
class DevStack:
    process: subprocess.Popen[str]
    pid_dir: pathlib.Path

    def pids(self) -> list[int]:
        return [int(p.read_text()) for p in sorted(self.pid_dir.glob("*.pid"))]

    def output(self) -> str:
        out, _ = self.process.communicate(timeout=DEADLINE_S)
        return out


def record_pid(pid_dir: pathlib.Path, pid: str, name: str) -> str:
    """Shell that writes a pid file whole, so the test never reads one half-written."""
    return f"echo {pid} > {pid_dir}/{name}.tmp && mv {pid_dir}/{name}.tmp {pid_dir}/{name}.pid"


def a_long_running_service(pid_dir: pathlib.Path, name: str) -> str:
    """A service that runs until stopped, with a child process of its own."""
    return (
        f"sleep 300 & {record_pid(pid_dir, '$!', f'{name}-child')}; "
        f"{record_pid(pid_dir, '$$', name)}; echo {name} up; wait"
    )


def a_service_that_exits(pid_dir: pathlib.Path, name: str, status: int) -> str:
    return f"{record_pid(pid_dir, '$$', name)}; sleep 1; echo {name} failed; exit {status}"


def eventually(condition: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + DEADLINE_S
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting until {what}")
        time.sleep(0.05)


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); it has exited all the same.
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return state.stdout.strip() != "" and not state.stdout.strip().startswith("Z")


@pytest.fixture
def start_dev_stack(tmp_path: pathlib.Path) -> Iterator[Callable[..., DevStack]]:
    started: list[DevStack] = []

    def start(**commands: str) -> DevStack:
        env = dict(os.environ)
        for name in SERVICES:
            command = commands.get(name, a_long_running_service(tmp_path, name))
            env[f"SURMAP_DEV_{name.upper()}_CMD"] = command
        process = subprocess.Popen(
            [str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        stack = DevStack(process, tmp_path)
        started.append(stack)
        return stack

    yield start

    for stack in started:
        if stack.process.poll() is None:
            stack.process.kill()
        for pid in stack.pids():
            if is_running(pid):
                os.kill(pid, signal.SIGKILL)


def all_services_up(stack: DevStack) -> Callable[[], bool]:
    return lambda: len(stack.pids()) == 2 * len(SERVICES)


def test_interrupting_the_script_stops_every_service_and_its_children(
    start_dev_stack: Callable[..., DevStack],
) -> None:
    # Given the four services running under the script
    stack = start_dev_stack()
    eventually(all_services_up(stack), "every service and its child is running")

    # When the developer presses Ctrl-C
    stack.process.send_signal(signal.SIGINT)

    # Then the script exits as interrupted and nothing it started is left running
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert [pid for pid in stack.pids() if is_running(pid)] == []


def test_killing_the_script_stops_every_service_and_its_children(
    start_dev_stack: Callable[..., DevStack],
) -> None:
    # Given the four services running under the script
    stack = start_dev_stack()
    eventually(all_services_up(stack), "every service and its child is running")

    # When the script is killed with SIGTERM
    stack.process.terminate()

    # Then it exits as terminated and nothing it started is left running
    assert stack.process.wait(timeout=DEADLINE_S) == 143
    assert [pid for pid in stack.pids() if is_running(pid)] == []


def test_a_service_that_exits_takes_the_rest_down_with_its_status(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a station that fails a second after it starts
    stack = start_dev_stack(station=a_service_that_exits(tmp_path, "station", 3))

    # When the script notices it has gone
    status = stack.process.wait(timeout=DEADLINE_S)

    # Then it stops the other services and exits with the station's status
    assert status == 3
    assert [pid for pid in stack.pids() if is_running(pid)] == []
    assert "station exited with status 3" in stack.output()


def planned_commands(*args: str) -> dict[str, str]:
    """`dev.sh --dry-run`: each service's command, keyed by service name."""
    result = subprocess.run(
        [str(SCRIPT), "--dry-run", *args], capture_output=True, text=True, timeout=DEADLINE_S
    )
    assert result.returncode == 0, result.stderr
    lines = (line.split(": ", 1) for line in result.stdout.splitlines())
    return {name: command for name, command in lines}


def test_the_station_runs_the_in_memory_detector_by_default() -> None:
    # When the stack is planned without options
    commands = planned_commands()

    # Then the station gets no SAM detector and the agent uses the fake SAM
    assert "--detector" not in commands["station"]
    assert "--sam-fake" in commands["agent"]


def test_with_sam_runs_sam_31_on_the_mac_gpu_in_the_station() -> None:
    # When the stack is planned with real SAM
    commands = planned_commands("--with-sam")

    # Then the station serves SAM 3.1 on MPS, with torch and sam3 layered on by uv
    assert "--detector sam31-torch --sam31-device mps" in commands["station"]
    assert "--with torch" in commands["station"]
    assert "git+https://github.com/facebookresearch/sam3.git" in commands["station"]


def test_with_sam_leaves_the_project_environment_and_the_agent_alone() -> None:
    # When the stack is planned with real SAM
    commands = planned_commands("--with-sam")

    # Then the CM5 is unchanged and the agent, which has no real-SAM option yet, stays fake
    assert "--with" not in commands["cm5"]
    assert "--sam-fake" in commands["agent"]


def test_each_output_line_is_labelled_with_its_service(
    start_dev_stack: Callable[..., DevStack],
) -> None:
    # Given the four services running under the script
    stack = start_dev_stack()
    eventually(all_services_up(stack), "every service and its child is running")

    # When it is stopped
    stack.process.send_signal(signal.SIGINT)

    # Then every service's own output is prefixed with its name
    output = stack.output()
    for name in SERVICES:
        assert f"[{name}] {name} up" in output
