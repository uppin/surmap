"""GLB files of object geometry, published under `surmap-glb://<run_id>/<object_id>.glb`."""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["GeometryStore"]

_GLB_URI = re.compile(r"surmap-glb://([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)\.glb")
_SAFE_KEY = re.compile(r"[A-Za-z0-9_-]+")


class GeometryStore:
    """GLB files of object geometry, one per `(run_id, object_id)`, under one directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def uri(self, run_id: str, object_id: str) -> str:
        """The URI the object's GLB is published at, whether or not it is written yet."""
        _checked_key(run_id, object_id)
        return f"surmap-glb://{run_id}/{object_id}.glb"

    def has(self, run_id: str, object_id: str) -> bool:
        """Whether the object's GLB is already written."""
        return self._path(run_id, object_id).is_file()

    def put(self, run_id: str, object_id: str, glb: bytes) -> str:
        """Store the object's GLB, replacing any earlier one, and return its URI."""
        path = self._path(run_id, object_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f"{path.name}.tmp"
        temporary.write_bytes(glb)
        temporary.replace(path)
        return self.uri(run_id, object_id)

    def read(self, uri: str) -> bytes | None:
        """The GLB a URI from `uri`/`put` names, or None when nothing is stored there."""
        match = _GLB_URI.fullmatch(uri)
        if match is None:
            return None
        path = self._path(match.group(1), match.group(2))
        return path.read_bytes() if path.is_file() else None

    def _path(self, run_id: str, object_id: str) -> Path:
        _checked_key(run_id, object_id)
        return self._root / run_id / f"{object_id}.glb"


def _checked_key(run_id: str, object_id: str) -> None:
    """Refuses any run or object id that could name a path outside the store."""
    if not (_SAFE_KEY.fullmatch(run_id) and _SAFE_KEY.fullmatch(object_id)):
        raise ValueError(f"not a geometry key: {run_id!r}, {object_id!r}")
