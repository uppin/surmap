"""What every simulation tool handler shares: the tooling bundle, blocking-call mapping and the
scenario edit/response helpers.

Every edit goes through `edit_scenario`, which refuses (`ABORTED`) to edit a scenario whose latest
version is not the one the tools last showed the agent — the scene moved on without it, e.g. an
import from the chat page — so the agent never edits on stale knowledge. A scenario the tools
never showed is not refused.
"""

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
    """What the handlers share: the store, the sources, the hits seen so far, and the version of
    each scenario the tools last showed the agent."""

    store: ScenarioStore
    sources: Mapping[str, AssetSource]
    hits: dict[str, AssetHit] = field(default_factory=dict)
    seen: dict[str, int] = field(default_factory=dict)

    def shown(self, scenario: Scenario) -> Scenario:
        """`scenario`, remembered as the version the agent now knows."""
        self.seen[scenario.id] = scenario.version
        return scenario


class StaleScenario(Exception):
    """An edit based on a scenario version older than its latest."""


async def blocking(call: Callable[[], T]) -> T:
    """Run a store/source call in a thread, mapping its failures to Connect codes."""
    try:
        return await asyncio.to_thread(call)
    except UnknownRecord as exc:
        raise ConnectError(Code.NOT_FOUND, str(exc)) from exc
    except StaleScenario as exc:
        raise ConnectError(Code.ABORTED, str(exc)) from exc
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
        seen = tooling.seen.get(scenario_id)
        if seen is not None and seen != current.version:
            raise StaleScenario(
                f"scenario {scenario_id!r} is at v{current.version} but you last saw "
                f"v{seen}: it changed outside your edits (e.g. imported from the chat page). "
                "Nothing was saved; call describe_scenario or get_scenario, then redo the edit "
                "on what it holds now"
            )
        return tooling.shown(tooling.store.save(scenario_id, edit(current)))

    return pb.ScenarioResponse(scenario=scenario_info(await blocking(apply)))
