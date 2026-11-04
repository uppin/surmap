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

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from surmap.simulation.fleet.commands import Stamped, command_json, parse_command
from surmap.simulation.fleet.link import SimHello, decode_sim_message, encode_sim_message

__all__ = ["FleetLogStore", "FleetSession", "UnknownSession"]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS fleet_sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    hello       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fleet_log (
    session_id   INTEGER NOT NULL REFERENCES fleet_sessions(session_id),
    seq          INTEGER NOT NULL,
    at_s         REAL NOT NULL,
    command_json TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""


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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._db_path, timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                db.executescript(_SCHEMA)
                yield db
        finally:
            db.close()

    def start_session(self, scenario_id: str, hello: SimHello) -> int:
        """A new session for `scenario_id`, opened by `hello`; its id."""
        started_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO fleet_sessions (scenario_id, started_at, hello) VALUES (?, ?, ?)",
                (scenario_id, started_at, encode_sim_message(hello)),
            )
        session_id = cursor.lastrowid
        if session_id is None:
            raise RuntimeError("SQLite gave no id for the new fleet session")
        return session_id

    def record(self, session_id: int, entry: Stamped) -> None:
        """Keeps `entry`, an applied command of `session_id`."""
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO fleet_log (session_id, seq, at_s, command_json) "
                "VALUES (?, ?, ?, ?)",
                (session_id, entry.seq, entry.at_s, json.dumps(command_json(entry.command))),
            )

    def sessions(self, scenario_id: str) -> tuple[FleetSession, ...]:
        """The scenario's sessions, oldest first."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT session_id, scenario_id, started_at, hello FROM fleet_sessions "
                "WHERE scenario_id = ? ORDER BY session_id",
                (scenario_id,),
            ).fetchall()
        return tuple(FleetSession(row[0], row[1], row[2], _hello(row[3])) for row in rows)

    def entries(self, session_id: int) -> tuple[Stamped, ...]:
        """The session's applied commands, in `at_s` order (ties by `seq`); `UnknownSession`
        when there is no such session."""
        with self._connect() as db:
            known = db.execute(
                "SELECT 1 FROM fleet_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if known is None:
                raise UnknownSession(f"no fleet session {session_id}")
            rows = db.execute(
                "SELECT seq, at_s, command_json FROM fleet_log WHERE session_id = ? "
                "ORDER BY at_s, seq",
                (session_id,),
            ).fetchall()
        return tuple(Stamped(row[0], row[1], parse_command(json.loads(row[2]))) for row in rows)

    def export_jsonl(self, session_id: int) -> str:
        """The session as a `--fleet-log` file's text, one line per entry, newline-terminated."""
        return "".join(
            json.dumps(
                {"seq": entry.seq, "at_s": entry.at_s, "command": command_json(entry.command)}
            )
            + "\n"
            for entry in self.entries(session_id)
        )


def _hello(frame: str) -> SimHello:
    message = decode_sim_message(frame)
    if not isinstance(message, SimHello):
        raise ValueError("a stored fleet session's hello is not a hello")
    return message
