"""The `FleetRegistry`: the server's `FleetController`s, one per scenario, and the page links
that attach to them."""

from __future__ import annotations

from surmap.simulation.fleet.controller import FleetController, FleetTiming, SimSocket
from surmap.simulation.fleet.link import (
    CLOSE_ALREADY_LINKED,
    CLOSE_PROTOCOL_ERROR,
    FleetLinkError,
    SimHello,
    decode_sim_message,
)
from surmap.simulation.fleet.log_store import FleetLogStore
from surmap.simulation.fleet_nests import nests_of
from surmap.simulation.scenario_store import ScenarioStore, UnknownRecord

__all__ = ["FleetRegistry"]


class FleetRegistry:
    """The server's controllers, one per scenario, built from the scenario's latest manifest on
    first use, and their sessions' log store in the scenario store's file."""

    def __init__(self, store: ScenarioStore, *, timing: FleetTiming | None = None) -> None:
        self._store = store
        self._timing = timing if timing is not None else FleetTiming()
        self._controllers: dict[str, FleetController] = {}
        self.log_store = FleetLogStore(store.db_path)

    def controller(self, scenario_id: str) -> FleetController:
        """The scenario's controller (the same one on every call)."""
        found = self._controllers.get(scenario_id)
        if found is None:
            manifest = self._store.scenario(scenario_id).manifest
            found = FleetController(
                scenario_id,
                nests_of(manifest),
                self.log_store,
                timing=self._timing,
                latest_nests=lambda: nests_of(self._store.scenario(scenario_id).manifest),
            )
            self._controllers[scenario_id] = found
        return found

    async def link(self, scenario_id: str, socket: SimSocket) -> None:
        """Runs one page's link until it closes: the first frame must be a `fleet/v1` `hello`
        (else close `CLOSE_PROTOCOL_ERROR`) naming this scenario (another is a protocol error
        too, and nothing is attached); a scenario already linked closes the newcomer with
        `CLOSE_ALREADY_LINKED`; every later frame goes to the controller (an undecodable one
        closes `CLOSE_PROTOCOL_ERROR`); the close detaches it."""
        try:
            controller = self.controller(scenario_id)
        except UnknownRecord:
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return
        hello = await self._hello_of(socket)
        if hello is None:
            return
        if hello.scenario != scenario_id:
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return
        if controller.linked:
            await socket.close(CLOSE_ALREADY_LINKED)
            return
        controller.attach(socket, hello)
        try:
            await self._pump(controller, socket)
        finally:
            controller.detach()

    @staticmethod
    async def _hello_of(socket: SimSocket) -> SimHello | None:
        first = await socket.receive_text()
        if first is None:
            return None
        try:
            opening = decode_sim_message(first)
        except FleetLinkError:
            opening = None
        if not isinstance(opening, SimHello):
            await socket.close(CLOSE_PROTOCOL_ERROR)
            return None
        return opening

    @staticmethod
    async def _pump(controller: FleetController, socket: SimSocket) -> None:
        while (text := await socket.receive_text()) is not None:
            try:
                message = decode_sim_message(text)
            except FleetLinkError:
                await socket.close(CLOSE_PROTOCOL_ERROR)
                return
            controller.receive(message)
