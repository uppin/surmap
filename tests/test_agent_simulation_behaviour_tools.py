"""The behaviour-tree tools over a real store (no model, no server)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.agent.tools.simulation_handlers import simulation_tool_handlers
from surmap.simulation.scenario_manifest import load_presets
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_fakes import POC_ASSETS, person_ids

WANDER = {"node": "wander", "id": "mill-about", "radius_m": 6.0, "speed_m_s": 0.8, "seed": 7}
VEER = {"node": "set_wind", "from_deg": 300.0, "speed_m_s": 10.0, "gust_m_s": 3.0, "over_s": 30.0}


def tools_on_the_wildfire_edge(tmp_path: Path) -> tuple[dict[str, object], str]:
    store = ScenarioStore(tmp_path / "s.sqlite", tmp_path / "library", load_presets(POC_ASSETS))
    handlers: dict[str, object] = dict(simulation_tool_handlers(store, {}))
    return handlers, store.create_scenario("Edge", "wildfire-edge").id


async def call(handlers: dict[str, object], rpc: str, request: object) -> object:
    handler = handlers[rpc]
    assert callable(handler)
    response: object = await handler(request, None)
    return response


async def scenario_call(
    handlers: dict[str, object], rpc: str, request: object
) -> pb.ScenarioResponse:
    response = await call(handlers, rpc, request)
    assert isinstance(response, pb.ScenarioResponse)
    return response


async def tree_of(
    handlers: dict[str, object], scenario_id: str, target: str
) -> pb.BehaviourResponse:
    response = await call(
        handlers, "GetBehaviour", pb.GetBehaviourRequest(scenario_id=scenario_id, target_id=target)
    )
    assert isinstance(response, pb.BehaviourResponse)
    return response


async def a_person(handlers: dict[str, object], scenario_id: str) -> pb.ScenarioResponse:
    return await scenario_call(
        handlers,
        "AddElement",
        pb.AddElementRequest(
            scenario_id=scenario_id,
            person=pb.PersonElement(
                id="evacuee-1",
                position=pb.EnuPoint(east=10.0, north=60.0),
                coat="coat_orange",
                skin="skin",
            ),
        ),
    )


async def test_a_person_is_given_a_tree_the_agent_can_read_back(tmp_path: Path) -> None:
    # Given the wildfire edge with a person in it
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)
    await a_person(tools, scenario_id)

    # When the agent sets the person's tree and reads it back
    set_ = await scenario_call(
        tools,
        "SetBehaviour",
        pb.SetBehaviourRequest(
            scenario_id=scenario_id, target_id="evacuee-1", tree_json=json.dumps(WANDER)
        ),
    )
    read = await tree_of(tools, scenario_id, "evacuee-1")

    # Then the tree is the one set, at the version that set it
    assert json.loads(read.tree_json) == WANDER
    assert read.version == set_.scenario.version


async def test_a_person_added_through_the_tool_keeps_its_skin(tmp_path: Path) -> None:
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)

    added = await a_person(tools, scenario_id)

    manifest = json.loads(added.scenario.manifest_json)
    assert "evacuee-1" in person_ids(manifest)
    assert [e["skin"] for e in manifest["elements"] if e["id"] == "evacuee-1"] == ["skin"]


async def test_the_wind_is_driven_by_its_own_tree(tmp_path: Path) -> None:
    # Given the wildfire edge (it has weather)
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)

    # When the wind is given a tree that veers it
    await scenario_call(
        tools,
        "SetBehaviour",
        pb.SetBehaviourRequest(
            scenario_id=scenario_id, target_id="wind", tree_json=json.dumps(VEER)
        ),
    )

    # Then the wind's tree reads back
    assert json.loads((await tree_of(tools, scenario_id, "wind")).tree_json) == VEER


async def test_one_node_is_replaced_by_its_id(tmp_path: Path) -> None:
    # Given a person who wanders
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)
    await a_person(tools, scenario_id)
    tree = {"node": "sequence", "children": [{"node": "idle", "s": 5.0}, WANDER]}
    await scenario_call(
        tools,
        "SetBehaviour",
        pb.SetBehaviourRequest(
            scenario_id=scenario_id, target_id="evacuee-1", tree_json=json.dumps(tree)
        ),
    )
    wider = {**WANDER, "radius_m": 12.0}

    # When the agent widens the wander
    await scenario_call(
        tools,
        "UpdateBehaviourNode",
        pb.UpdateBehaviourNodeRequest(
            scenario_id=scenario_id,
            target_id="evacuee-1",
            node_id="mill-about",
            node_json=json.dumps(wider),
        ),
    )

    # Then only that node changed
    read = await tree_of(tools, scenario_id, "evacuee-1")
    assert json.loads(read.tree_json) == {
        "node": "sequence",
        "children": [{"node": "idle", "s": 5.0}, wider],
    }


async def test_a_target_without_a_tree_reads_back_empty(tmp_path: Path) -> None:
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)
    await a_person(tools, scenario_id)

    assert (await tree_of(tools, scenario_id, "evacuee-1")).tree_json == ""


@pytest.mark.parametrize(
    ("target", "tree_json"),
    [
        ("evacuee-1", json.dumps({"node": "teleport"})),
        ("evacuee-1", json.dumps(VEER)),
        ("nobody", json.dumps(WANDER)),
        ("evacuee-1", "{not json"),
        ("evacuee-1", "[1, 2]"),
    ],
)
async def test_a_tree_that_cannot_run_is_invalid(
    tmp_path: Path, target: str, tree_json: str
) -> None:
    tools, scenario_id = tools_on_the_wildfire_edge(tmp_path)
    await a_person(tools, scenario_id)

    with pytest.raises(ConnectError) as raised:
        await scenario_call(
            tools,
            "SetBehaviour",
            pb.SetBehaviourRequest(scenario_id=scenario_id, target_id=target, tree_json=tree_json),
        )
    assert raised.value.code == Code.INVALID_ARGUMENT
