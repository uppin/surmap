"""Local viewer server. One replay clock, pushed as server-sent events.

`POST /ask` is the map question hook. It does not call a model.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from surmap.types import Vec3
from surmap.viewer.ask import answer_map_question
from surmap.viewer.model import SemanticMapSnapshot, Track, ViewerTick, empty_snapshot
from surmap.viewer.snapshot import read_snapshot

_PAGE = (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")


class Replay(Protocol):
    title: str
    source_name: str
    snapshot: SemanticMapSnapshot
    snapshot_path: str | None

    def ticks(self) -> Iterator[ViewerTick]: ...


class _ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    replay_factory: Callable[[], Replay]
    fps: float
    loop: bool
    stream_lock: threading.Lock


def make_viewer_server(
    replay_factory: Callable[[], Replay],
    *,
    host: str = "0.0.0.0",
    port: int = 8770,
    fps: float = 10.0,
    loop: bool = False,
) -> ThreadingHTTPServer:
    """The viewer HTTP server, not yet serving."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    server = _ViewerServer((host, port), _Handler)
    server.replay_factory = replay_factory
    server.fps = fps
    server.loop = loop
    server.stream_lock = threading.Lock()
    return server


class _Handler(BaseHTTPRequestHandler):
    server: _ViewerServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, "application/json", b'{"status": "ok"}')
            return
        if path == "/":
            self._send(200, "text/html; charset=utf-8", _PAGE.encode())
            return
        if path == "/stream":
            self._stream()
            return
        self._send(404, "text/plain", b"not found")

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/ask":
            self._send(404, "text/plain", b"not found")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            raw = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, "application/json", b'{"error": "body must be JSON"}')
            return
        if not isinstance(raw, dict):
            self._send(400, "application/json", b'{"error": "body must be an object"}')
            return
        question = raw.get("question")
        if not isinstance(question, str) or not question.strip():
            self._send(400, "application/json", b'{"error": "question must be a non-empty string"}')
            return
        snapshot, error, status = _snapshot_for_question(
            raw.get("snapshot_path"), self.server.replay_factory
        )
        if error is not None:
            self._send(status, "application/json", json.dumps({"error": error}).encode())
            return
        answer = answer_map_question(question, snapshot)
        self._send(200, "application/json", json.dumps(answer.as_json()).encode())

    def _stream(self) -> None:
        if not self.server.stream_lock.acquire(blocking=False):
            self._send(409, "text/plain", b"a viewer stream is already running")
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                replay = self.server.replay_factory()
                self._write_event("session", _session_payload(replay))
                previous = time.monotonic()
                for tick in replay.ticks():
                    elapsed = time.monotonic() - previous
                    self._write_event("tick", _tick_payload(tick))
                    remaining = 1.0 / self.server.fps - elapsed
                    if remaining > 0:
                        time.sleep(remaining)
                    previous = time.monotonic()
                if not self.server.loop:
                    break
                self._write_event("reset", {})
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.server.stream_lock.release()

    def _write_event(self, kind: str, payload: dict[str, object]) -> None:
        chunk = f"event: {kind}\ndata: {json.dumps(payload)}\n\n".encode()
        self.wfile.write(chunk)
        self.wfile.flush()


def _snapshot_for_question(
    snapshot_path: object, factory: Callable[[], Replay]
) -> tuple[SemanticMapSnapshot, str | None, int]:
    if snapshot_path is None or snapshot_path == "":
        return factory().snapshot, None, 200
    if not isinstance(snapshot_path, str):
        return empty_snapshot(), "snapshot_path must be a string", 400
    path = Path(snapshot_path)
    if not path.is_file():
        return empty_snapshot(), f"snapshot not found: {snapshot_path}", 404
    try:
        return read_snapshot(path), None, 200
    except ValueError as exc:
        return empty_snapshot(), str(exc), 400


def _session_payload(replay: Replay) -> dict[str, object]:
    origin = replay.snapshot.origin
    return {
        "title": replay.title,
        "source": replay.source_name,
        "snapshot_path": replay.snapshot_path,
        "origin": None
        if origin is None
        else {
            "t_ns": origin.t_ns,
            "lat": origin.lat,
            "lon": origin.lon,
            "alt": origin.alt,
            "accuracy_m": origin.accuracy_m,
        },
        "tracks": [_track_payload(track) for track in replay.snapshot.tracks()],
    }


def _track_payload(track: Track) -> dict[str, object]:
    mask: object
    if track.mask_points is None:
        mask = None
    else:
        mask = [_xyz(point) for point in track.mask_points]
    return {
        "id": track.id,
        "label": track.label,
        "description": track.description,
        "motion": track.motion,
        "layer": track.layer,
        "lat": track.lat,
        "lon": track.lon,
        "alt": track.alt,
        "mask_points": mask,
    }


def _tick_payload(tick: ViewerTick) -> dict[str, object]:
    return {
        "index": tick.index,
        "total": tick.total,
        "t_ns": tick.t_ns,
        "image_b64": base64.b64encode(tick.jpeg).decode("ascii"),
        "width": tick.width,
        "height": tick.height,
        "drone": _xyz(tick.drone),
        "points": [_xyz(point) for point in tick.points],
        "scene_points": tick.scene_points,
        "height_m": round(tick.height_m, 3),
        "gps_fix": tick.gps_fix,
        "pose_ok": tick.pose_ok,
        "hud": list(tick.hud),
        "overlays": [
            {
                "xyxy": [round(value, 1) for value in overlay.xyxy],
                "label": overlay.label,
                "motion": overlay.motion,
                "track_id": overlay.track_id,
                "mask": [[round(u, 1), round(v, 1)] for u, v in overlay.mask],
            }
            for overlay in tick.overlays
        ],
        "placed": [
            {
                "id": item.track.id,
                "x": round(item.xyz.x, 3),
                "y": round(item.xyz.y, 3),
                "z": round(item.xyz.z, 3),
                "visible": item.visible,
                "trail": [_xyz(point) for point in item.trail],
            }
            for item in tick.placed
        ],
    }


def _xyz(point: Vec3) -> dict[str, float]:
    return {"x": round(point.x, 3), "y": round(point.y, 3), "z": round(point.z, 3)}
