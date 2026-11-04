#!/usr/bin/env python3
"""V4 harness for the fleet link: a station for one browser tab, and a scripted sortie.

It serves the simulation page (`trunk build` output) and the `/sim/fleet` WebSocket on one port,
creates an earthquake-fleet scenario, prints the page URL to open in Chrome (WebGPU) and waits for
the page's `hello`. It then flies a sortie through the scenario's `FleetController`, printing each
`applied` (its log `seq` and the simulation time) and the drones' phases:

1. launch `nest-sw-d1` over two waypoints;
2. 15 s later a detour for it;
3. launch `nest-ne-d1` and make it the active drone (the stereo feed switches to its eyes);
4. recall both and wait until they are docked.

The session is then exported as a `--fleet-log` file; replaying that file natively
(`--screenshot <dir> --at <t> --fleet-log <file> --scenario <id>`) must show the drones where the
browser showed them at the same simulation time.

    cd examples/bevy-sitl-poc && trunk build index.html --release && cd ../..
    uv run python scripts/fleet_link_smoke.py --sim-dist examples/bevy-sitl-poc/dist

Needs the simulation's assets fetched (`uv run python scripts/fetch_sim_assets.py`). Waits are
wall-clock seconds, which is simulation time on a page running at 1x. Exit 0 once every command
applied and the drones docked; 1 when one was refused, timed out or the page never linked.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from surmap.agent.server.fleet_routes import fleet_websocket_route
from surmap.agent.server.sim_routes import SimulationRig, serve_simulation
from surmap.rpc.description import HttpRoute, ServerDescription
from surmap.rpc.hosts.hypercorn import HypercornHost
from surmap.rpc.http import HttpRequest, HttpResponse
from surmap.simulation.fleet.commands import (
    Detour,
    FleetCommand,
    Launch,
    Recall,
    Route,
    SetActive,
)
from surmap.simulation.fleet.controller import FleetController, FleetError
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore

REPO = Path(__file__).resolve().parents[1]
BEVY_POC = REPO / "examples" / "bevy-sitl-poc"
SW_D1 = "nest-sw-d1"
NE_D1 = "nest-ne-d1"
DETOUR_AFTER_S = 15.0
DOCK_WITHIN_S = 120.0
REPORT_EVERY_S = 2.0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--sim-dist",
        type=Path,
        default=BEVY_POC / "dist",
        help="a `trunk build` output served at /sim/ (default: examples/bevy-sitl-poc/dist)",
    )
    parser.add_argument(
        "--sim-assets",
        type=Path,
        default=BEVY_POC / "assets",
        help="the simulation's assets/ (scene, presets, pinned textures)",
    )
    parser.add_argument("--preset", default="earthquake-fleet", help="the scenario's preset")
    parser.add_argument("--host", default="127.0.0.1", help="interface to listen on")
    parser.add_argument("--port", type=int, default=8770, help="port for /sim/ and /sim/fleet")
    parser.add_argument(
        "--wait-s", type=float, default=300.0, help="how long to wait for the page's hello"
    )
    parser.add_argument(
        "--log-out",
        type=Path,
        default=Path("fleet-link-smoke.fleet.jsonl"),
        help="where the session's `--fleet-log` export is written",
    )
    return parser.parse_args(argv)


@dataclass(frozen=True)
class Step:
    """One command of the sortie, and how long to watch the drones after it applied."""

    what: str
    command: FleetCommand
    watch_s: float = 0.0


SORTIE = (
    Step(
        "launch nest-sw-d1",
        Launch(SW_D1, Route(((-20.0, 0.0, 15.0), (-20.0, 60.0, 18.0)), 6.0, "hover")),
        watch_s=DETOUR_AFTER_S,
    ),
    Step("detour nest-sw-d1", Detour(SW_D1, ((0.0, 35.0, 18.0), (5.0, 45.0, 18.0)))),
    Step(
        "launch nest-ne-d1",
        Launch(NE_D1, Route(((30.0, 90.0, 15.0), (0.0, 60.0, 20.0)), 6.0, "hover")),
    ),
    Step("make nest-ne-d1 active", SetActive(NE_D1), watch_s=10.0),
    Step("recall nest-sw-d1", Recall(SW_D1)),
    Step("recall nest-ne-d1", Recall(NE_D1)),
)


def phases(controller: FleetController) -> str:
    return (
        "  ".join(f"{drone.id}={drone.phase}" for drone in controller.drones()) or "(no telemetry)"
    )


async def watch(controller: FleetController, seconds: float) -> None:
    """Prints the drones' phases every `REPORT_EVERY_S` for `seconds`."""
    waited = 0.0
    while waited < seconds:
        step = min(REPORT_EVERY_S, seconds - waited)
        await asyncio.sleep(step)
        waited += step
        print(f"  [{waited:5.1f} s] {phases(controller)}  active={controller.active()}")


