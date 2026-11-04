"""What every simulation tool handler shares: the tooling bundle, blocking-call mapping and the
scenario edit/response helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeVar

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.proto import simulation_tools_pb2 as pb
from surmap.simulation.asset_sources import AssetHit, AssetSource, AssetSourceError
from surmap.simulation.manifest_checks import ScenarioInvalid
from surmap.simulation.scenario_store import (
    LicenceRefused,
    Scenario,
    ScenarioStore,
    UnknownRecord,
)

T = TypeVar("T")


@dataclass
class SimulationTooling:
    """What the handlers share: the store, the sources and the hits seen so far."""

    store: ScenarioStore
    sources: Mapping[str, AssetSource]
    hits: dict[str, AssetHit] = field(default_factory=dict)


async def blocking(call: Callable[[], T]) -> T:
    """Run a store/source call in a thread, mapping its failures to Connect codes."""
    try:
        return await asyncio.to_thread(call)
    except UnknownRecord as exc:
        raise ConnectError(Code.NOT_FOUND, str(exc)) from exc
    except ScenarioInvalid as exc:
        raise ConnectError(Code.INVALID_ARGUMENT, str(exc)) from exc
    except (LicenceRefused, AssetSourceError) as exc:
        raise ConnectError(Code.FAILED_PRECONDITION, str(exc)) from exc


def scenario_url(scenario_id: str) -> str:
    """Where the station's simulation page opens a scenario."""
    return f"/sim/?scenario={scenario_id}"


def scenario_info(scenario: Scenario, *, with_manifest: bool = True) -> pb.ScenarioInfo:
    return pb.ScenarioInfo(
        id=scenario.id,
        name=scenario.name,
        version=scenario.version,
        manifest_json=json.dumps(scenario.manifest) if with_manifest else "",
        credits=[c.line() for c in scenario.credits],
        url=scenario_url(scenario.id),
        updated_at=scenario.updated_at,
    )


async def edit_scenario(
    tooling: SimulationTooling, scenario_id: str, edit: Callable[[Scenario], dict[str, object]]
) -> pb.ScenarioResponse:
    def apply() -> Scenario:
        current = tooling.store.scenario(scenario_id)
        return tooling.store.save(scenario_id, edit(current))

    return pb.ScenarioResponse(scenario=scenario_info(await blocking(apply)))
