"""Persisted demo runs: every streamed run stored in SQLite for replay.

A run is the frame timeline exactly as shown (JPEG, overlay points,
camera), the detections per frame, a map snapshot per map update, and
each surface assignment (the points a frame added to a SAM object's
surface). `snapshot_at` joins them at one moment: the frame at that
position plus the newest map snapshot at or before its frame and every
surface point assigned by then — so rewinding shows the points and
surfaces as they were then, not the final cloud.

A run's *journal* is what a replay needs to run the segmentation again
without RTAB-Map or SAM (`surmap.demo.replay`): every streamed event in
order (render-only images stripped), the rig regions are answered with,
and RTAB-Map's dense buffer — each SAM frame's disparity as the sidecar
computed it (`surmap.slam.dense`). A replay is itself a run; its source
names the run whose dense buffer it reads.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

from surmap.slam.dense import DenseFrame
from surmap.types import Pose, Vec3

PointList = list[list[float]]

# Server-rendered images a replay draws again; never journalled.
RENDER_ONLY = ("cloud_png",)

# Journal rows read per query while streaming a replay.
JOURNAL_PAGE = 64


def _journalled(kind: str, data: dict[str, object]) -> dict[str, object]:
    """What the journal keeps of an event: no render-only images, and a
    region's points only as their count (the dense buffer reproduces them)."""
    kept = {key: value for key, value in data.items() if key not in RENDER_ONLY}
    regions = kept.get("regions")
    if kind == "region" and isinstance(regions, list):
        kept["regions"] = [
            {
                **{key: value for key, value in region.items() if key != "points"},
                "point_count": len(region.get("points") or []),
            }
            for region in regions
            if isinstance(region, dict)
        ]
    return kept


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
CREATE TABLE IF NOT EXISTS surface_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    surface_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    moving INTEGER NOT NULL,
    points TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_rigs (
    run_id TEXT PRIMARY KEY,
    rig TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dense_frames (
    run_id TEXT NOT NULL,
    frame_id INTEGER NOT NULL,
    channel INTEGER NOT NULL,
    t_ns INTEGER NOT NULL,
    to_map TEXT NOT NULL,
    disparity_png BLOB NOT NULL,
    PRIMARY KEY (run_id, frame_id, channel)
);
CREATE TABLE IF NOT EXISTS run_sources (
    run_id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events (run_id, id);
CREATE INDEX IF NOT EXISTS frames_run_frame ON frames (run_id, frame_id);
CREATE INDEX IF NOT EXISTS surface_points_run_frame ON surface_points (run_id, frame_id, id);
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

    def record_surface(
        self,
        run_id: str,
        *,
        frame_id: int,
        surface_id: int,
        label: str,
        track_id: int,
        points: PointList,
        moving: bool,
    ) -> None:
        """The points `frame_id` newly assigned to `surface_id`, and whether the
        surface was moving by then (append-only)."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO surface_points"
                " (run_id, frame_id, surface_id, label, track_id, moving, points)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, frame_id, surface_id, label, track_id, int(moving), json.dumps(points)),
            )

    def record_surface_event(self, run_id: str, data: dict[str, object]) -> None:
        """Every assignment of one streamed `surface` event."""
        surfaces = data.get("surfaces")
        for surface in surfaces if isinstance(surfaces, list) else []:
            self.record_surface(
                run_id,
                frame_id=int(str(data["frame_id"])),
                surface_id=int(surface["surface_id"]),
                label=str(surface["label"]),
                track_id=int(surface["track_id"]),
                points=list(surface["points"]),
                moving=bool(surface.get("moving")),
            )

    def surfaces_at(self, run_id: str, frame_id: int) -> list[dict[str, object]]:
        """Every surface with all points assigned to it at or before `frame_id`;
        `moving` as it was by then (once moving, a surface stays moving)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT surface_id, label, moving, points FROM surface_points"
                " WHERE run_id = ? AND frame_id <= ? ORDER BY id",
                (run_id, frame_id),
            ).fetchall()
        surfaces: dict[int, dict[str, object]] = {}
        for row in rows:
            surface = surfaces.setdefault(
                int(row["surface_id"]),
                {
                    "surface_id": int(row["surface_id"]),
                    "label": str(row["label"]),
                    "moving": False,
                    "points": [],
                },
            )
            surface["moving"] = surface["moving"] or bool(row["moving"])
            cast(PointList, surface["points"]).extend(json.loads(str(row["points"])))
        return [surfaces[surface_id] for surface_id in sorted(surfaces)]

    def record_event(self, run_id: str, kind: str, data: dict[str, object]) -> None:
        """Append one streamed event to the run's journal."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events (run_id, kind, data) VALUES (?, ?, ?)",
                (run_id, kind, json.dumps(_journalled(kind, data))),
            )

    def journal(self, run_id: str) -> list[tuple[str, dict[str, object]]]:
        """The run's journalled events as (kind, data), in recorded order."""
        return list(self.journal_events(run_id))

    def journal_events(self, run_id: str) -> Iterator[tuple[str, dict[str, object]]]:
        """The run's journal, streamed in recorded order, a page of rows at a time.

        A long run's journal is hundreds of MB of map clouds: a replay
        starts on its first rows instead of decoding all of them first,
        and the store stays free for writes between pages.
        """
        after = 0
        while True:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id, kind, data FROM events WHERE run_id = ? AND id > ?"
                    " ORDER BY id LIMIT ?",
                    (run_id, after, JOURNAL_PAGE),
                ).fetchall()
            if not rows:
                return
            for row in rows:
                yield str(row["kind"]), cast(dict[str, object], json.loads(row["data"]))
            after = int(rows[-1]["id"])

    def sam_at(self, run_id: str, frame_id: int) -> dict[str, object] | None:
        """The newest journalled SAM result at or before `frame_id`, with its frame's image."""
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM events WHERE run_id = ? AND kind = 'sam'"
                " AND json_extract(data, '$.frame_id') <= ? ORDER BY id DESC LIMIT 1",
                (run_id, frame_id),
            ).fetchone()
        if row is None:
            return None
        sam = cast(dict[str, object], json.loads(row["data"]))
        jpeg = self.frame_jpeg(run_id, int(str(sam["frame_id"])))
        return {**sam, "image_b64": base64.b64encode(jpeg).decode() if jpeg else ""}

    def frame_jpeg(self, run_id: str, frame_id: int) -> bytes | None:
        with self._lock:
            row = self._db.execute(
                "SELECT jpeg FROM frames WHERE run_id = ? AND frame_id = ? ORDER BY seq LIMIT 1",
                (run_id, frame_id),
            ).fetchone()
        return bytes(row["jpeg"]) if row is not None else None

    def record_rig(self, run_id: str, rig: dict[str, object]) -> None:
        """How the run's regions were answered (rig message and display size)."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO run_rigs VALUES (?, ?)", (run_id, json.dumps(rig))
            )

    def rig(self, run_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT rig FROM run_rigs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return cast(dict[str, object], json.loads(row["rig"])) if row is not None else None

    def record_dense(self, run_id: str, frame: DenseFrame) -> None:
        """One frame's journalled dense buffer (RTAB-Map's disparity, as computed)."""
        position = frame.to_map.position
        to_map = [position.x, position.y, position.z, *frame.to_map.orientation_xyzw]
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO dense_frames VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    frame.frame_id,
                    frame.channel,
                    frame.t_ns,
                    json.dumps(to_map),
                    frame.disparity_png,
                ),
            )

    def dense_frames(self, run_id: str) -> list[DenseFrame]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM dense_frames WHERE run_id = ? ORDER BY frame_id, channel",
                (run_id,),
            ).fetchall()
        frames: list[DenseFrame] = []
        for row in rows:
            x, y, z, qx, qy, qz, qw = (float(v) for v in json.loads(row["to_map"]))
            frames.append(
                DenseFrame(
                    int(row["frame_id"]),
                    int(row["t_ns"]),
                    int(row["channel"]),
                    Pose(Vec3(x, y, z), (qx, qy, qz, qw)),
                    bytes(row["disparity_png"]),
                )
            )
        return frames

    def record_source(self, run_id: str, source_run_id: str) -> None:
        """`run_id` replays `source_run_id`'s journal."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO run_sources VALUES (?, ?)", (run_id, source_run_id)
            )

    def source_run(self, run_id: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT source_run_id FROM run_sources WHERE run_id = ?", (run_id,)
            ).fetchone()
        return str(row["source_run_id"]) if row is not None else None

    def root_run(self, run_id: str) -> str:
        """The recorded (non-replay) run at the end of `run_id`'s replay lineage."""
        seen = {run_id}
        while (source := self.source_run(run_id)) is not None and source not in seen:
            seen.add(source)
            run_id = source
        return run_id

    def latest_recording(self, dataset_id: str) -> str | None:
        """The scene's newest complete, journalled recording (never a replay), if any.

        This is the run the console reruns by default.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT run_id FROM runs WHERE dataset_id = ? AND status = 'completed'"
                " AND run_id NOT IN (SELECT run_id FROM run_sources)"
                " AND EXISTS (SELECT 1 FROM events WHERE events.run_id = runs.run_id)"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (dataset_id,),
            ).fetchone()
        return str(row["run_id"]) if row is not None else None

    def _journalled(self, run_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM events WHERE run_id = ? LIMIT 1", (run_id,)
            ).fetchone()
        return row is not None

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
            "replayable": self._journalled(run_id),
            "replay_of": self.source_run(run_id),
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
            "surfaces": self.surfaces_at(run_id, frame_id),
            "sam": self.sam_at(run_id, frame_id),
            "frame_count": self._frame_count(run_id),
        }
