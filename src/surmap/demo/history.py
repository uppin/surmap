"""Persisted demo runs: every streamed run stored in SQLite for replay.

A run is the frame timeline exactly as shown (JPEG, overlay points,
camera), the detections per frame, and a map snapshot per map update.
`snapshot_at` joins them at one moment: the frame at that position plus
the newest map snapshot at or before its frame — so rewinding shows the
points as they were then, not the final cloud.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import cast

PointList = list[list[float]]
ColourList = list[list[int]]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    title TEXT NOT NULL,
    total_frames INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS frames (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    frame_id INTEGER NOT NULL,
    t_ns INTEGER NOT NULL,
    jpeg BLOB NOT NULL,
    overlay TEXT NOT NULL,
    camera TEXT,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    points TEXT NOT NULL,
    colors TEXT NOT NULL,
    trajectory_xy TEXT NOT NULL,
    extent TEXT NOT NULL,
    cloud_points INTEGER NOT NULL,
    keyframes INTEGER NOT NULL,
    odom_state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    t_ns INTEGER NOT NULL,
    objects TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS maps_run_frame ON maps (run_id, frame_id, id);
CREATE INDEX IF NOT EXISTS detections_run_frame ON detections (run_id, frame_id, id);
"""


class RunHistoryStore:
    """Thread-safe SQLite store for demo runs (stdlib sqlite3 only)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_run(self, dataset_id: str, title: str, total_frames: int = 0) -> str:
        run_id = uuid.uuid4().hex[:16]
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, 'running', ?, NULL)",
                (run_id, dataset_id, title, total_frames, time.time()),
            )
        return run_id

    def record_frame(
        self,
        run_id: str,
        *,
        index: int,
        frame_id: int,
        t_ns: int,
        jpeg: bytes,
        overlay: Sequence[object],
        camera: dict[str, float] | None,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO frames VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    index,
                    frame_id,
                    t_ns,
                    jpeg,
                    json.dumps(list(overlay)),
                    json.dumps(camera) if camera is not None else None,
                ),
            )

    def record_map(
        self,
        run_id: str,
        *,
        frame_id: int,
        points: PointList,
        colors: ColourList,
        trajectory_xy: Sequence[object],
        extent: Sequence[object],
        cloud_points: int,
        keyframes: int,
        odom_state: str,
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO maps (run_id, frame_id, points, colors, trajectory_xy,"
                " extent, cloud_points, keyframes, odom_state)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    frame_id,
                    json.dumps(points),
                    json.dumps(colors),
                    json.dumps(list(trajectory_xy)),
                    json.dumps(list(extent)),
                    cloud_points,
                    keyframes,
                    odom_state,
                ),
            )

    def record_detections(
        self, run_id: str, *, frame_id: int, t_ns: int, objects: Sequence[object]
    ) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO detections (run_id, frame_id, t_ns, objects) VALUES (?, ?, ?, ?)",
                (run_id, frame_id, t_ns, json.dumps(list(objects))),
            )

    def finish_run(self, run_id: str, status: str = "completed") -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, time.time(), run_id),
            )

    def _run_row(self, run_id: str) -> sqlite3.Row | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return cast("sqlite3.Row | None", row)

    def _frame_count(self, run_id: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM frames WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    def _public_run(self, row: sqlite3.Row) -> dict[str, object]:
        run_id = str(row["run_id"])
        return {
            "run_id": run_id,
            "dataset_id": str(row["dataset_id"]),
            "title": str(row["title"]),
            "total_frames": int(row["total_frames"]),
            "status": str(row["status"]),
            "created_at": float(row["created_at"]),
            "finished_at": (float(row["finished_at"]) if row["finished_at"] is not None else None),
            "frame_count": self._frame_count(run_id),
        }

    def list_runs(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return [self._public_run(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, object] | None:
        row = self._run_row(run_id)
        return self._public_run(row) if row is not None else None

    def timeline(self, run_id: str) -> list[dict[str, object]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, frame_id, t_ns, overlay FROM frames WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        return [
            {
                "seq": int(row["seq"]),
                "frame_id": int(row["frame_id"]),
                "t_ns": int(row["t_ns"]),
                "point_count": len(cast(list[object], json.loads(str(row["overlay"])))),
            }
            for row in rows
        ]

    def snapshot_at(self, run_id: str, seq: int) -> dict[str, object] | None:
        """One moment of a run: its frame plus the cloud as it was then."""
        if self._run_row(run_id) is None:
            return None
        with self._lock:
            frame = self._db.execute(
                "SELECT * FROM frames WHERE run_id = ? AND seq = ?", (run_id, seq)
            ).fetchone()
            if frame is None:
                return None
            frame_id = int(frame["frame_id"])
            map_row = self._db.execute(
                "SELECT * FROM maps WHERE run_id = ? AND frame_id <= ?"
                " ORDER BY frame_id DESC, id DESC LIMIT 1",
                (run_id, frame_id),
            ).fetchone()
            det_row = self._db.execute(
                "SELECT objects FROM detections WHERE run_id = ? AND frame_id = ?"
                " ORDER BY id DESC LIMIT 1",
                (run_id, frame_id),
            ).fetchone()
        cloud: dict[str, object] | None = None
        if map_row is not None:
            cloud = {
                "frame_id": int(map_row["frame_id"]),
                "points": json.loads(str(map_row["points"])),
                "colors": json.loads(str(map_row["colors"])),
                "trajectory_xy": json.loads(str(map_row["trajectory_xy"])),
                "extent": json.loads(str(map_row["extent"])),
                "cloud_points": int(map_row["cloud_points"]),
                "keyframes": int(map_row["keyframes"]),
                "odom_state": str(map_row["odom_state"]),
            }
        return {
            "run_id": run_id,
            "seq": seq,
            "index": seq,
            "frame_id": frame_id,
            "t_ns": int(frame["t_ns"]),
            "image_b64": base64.b64encode(bytes(frame["jpeg"])).decode(),
            "overlay": json.loads(str(frame["overlay"])),
            "camera": (json.loads(str(frame["camera"])) if frame["camera"] is not None else None),
            "objects": (json.loads(str(det_row["objects"])) if det_row is not None else []),
            "cloud": cloud,
            "frame_count": self._frame_count(run_id),
        }
