"""The station's fleet log store: the applied commands of each linked page's session, kept in
the scenario store's SQLite file and exported as the renderer's `--fleet-log`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from surmap.simulation.fleet.commands import SetActive, Stamped
from surmap.simulation.fleet.link import SimHello
from surmap.simulation.fleet.log_store import FleetLogStore, UnknownSession
from tests.fleet_fakes import (
    EARTHQUAKE_FLEET_DRONES,
    QUAKE_FLEET,
    THE_SHARED_LAUNCH,
    a_fleet_store,
    a_hello,
)

SCENARIO = QUAKE_FLEET
SW_D1 = "nest-sw-d1"
NE_D1 = "nest-ne-d1"
FIXTURES = Path(__file__).parent / "fixtures"


# ---- the log store ----------------------------------------------------------------------------


def test_a_stored_session_exports_as_the_fleet_log_file_the_renderer_reads(
    tmp_path: Path,
) -> None:
    # Given a session that applied a launch as entry 1 and a set_active as entry 3
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    session = store.start_session(SCENARIO, a_hello())
    store.record(session, Stamped(1, 2.0, THE_SHARED_LAUNCH))
    store.record(session, Stamped(3, 12.5, SetActive(SW_D1)))

    # When it is exported
    exported = store.export_jsonl(session)

    # Then the export is the shared station-export fixture, line for line
    assert exported == (FIXTURES / "fleet_link" / "session.fleet.jsonl").read_text(encoding="utf-8")


def test_entries_come_back_in_simulation_time_order(tmp_path: Path) -> None:
    # Given entries recorded out of time order
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    session = store.start_session(SCENARIO, a_hello())
    store.record(session, Stamped(2, 5.0, SetActive(NE_D1)))
    store.record(session, Stamped(1, 2.0, SetActive(SW_D1)))

    # When the session's entries are read
    entries = store.entries(session)

    # Then they are in simulation-time order
    assert [entry.seq for entry in entries] == [1, 2]


def test_each_linked_page_is_its_own_session(tmp_path: Path) -> None:
    # Given two sessions of the scenario, the first with one entry
    store = FleetLogStore(tmp_path / "simulation.sqlite")
    first = store.start_session(SCENARIO, a_hello())
    store.record(first, Stamped(1, 2.0, SetActive(NE_D1)))
    second = store.start_session(SCENARIO, SimHello(SCENARIO, 30.0, EARTHQUAKE_FLEET_DRONES))

    # When the scenario's sessions are listed
    sessions = store.sessions(SCENARIO)

    # Then both are listed oldest first with their hellos, and the second has no entries
    assert [(s.session_id, s.hello.sim_t_s) for s in sessions] == [(first, 0.0), (second, 30.0)]
    assert store.entries(second) == ()


def test_an_unknown_session_has_no_entries(tmp_path: Path) -> None:
    # Given an empty log store
    store = FleetLogStore(tmp_path / "simulation.sqlite")

    # When an unknown session is read, then it is refused
    with pytest.raises(UnknownSession):
        store.entries(999)


def test_the_fleet_tables_live_in_the_scenario_file_beside_its_scenarios(tmp_path: Path) -> None:
    # Given a scenario store holding a scenario
    scenarios = a_fleet_store(tmp_path)

    # When a fleet session is kept in the same file
    FleetLogStore(scenarios.db_path).start_session(SCENARIO, a_hello())

    # Then the file has the fleet tables, and the scenario is still there
    with sqlite3.connect(scenarios.db_path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"fleet_sessions", "fleet_log"} <= tables
    assert scenarios.scenario(SCENARIO).id == SCENARIO
