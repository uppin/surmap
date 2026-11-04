"""The applied fleet commands of every linked session, kept beside the scenarios.

Two tables in the scenario store's SQLite file, created on first use (existing rows untouched):

- `fleet_sessions(session_id, scenario_id, started_at, hello)` — one row per linked page;
- `fleet_log(session_id, seq, at_s, command_json)` — the `applied` answers, as the page stamped
  them.

`export_jsonl` writes a session as the renderer's `--fleet-log` file (n2): one
`{"seq": …, "at_s": …, "command": {…}}` line per entry (`json.dumps` default separators), in
`at_s` order, ties by `seq`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from surmap.simulation.fleet.commands import Stamped
from surmap.simulation.fleet.link import SimHello

__all__ = ["FleetLogStore", "FleetSession", "UnknownSession"]


class UnknownSession(LookupError):
    """No session of that id."""


@dataclass(frozen=True)
class FleetSession:
    """One linked page: when it linked and what its `hello` said."""

    session_id: int
    scenario_id: str
    started_at: str
    hello: SimHello


class FleetLogStore:
    """Fleet sessions and their applied commands in the SQLite file at `db_path`."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def start_session(self, scenario_id: str, hello: SimHello) -> int:
        """A new session for `scenario_id`, opened by `hello`; its id."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def record(self, session_id: int, entry: Stamped) -> None:
        """Keeps `entry`, an applied command of `session_id`."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def sessions(self, scenario_id: str) -> tuple[FleetSession, ...]:
        """The scenario's sessions, oldest first."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def entries(self, session_id: int) -> tuple[Stamped, ...]:
        """The session's applied commands, in `at_s` order (ties by `seq`); `UnknownSession`
        when there is no such session."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")

    def export_jsonl(self, session_id: int) -> str:
        """The session as a `--fleet-log` file's text, one line per entry, newline-terminated."""
        # TODO(pr-3): implement
        raise NotImplementedError("pr-3: implement")
