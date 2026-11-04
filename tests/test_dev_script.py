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


def a_ready_sim_page(directory: pathlib.Path) -> pathlib.Path:
    """A sim page build whose page already addresses its assets under `/sim/`."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text('<script type="module" src="/sim/bevy-fake.js"></script>')
    return directory


@pytest.fixture
def start_dev_stack(tmp_path: pathlib.Path) -> Iterator[Callable[..., DevStack]]:
    started: list[DevStack] = []

    def start(
        env: dict[str, str] | None = None, args: tuple[str, ...] = (), **commands: str
    ) -> DevStack:
        env = dict(os.environ) | (env or {})
        env.setdefault("SURMAP_DEV_SIM_DIST", str(a_ready_sim_page(tmp_path / "sim-dist")))
        env.setdefault("SURMAP_DEV_SIM_FETCH_CMD", f"echo ok > {tmp_path}/sim-fetch.txt")
        env.setdefault("SURMAP_DEV_RTABMAP_INIT_CMD", f"echo ok > {tmp_path}/rtabmap-init.txt")
        for name in SERVICES:
            command = commands.get(name, a_long_running_service(tmp_path, name))
            env[f"SURMAP_DEV_{name.upper()}_CMD"] = command
        process = subprocess.Popen(
            [str(SCRIPT), *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
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


def planned_commands(*args: str, env: dict[str, str] | None = None) -> dict[str, str]:
    """`dev.sh --dry-run`: each service's command, keyed by service name."""
    result = subprocess.run(
        [str(SCRIPT), "--dry-run", *args],
        env=dict(os.environ) | (env or {}),
        capture_output=True,
        text=True,
        timeout=DEADLINE_S,
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


def test_the_agent_serves_the_simulation_page_by_default(tmp_path: pathlib.Path) -> None:
    # Given a sim page location chosen for the stack
    sim_dist = tmp_path / "sim-dist"

    # When the stack is planned without options
    commands = planned_commands(env={"SURMAP_DEV_SIM_DIST": str(sim_dist)})

    # Then the agent serves that page, so `/sim/?scenario=…` opens on its origin
    assert f"--sim-dist {sim_dist}" in commands["agent"]


def test_the_stereo_bridge_is_off_by_default() -> None:
    # When the stack is planned without options
    commands = planned_commands()

    # Then the agent serves no bridge and the chat is told of none
    assert "--bevy-bridge-port" not in commands["agent"]
    assert "VITE_SURMAP_BRIDGE_URL" not in commands["chat"]


def test_with_bridge_the_agent_serves_the_stereo_bridge_and_the_chat_links_its_preview() -> None:
    # When the stack is planned with the bridge
    commands = planned_commands("--bridge")

    # Then the agent serves the bridge on its default port and the chat's preview streams there
    assert "--bevy-bridge-port 8790" in commands["agent"]
    assert "VITE_SURMAP_BRIDGE_URL=ws://127.0.0.1:8790" in commands["chat"]


def test_the_bridge_port_can_be_chosen() -> None:
    # When the stack is planned with the bridge on another port
    commands = planned_commands("--bridge", env={"SURMAP_DEV_BRIDGE_PORT": "9911"})

    # Then the agent and the chat agree on it
    assert "--bevy-bridge-port 9911" in commands["agent"]
    assert "VITE_SURMAP_BRIDGE_URL=ws://127.0.0.1:9911" in commands["chat"]


def a_stub_trunk(bin_dir: pathlib.Path, record: pathlib.Path) -> pathlib.Path:
    """A fake `trunk` on PATH: records its arguments and writes a `/sim/` page."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    trunk = bin_dir / "trunk"
    trunk.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"record = pathlib.Path({str(record)!r})\n"
        "record.parent.mkdir(parents=True, exist_ok=True)\n"
        "with record.open('a') as stream:\n"
        "    stream.write(' '.join(sys.argv[1:]) + '\\n')\n"
        "args = sys.argv[1:]\n"
        "dist = pathlib.Path(args[args.index('--dist') + 1])\n"
        "dist.mkdir(parents=True, exist_ok=True)\n"
        "(dist / 'index.html').write_text('<script src=\"/sim/bevy-stub.js\"></script>')\n"
    )
    trunk.chmod(0o755)
    return bin_dir


def env_with_stub_trunk(tmp_path: pathlib.Path, sim_dist: pathlib.Path) -> dict[str, str]:
    bin_dir = a_stub_trunk(tmp_path / "bin", tmp_path / "trunk.args")
    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SURMAP_DEV_SIM_DIST": str(sim_dist),
    }


def test_a_missing_sim_page_is_built_for_the_sim_prefix_before_starting(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given no sim page build at the stack's sim page location
    sim_dist = tmp_path / "missing-sim-dist"

    # When the stack starts
    stack = start_dev_stack(env=env_with_stub_trunk(tmp_path, sim_dist))
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then trunk built the page for `/sim/` before the services came up
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert "--public-url /sim/" in (tmp_path / "trunk.args").read_text()
    assert "/sim/" in (sim_dist / "index.html").read_text()


def test_a_sim_page_built_for_the_root_is_rebuilt_for_the_sim_prefix(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a sim page build that addresses its WASM from the server root
    sim_dist = tmp_path / "root-sim-dist"
    sim_dist.mkdir()
    (sim_dist / "index.html").write_text('<script src="/bevy-root.js"></script>')

    # When the stack starts
    stack = start_dev_stack(env=env_with_stub_trunk(tmp_path, sim_dist))
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then the page was rebuilt, because under `/sim/` those root URLs 404
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert "--public-url /sim/" in (tmp_path / "trunk.args").read_text()


def test_a_sim_page_already_built_for_the_sim_prefix_is_not_rebuilt(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a sim page build that already addresses its assets under `/sim/`
    sim_dist = a_ready_sim_page(tmp_path / "ready-sim-dist")

    # When the stack starts
    stack = start_dev_stack(env=env_with_stub_trunk(tmp_path, sim_dist))
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then trunk never ran: the build is left alone
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert not (tmp_path / "trunk.args").exists()


def test_a_sim_page_that_cannot_be_built_stops_the_stack_before_any_service_starts(
    tmp_path: pathlib.Path,
) -> None:
    # Given no sim page build, assets already fetched, and no trunk anywhere on PATH
    env = dict(os.environ)
    env["PATH"] = "/usr/bin:/bin"
    env["SURMAP_DEV_SIM_FETCH_CMD"] = "true"
    env["SURMAP_DEV_SIM_DIST"] = str(tmp_path / "missing-sim-dist")
    for name in SERVICES:
        env[f"SURMAP_DEV_{name.upper()}_CMD"] = a_long_running_service(tmp_path, name)

    # When the stack is started
    result = subprocess.run(
        [str(SCRIPT)], env=env, capture_output=True, text=True, timeout=DEADLINE_S
    )

    # Then it refuses to start, names the missing prerequisite, and starts nothing
    assert result.returncode != 0
    assert "trunk" in result.stdout + result.stderr
    assert list(tmp_path.glob("*.pid")) == []


def test_the_pinned_sim_assets_are_fetched_before_the_stack_starts(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a stack whose asset fetch is stubbed to leave a record
    stack = start_dev_stack()

    # When the services come up
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then the pinned textures/models were fetched before anything started
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert (tmp_path / "sim-fetch.txt").read_text().strip() == "ok"


def test_a_failed_asset_fetch_stops_the_stack_before_any_service_starts(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given an asset fetch that fails (no network, a dead pin, …)
    stack = start_dev_stack(env={"SURMAP_DEV_SIM_FETCH_CMD": "false"})

    # When the script gives up before starting anything
    status = stack.process.wait(timeout=DEADLINE_S)

    # Then it exits non-zero and no service was started
    assert status != 0
    assert stack.pids() == []
    assert "fetch" in stack.output()


def test_with_bridge_the_rtabmap_image_is_prepared_before_the_stack_starts(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a bridge stack whose RTAB-Map image preparation is stubbed to leave a record
    stack = start_dev_stack(args=("--bridge",))

    # When the services come up
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then the streaming RTAB-Map image was made ready before anything started
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert (tmp_path / "rtabmap-init.txt").read_text().strip() == "ok"


def test_without_bridge_the_rtabmap_image_is_left_alone(
    tmp_path: pathlib.Path, start_dev_stack: Callable[..., DevStack]
) -> None:
    # Given a stack started without the bridge
    stack = start_dev_stack()

    # When the services come up
    eventually(all_services_up(stack), "every service and its child is running")
    stack.process.send_signal(signal.SIGINT)

    # Then no RTAB-Map image was prepared
    assert stack.process.wait(timeout=DEADLINE_S) == 130
    assert not (tmp_path / "rtabmap-init.txt").exists()


def test_a_failed_rtabmap_image_preparation_stops_the_stack_before_any_service_starts(
    start_dev_stack: Callable[..., DevStack],
) -> None:
    # Given a bridge stack whose RTAB-Map image cannot be prepared (no Docker, a failed build)
    stack = start_dev_stack(env={"SURMAP_DEV_RTABMAP_INIT_CMD": "false"}, args=("--bridge",))

    # When the script gives up before starting anything
    status = stack.process.wait(timeout=DEADLINE_S)

    # Then it exits non-zero, names RTAB-Map, and no service was started
    assert status != 0
    assert stack.pids() == []
    assert "RTAB-Map" in stack.output()


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
