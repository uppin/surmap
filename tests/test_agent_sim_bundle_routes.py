"""The chat page's export and import of a simulation over the agent server's HTTP routes.

`GET /sim/export/<id>.zip` downloads a scenario's bundle; `POST /sim/import` (optionally
`?into=<id>`) stores one. In memory, over a real store.
"""

from __future__ import annotations

import json
from pathlib import Path

from surmap.agent.server.access import AccessGate
from surmap.agent.server.routes import agent_http_routes
from surmap.agent.server.sim_routes import SimulationRig
from surmap.rpc.description import ServerDescription
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.rpc.http import HttpResponse
from surmap.simulation.scenario_bundle import export_bundle
from surmap.simulation.scenario_store import ScenarioStore
from tests.sim_bundle_fakes import a_scene_with_the_covered_car, a_station_store, member_names
from tests.sim_fakes import POC_ASSETS
from tests.test_agent_server_routes import FramesOfOneRun, GlbsInMemory

UI_ORIGIN = "http://localhost:5173"


def a_station(store: ScenarioStore, gate: AccessGate | None = None) -> InMemoryHost[None]:
    routes = agent_http_routes(
        FramesOfOneRun(),
        GlbsInMemory(),
        cors_origins=(UI_ORIGIN,),
        simulation=SimulationRig(store=store, sources={}, static_assets=POC_ASSETS),
        gate=gate,
    )
    return InMemoryHost(ServerDescription(http_routes=routes), None)


def header(response: HttpResponse, name: str) -> str | None:
    return {key.lower(): value for key, value in response.headers.items()}.get(name.lower())


def scenario_of(response: HttpResponse) -> dict[str, object]:
    scenario = json.loads(response.body)["scenario"]
    assert isinstance(scenario, dict)
    return scenario


async def test_a_scenario_downloads_as_a_zip_attachment(tmp_path: Path) -> None:
    # Given a station with the car park
    store = a_station_store(tmp_path)
    scene = a_scene_with_the_covered_car(store, "Car park")

    # When the chat page exports it
    response = await a_station(store).http("GET", f"/sim/export/{scene.id}.zip")

    # Then it gets the bundle as a named zip download
    assert (response.status, header(response, "content-type")) == (200, "application/zip")
    assert header(response, "content-disposition") == (
        'attachment; filename="car-park.surmap-sim.zip"'
    )
    assert "scenario.json" in member_names(response.body)


async def test_exporting_an_unknown_scenario_is_not_found(tmp_path: Path) -> None:
    # Given an empty station
    station = a_station(a_station_store(tmp_path))

    # Then exporting a scenario it lacks is 404
    assert (await station.http("GET", "/sim/export/nowhere.zip")).status == 404


async def test_a_bundle_imported_into_the_pane_s_scenario_is_its_next_version(
    tmp_path: Path,
) -> None:
    # Given the pane's car park at v2 and a bundle of a flooded street
    store = a_station_store(tmp_path)
    scene = a_scene_with_the_covered_car(store, "Car park")
    bundle = export_bundle(store, store.create_scenario("Flood", "flood-street").id)

    # When the chat page imports the bundle into the car park
    response = await a_station(store).http(
        "POST",
        "/sim/import",
        query=f"into={scene.id}",
        body=bundle,
        headers={"origin": UI_ORIGIN, "content-type": "application/zip"},
    )

    # Then the car park is at v3, answered with what the pane shows, readable from the dev origin
    assert response.status == 200
    assert {k: scenario_of(response)[k] for k in ("id", "name", "version", "url")} == {
        "id": "car-park",
        "name": "Car park",
        "version": 3,
        "url": "/sim/?scenario=car-park",
    }
    assert header(response, "access-control-allow-origin") == UI_ORIGIN
    assert store.scenario("car-park").version == 3


async def test_a_bundle_imported_without_a_target_is_a_new_scenario(tmp_path: Path) -> None:
    # Given a bundle from another station
    origin = a_station_store(tmp_path, "origin")
    bundle = export_bundle(origin, a_scene_with_the_covered_car(origin, "Car park").id)

    # When it is imported with no target
    response = await a_station(a_station_store(tmp_path, "here")).http(
        "POST", "/sim/import", body=bundle
    )

    # Then it is a new scenario at v1
    assert (response.status, scenario_of(response)["id"], scenario_of(response)["version"]) == (
        200,
        "car-park",
        1,
    )


async def test_a_file_that_is_not_a_bundle_is_a_bad_request_with_the_reason(
    tmp_path: Path,
) -> None:
    # Given a station
    station = a_station(a_station_store(tmp_path))

    # When a text file is imported
    response = await station.http("POST", "/sim/import", body=b"hello")

    # Then it is 400 and says why
    assert response.status == 400
    assert b"not a SurMap scenario bundle" in response.body


async def test_importing_into_an_unknown_scenario_is_not_found(tmp_path: Path) -> None:
    # Given a bundle
    store = a_station_store(tmp_path)
    bundle = export_bundle(store, a_scene_with_the_covered_car(store).id)

    # When it is imported into a scenario the station lacks
    response = await a_station(store).http("POST", "/sim/import", query="into=nowhere", body=bundle)

    # Then it is 404
    assert response.status == 404


async def test_import_needs_a_session_when_the_station_is_gated(tmp_path: Path) -> None:
    # Given a gated station and a bundle
    store = a_station_store(tmp_path)
    bundle = export_bundle(store, a_scene_with_the_covered_car(store).id)
    station = a_station(store, gate=AccessGate(code="open-sesame"))

    # When an import comes without a session
    response = await station.http("POST", "/sim/import", body=bundle)

    # Then it is refused and nothing is stored
    assert response.status == 401
    assert len(store.scenarios()) == 1