async def docked(controller: FleetController, within_s: float) -> bool:
    """Whether the two sortie drones are docked, waiting up to `within_s`."""
    waited = 0.0
    while waited <= within_s:
        reported = {drone.id: drone.phase for drone in controller.drones()}
        if reported.get(SW_D1) == "docked" and reported.get(NE_D1) == "docked":
            return True
        await asyncio.sleep(REPORT_EVERY_S)
        waited += REPORT_EVERY_S
        print(f"  [{waited:5.1f} s] {phases(controller)}")
    return False


async def fly(controller: FleetController) -> bool:
    """Sends the sortie; whether every command applied and the drones docked again."""
    for step in SORTIE:
        try:
            applied = await controller.send(step.command)
        except FleetError as error:
            print(f"{step.what}: {type(error).__name__}: {error}")
            return False
        print(f"{step.what}: applied  seq={applied.seq}  at_s={applied.at_s:.2f}")
        await watch(controller, step.watch_s)
    print("waiting for both drones to dock")
    return await docked(controller, DOCK_WITHIN_S)


async def linked(controller: FleetController, within_s: float) -> bool:
    waited = 0.0
    while not controller.linked:
        if waited >= within_s:
            return False
        await asyncio.sleep(0.5)
        waited += 0.5
    return True


def page_routes(rig: SimulationRig) -> tuple[HttpRoute[None], ...]:
    async def serve(request: HttpRequest) -> HttpResponse:
        served = serve_simulation(rig, request.path)
        return served if served is not None else HttpResponse(status=404, body=b"not found")

    return (HttpRoute("GET", "*", lambda _context: serve),)


async def run(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="fleet-link-smoke-") as workdir:
        store = ScenarioStore(
            db_path=Path(workdir) / "simulation.sqlite",
            library_dir=Path(workdir) / "library",
            presets=load_presets(args.sim_assets),
            assets_dir=args.sim_assets,
        )
        scenario = store.create_scenario("Fleet link smoke", args.preset)
        rig = SimulationRig(
            store=store, sources={}, static_assets=args.sim_assets, page_dist=args.sim_dist
        )
        description = ServerDescription[None](
            http_routes=page_routes(rig), websocket_routes=(fleet_websocket_route(rig),)
        )
        host = HypercornHost(description, None, host=args.host, port=args.port)
        ports = await host.start()
        controller = rig.fleet.controller(scenario.id)
        try:
            print(
                f"open in Chrome: http://{args.host}:{ports.public}/sim/?scenario={scenario.id}&fleet=1"
            )
            print(f"waiting up to {args.wait_s:.0f} s for the page's hello")
            if not await linked(controller, args.wait_s):
                print("no page linked")
                return 1
            print(f"linked: session {controller.session_id}; {phases(controller)}")
            ok = await fly(controller)
            session = controller.session_id
            if session is not None:
                args.log_out.write_text(rig.fleet.log_store.export_jsonl(session), encoding="utf-8")
                print(f"fleet log: {args.log_out} ({len(controller.session_log())} commands)")
            print("sortie flown" if ok else "sortie did not complete")
            return 0 if ok else 1
        finally:
            await host.stop()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
