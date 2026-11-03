"""Acceptance: the agent builds a scenario through its tools alone, and the station serves it.

A scripted model drives a real agent turn on a real socket (`build_agent_description` on
`HypercornHost` port 0) over a real SQLite store; only the asset sources' HTTP is canned.
Afterwards the simulation page's own requests are made: the scenario manifest and the
downloaded model's files, from `/sim/assets/` on the same origin.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from surmap.simulation.asset_sources import AmbientCg, PolyHaven, Sketchfab
from surmap.simulation.scenario_manifest import load_presets, validate_manifest
from surmap.simulation.scenario_store import ScenarioStore

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.server.app import AgentServerConfig, SimulationRig, build_agent_description
from surmap.rpc.hosts.hypercorn import HypercornHost
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.agent_server_fakes import STEP_TIMEOUT_S
from tests.agent_tool_fakes import a_tool_rig
from tests.fake_ollama import a_closed_ollama_url
from tests.sim_fakes import GLB_BYTES, POC_ASSETS, RecordingFetch, element_ids

STREAM_TURN = "/surmap.agent.v1.ChatService/StreamTurn"


@dataclass(frozen=True)
class Station:
    address: str
    store: ScenarioStore

    def get(self, path: str) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection(self.address, timeout=STEP_TIMEOUT_S)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def turn(self, text: str) -> None:
        payload = chat_pb2.StreamTurnRequest(conversation_id="sim-1", text=text).SerializeToString()
        connection = http.client.HTTPConnection(self.address, timeout=STEP_TIMEOUT_S * 4)
        try:
            connection.request(
                "POST",
                STREAM_TURN,
                body=struct.pack(">BI", 0, len(payload)) + payload,
                headers={"content-type": "application/connect+proto"},
            )
            assert connection.getresponse().read()
        finally:
            connection.close()


def an_agent_building_a_wreck_scene() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(
            tool_call(
                "search_assets",
                "c1",
                query="burnt car",
                kind="ASSET_KIND_MODEL",
                sources=["sketchfab"],
            )
        ),
        calling(tool_call("download_asset", "c2", ref="sketchfab:3f1c0a")),
        calling(
            tool_call(
                "create_scenario", "c3", name="Wreck on the avenue", preset="earthquake-block"
            )
        ),
        calling(
            tool_call(
                "add_model",
                "c4",
                scenario_id="wreck-on-the-avenue",
                asset_ref="sketchfab:3f1c0a",
                position={"east": 2.0, "north": 30.0, "up": 0.0},
                yaw_deg=80.0,
                collider="COLLIDER_BOX",
                ground_truth_kind="car",
                element_id="burnt-car-1",
            )
        ),
        calling(
            tool_call(
                "add_element",
                "c5",
                scenario_id="wreck-on-the-avenue",
                person={
                    "id": "survivor-8",
                    "position": {"east": 4.0, "north": 31.0, "up": 0.0},
                    "coat": "coat_orange",
                },
            )
        ),
        calling(tool_call("get_scenario", "c6", scenario_id="wreck-on-the-avenue")),
        answer("The wreck scenario is ready at /sim/?scenario=wreck-on-the-avenue"),
    )


@asynccontextmanager
async def a_station(tmp_path: Path, model: ScriptedChatModel) -> AsyncIterator[Station]:
    fetch = RecordingFetch()
    store = ScenarioStore(
        db_path=tmp_path / "simulation.sqlite",
        library_dir=tmp_path / "library",
        presets=load_presets(POC_ASSETS),
    )
    simulation = SimulationRig(
        store=store,
        sources={
            "polyhaven": PolyHaven(fetch),
            "ambientcg": AmbientCg(fetch),
            "sketchfab": Sketchfab(fetch, token="t"),
        },
        static_assets=POC_ASSETS,
        page_dist=None,
    )
    with a_tool_rig(tmp_path) as rig:
        config = AgentServerConfig(
            port=0, model_id="ollama:scripted", model_factory=lambda _: model
        )
        description = build_agent_description(
            config,
            workspace=rig.workspace,
            geometry=rig.workspace.geometry,
            registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
            simulation=simulation,
        )
        host = HypercornHost(description, None, host="127.0.0.1", port=0)
        ports = await host.start()
        try:
            yield Station(address=f"127.0.0.1:{ports.public}", store=store)
        finally:
            await host.stop()


async def test_an_agent_turn_builds_a_scenario_the_station_serves(tmp_path: Path) -> None:
    # Given the station with an agent scripted to build a wreck scenario
    model = an_agent_building_a_wreck_scene()
    async with a_station(tmp_path, model) as station:
        # When the agent takes its turn, and the page then asks for the scenario
        await asyncio.to_thread(station.turn, "Put a burnt car on the avenue with a survivor")
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/scenarios/wreck-on-the-avenue.json"
        )

    # Then the served manifest is the latest version, valid, with the car and the survivor
    assert model.calls == 7
    assert status == 200
    manifest = json.loads(body)
    validate_manifest(manifest)
    assert "survivor-8" in element_ids(manifest)
    assert {m["id"]: m["glb"] for m in manifest["models"]}["burnt-car-1"] == (
        "library/sketchfab/3f1c0a/model.glb"
    )


async def test_the_downloaded_model_is_served_byte_identical_to_its_hash(tmp_path: Path) -> None:
    # Given the station after the agent built the wreck scenario
    async with a_station(tmp_path, an_agent_building_a_wreck_scene()) as station:
        await asyncio.to_thread(station.turn, "Put a burnt car on the avenue with a survivor")

        # When the page fetches the model the manifest names
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/library/sketchfab/3f1c0a/model.glb"
        )
        recorded = station.store.asset("sketchfab:3f1c0a").files[0].sha256

    # Then it is the downloaded GLB, matching the SHA-256 the store recorded
    assert status == 200
    assert body == GLB_BYTES
    assert hashlib.sha256(body).hexdigest() == recorded


async def test_the_scenario_credits_the_cc_by_author(tmp_path: Path) -> None:
    # Given the station after the agent built the wreck scenario
    async with a_station(tmp_path, an_agent_building_a_wreck_scene()) as station:
        await asyncio.to_thread(station.turn, "Put a burnt car on the avenue with a survivor")
        scenario = station.store.scenario("wreck-on-the-avenue")

    # Then the CC BY model's author is credited, at version 3 (created, model, survivor)
    assert [(c.title, c.author) for c in scenario.credits] == [("Burnt Car", "photoscanner")]
    assert scenario.version == 3


async def test_the_page_static_assets_are_served_beside_scenarios(tmp_path: Path) -> None:
    # Given the station
    async with a_station(tmp_path, an_agent_building_a_wreck_scene()) as station:
        # When the page asks for the camera profile every scenario names
        status, body = await asyncio.to_thread(
            station.get, "/sim/assets/cameras/elp-stereo-pinhole.camera.json"
        )
        # And for a path outside the assets
        escaped, _ = await asyncio.to_thread(station.get, "/sim/assets/../../pyproject.toml")

    # Then the profile is the PoC's, and nothing outside the assets leaks
    assert status == 200
    assert json.loads(body)["id"] == "elp-stereo-pinhole-v1"
    assert escaped == 404
