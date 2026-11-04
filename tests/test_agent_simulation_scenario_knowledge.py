"""What the agent knows of a scenario: `describe_scenario`, and edits refused on stale knowledge.

The tools remember the version of each scenario they last showed the agent. When the scenario
moved on without them — an import from the chat page — an edit is `ABORTED` until the agent
reads it again. Handler tests over a real store, no model and no server.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_contents_pb2 as contents
from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.simulation.scenario_bundle import export_bundle, import_bundle
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_bundle_fakes import a_station_store

A_SURVIVOR = pb.PersonElement(
    id="survivor-9", position=pb.EnuPoint(east=1.0, north=2.0, up=0.0), coat="coat_orange"
)


@dataclass
class Tools:
    store: ScenarioStore
    handlers: dict[str, object]

    async def call(self, rpc: str, request: object) -> object:
        handler = self.handlers[rpc]
        assert callable(handler)
        return await handler(request, None)

    async def create(self, name: str, preset: str) -> str:
        created = await self.call(
            "CreateScenario", pb.CreateScenarioRequest(name=name, preset=preset)
        )
        assert isinstance(created, pb.ScenarioResponse)
        return created.scenario.id

    async def add_survivor(self, scenario_id: str) -> pb.ScenarioResponse:
        added = await self.call(
            "AddElement", pb.AddElementRequest(scenario_id=scenario_id, person=A_SURVIVOR)
        )
        assert isinstance(added, pb.ScenarioResponse)
        return added

    async def describe(self, scenario_id: str) -> contents.DescribeScenarioResponse:
        described = await self.call(
            "DescribeScenario", contents.DescribeScenarioRequest(scenario_id=scenario_id)
        )
        assert isinstance(described, contents.DescribeScenarioResponse)
        return described


def the_tools(tmp_path: Path) -> Tools:
    store = a_station_store(tmp_path)
    return Tools(store, dict(simulation_tool_handlers(store, {})))


def imported_from_the_page(store: ScenarioStore, into: str, preset_scene: str) -> None:
    """The chat page imports a bundle of another scene into `into`, bypassing the tools."""
    other = store.create_scenario("Imported", preset_scene)
    import_bundle(store, export_bundle(store, other.id), into=into)


async def test_an_edit_after_an_import_the_agent_has_not_read_is_refused_as_stale(
    tmp_path: Path,
) -> None:
    # Given a scene the agent created at v1, then replaced from the page at v2
    tools = the_tools(tmp_path)
    scene = await tools.create("Lot", "empty-lot")
    imported_from_the_page(tools.store, scene, "flood-street")

    # When the agent edits it on what it last saw
    with pytest.raises(ConnectError) as raised:
        await tools.add_survivor(scene)

    # Then the edit is aborted, naming both versions and how to catch up, and nothing is saved
    assert raised.value.code == Code.ABORTED
    assert "v2" in raised.value.message and "v1" in raised.value.message
    assert "describe_scenario" in raised.value.message
    assert tools.store.scenario(scene).version == 2


async def test_reading_the_scenario_again_lets_the_edit_through(tmp_path: Path) -> None:
    # Given a scene replaced from the page after the agent created it
    tools = the_tools(tmp_path)
    scene = await tools.create("Lot", "empty-lot")
    imported_from_the_page(tools.store, scene, "flood-street")

    # When the agent describes it, then edits it
    await tools.describe(scene)
    edited = await tools.add_survivor(scene)

    # Then the edit lands on the imported version
    assert edited.scenario.version == 3


async def test_get_scenario_also_catches_the_agent_up(tmp_path: Path) -> None:
    # Given a scene replaced from the page after the agent created it
    tools = the_tools(tmp_path)
    scene = await tools.create("Lot", "empty-lot")
    imported_from_the_page(tools.store, scene, "flood-street")

    # When the agent reads it with get_scenario, then edits it
    await tools.call("GetScenario", pb.GetScenarioRequest(scenario_id=scene))
    edited = await tools.add_survivor(scene)

    # Then the edit lands
    assert edited.scenario.version == 3


async def test_the_agent_s_own_edits_in_a_row_are_never_stale(tmp_path: Path) -> None:
    # Given a scene the agent created
    tools = the_tools(tmp_path)
    scene = await tools.create("Lot", "empty-lot")

    # When it edits twice in a row
    await tools.add_survivor(scene)
    second = await tools.call(
        "RemoveElement", pb.RemoveElementRequest(scenario_id=scene, element_id="survivor-9")
    )

    # Then both land
    assert isinstance(second, pb.ScenarioResponse)
    assert second.scenario.version == 3


async def test_a_scenario_the_tools_never_showed_is_not_refused(tmp_path: Path) -> None:
    # Given a scene imported from the page as a new scenario
    tools = the_tools(tmp_path)
    scene = tools.store.create_scenario("Imported", "empty-lot").id

    # When the agent edits it without having read it
    edited = await tools.add_survivor(scene)

    # Then the edit lands: there is no older knowledge of it to be stale
    assert edited.scenario.version == 2


async def test_describe_lists_every_element_with_its_kind_and_position(tmp_path: Path) -> None:
    # Given the downtown blaze
    tools = the_tools(tmp_path)
    scene = await tools.create("Blaze", "downtown-blaze")

    # When the agent describes it
    described = await tools.describe(scene)

    # Then the tower, its fire and the district are among the items, with what they are
    items = {item.id: item for item in described.items}
    assert (items["tower-1"].kind, list(items["tower-1"].position_enu)) == (
        "building",
        [-10.0, 0.0, 0.0],
    )
    assert (items["blaze-1"].kind, items["blaze-1"].detail) == (
        "building_fire",
        "on tower-1, floor 3, from 5 s",
    )
    assert (items["core"].kind, items["core"].detail) == ("district", "downtown, 120 × 80 m")


async def test_describe_names_the_scenario_its_version_and_the_weather(tmp_path: Path) -> None:
    # Given the flood rescue
    tools = the_tools(tmp_path)
    scene = await tools.create("Flood", "flood-rescue")

    # When the agent describes it
    described = await tools.describe(scene)

    # Then it reads the header and the weather in one line
    assert (described.id, described.name, described.version, described.url) == (
        "flood",
        "Flood",
        1,
        "/sim/?scenario=flood",
    )
    assert described.weather == "rain 8 mm/h, fog to 250 m, wind from 250° at 2 m/s"


async def test_describe_says_which_people_and_vehicles_have_a_behaviour(tmp_path: Path) -> None:
    # Given the flood rescue, whose boats are driven
    tools = the_tools(tmp_path)
    scene = await tools.create("Flood", "flood-rescue")

    # When the agent describes it
    described = await tools.describe(scene)

    # Then the boats are vehicles with a behaviour and the stranded survivor has none
    items = {item.id: item for item in described.items}
    assert (items["rescue-boat-1"].kind, items["rescue-boat-1"].detail) == ("vehicle", "boat")
    assert items["rescue-boat-1"].has_behaviour
    assert (items["survivor-flood"].kind, items["survivor-flood"].has_behaviour) == (
        "person",
        False,
    )


async def test_describing_an_unknown_scenario_is_not_found(tmp_path: Path) -> None:
    # Given no scenarios
    tools = the_tools(tmp_path)

    # Then describing one is NOT_FOUND
    with pytest.raises(ConnectError) as raised:
        await tools.describe("nowhere")
    assert raised.value.code == Code.NOT_FOUND
