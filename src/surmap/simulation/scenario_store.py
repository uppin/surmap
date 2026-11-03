"""The station's simulation store: an SQLite catalogue, a hashed asset library, versioned scenarios.

Downloads land under `<library>/<source>/<asset id>/` and are recorded with their SHA-256, so the
station serves exactly what it fetched; nothing downloaded is committed. Every scenario edit is
a new version (`scenario_versions`); `scenarios/<id>.json` serves the latest. Only assets whose
licence passes `check_licence` are fetched at all. One connection per call — the agent server's
tool handlers run on worker threads — with WAL so readers never block the writer.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from surmap.simulation.asset_sources import AssetHit, AssetKind, AssetSource
from surmap.simulation.licences import check_licence
from surmap.simulation.scenario_manifest import Manifest, ScenarioInvalid, validate_manifest

_SCHEMA = (
    """CREATE TABLE assets (
        ref TEXT PRIMARY KEY, source TEXT NOT NULL, asset_id TEXT NOT NULL, kind TEXT NOT NULL,
        title TEXT NOT NULL, author TEXT NOT NULL, licence TEXT NOT NULL, page_url TEXT NOT NULL,
        entry TEXT NOT NULL, downloaded_at TEXT NOT NULL)""",
    """CREATE TABLE asset_files (
        ref TEXT NOT NULL REFERENCES assets(ref), path TEXT NOT NULL, sha256 TEXT NOT NULL,
        bytes INTEGER NOT NULL, url TEXT NOT NULL, PRIMARY KEY (ref, path))""",
    """CREATE TABLE scenarios (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
        updated_at TEXT NOT NULL)""",
    """CREATE TABLE scenario_versions (
        scenario_id TEXT NOT NULL REFERENCES scenarios(id), version INTEGER NOT NULL,
        manifest TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (scenario_id, version))""",
)
SCHEMA_VERSION = 1


class LicenceRefused(ValueError):
    """An asset whose licence keeps it out of scenarios."""


class UnknownRecord(LookupError):
    """No such asset or scenario."""


@dataclass(frozen=True)
class StoredFile:
    path: str
    """Relative to the simulation's assets: `library/<source>/<id>/<file>`."""
    sha256: str
    bytes: int


@dataclass(frozen=True)
class StoredAsset:
    ref: str
    source: str
    asset_id: str
    kind: AssetKind
    title: str
    author: str
    licence: str
    page_url: str
    entry: str
    files: tuple[StoredFile, ...]


@dataclass(frozen=True)
class Credit:
    ref: str
    title: str
    author: str
    licence: str
    page_url: str

    def line(self) -> str:
        return f"{self.title} by {self.author} ({self.licence}), {self.page_url}"


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    version: int
    manifest: Manifest
    credits: tuple[Credit, ...]
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "scenario"


def _kind(value: object) -> AssetKind:
    if value == "model":
        return "model"
    if value == "texture":
        return "texture"
    if value == "hdri":
        return "hdri"
    raise ValueError(f"unknown asset kind {value!r}")


class ScenarioStore:
    def __init__(
        self,
        db_path: Path,
        library_dir: Path,
        presets: Mapping[str, Manifest],
    ) -> None:
        self._db_path = Path(db_path)
        self._library = Path(library_dir)
        self._presets = dict(presets)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._library.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
                for statement in _SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @property
    def library_dir(self) -> Path:
        return self._library

    @property
    def presets(self) -> list[str]:
        return sorted(self._presets)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self._db_path, timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    # --- assets ---------------------------------------------------------------------------

    def download(self, source: AssetSource, hit: AssetHit) -> StoredAsset:
        """Fetch an accepted hit's files into the library and catalogue them."""
        verdict = check_licence(hit.licence)
        if not verdict.accepted:
            raise LicenceRefused(verdict.reason)
        files = source.files(hit.asset_id, hit.kind)
        folder = self._library / hit.source / hit.asset_id
        folder.mkdir(parents=True, exist_ok=True)
        archives: dict[str, bytes] = {}
        stored: list[StoredFile] = []
        rows: list[tuple[str, str, int, str]] = []
        for file in files:
            if file.member is not None:
                if file.url not in archives:
                    archives[file.url] = source.fetch_file(file.url)
                with zipfile.ZipFile(io.BytesIO(archives[file.url])) as archive:
                    data = archive.read(file.member)
            else:
                data = source.fetch_file(file.url)
            target = folder / file.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            path = f"library/{hit.source}/{hit.asset_id}/{file.path}"
            digest = hashlib.sha256(data).hexdigest()
            stored.append(StoredFile(path=path, sha256=digest, bytes=len(data)))
            rows.append((path, digest, len(data), file.url))
        entry = stored[0].path
        with self._connect() as db:
            db.execute("DELETE FROM asset_files WHERE ref = ?", (hit.ref,))
            db.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    hit.ref,
                    hit.source,
                    hit.asset_id,
                    hit.kind,
                    hit.title,
                    hit.author,
                    hit.licence,
                    hit.page_url,
                    entry,
                    _now(),
                ),
            )
            db.executemany(
                "INSERT INTO asset_files VALUES (?, ?, ?, ?, ?)",
                [(hit.ref, *row) for row in rows],
            )
        return self.asset(hit.ref)

    def asset(self, ref: str) -> StoredAsset:
        with self._connect() as db:
            row = db.execute(
                "SELECT ref, source, asset_id, kind, title, author, licence, page_url, entry "
                "FROM assets WHERE ref = ?",
                (ref,),
            ).fetchone()
            if row is None:
                raise UnknownRecord(f"no asset {ref!r} in the library")
            files = db.execute(
                "SELECT path, sha256, bytes FROM asset_files WHERE ref = ? ORDER BY rowid", (ref,)
            ).fetchall()
        return StoredAsset(
            ref=row[0],
            source=row[1],
            asset_id=row[2],
            kind=_kind(row[3]),
            title=row[4],
            author=row[5],
            licence=row[6],
            page_url=row[7],
            entry=row[8],
            files=tuple(StoredFile(path=p, sha256=s, bytes=b) for p, s, b in files),
        )

    def assets(self) -> list[StoredAsset]:
        with self._connect() as db:
            refs = [r[0] for r in db.execute("SELECT ref FROM assets ORDER BY downloaded_at, ref")]
        return [self.asset(ref) for ref in refs]

    # --- scenarios ------------------------------------------------------------------------

    def create_scenario(self, name: str, preset: str) -> Scenario:
        if preset not in self._presets:
            raise UnknownRecord(f"no preset {preset!r} (have: {', '.join(self.presets)})")
        base = _slug(name)
        with self._connect() as db:
            taken = {
                r[0] for r in db.execute("SELECT id FROM scenarios WHERE id LIKE ?", (f"{base}%",))
            }
            scenario_id = base
            n = 2
            while scenario_id in taken:
                scenario_id, n = f"{base}-{n}", n + 1
            now = _now()
            db.execute("INSERT INTO scenarios VALUES (?, ?, 1, ?)", (scenario_id, name, now))
            db.execute(
                "INSERT INTO scenario_versions VALUES (?, 1, ?, ?)",
                (scenario_id, json.dumps(self._presets[preset]), now),
            )
        return self.scenario(scenario_id)

    def save(self, scenario_id: str, manifest: Manifest) -> Scenario:
        """Validate and store `manifest` as the scenario's next version."""
        validate_manifest(manifest)
        current = self.scenario(scenario_id)
        version = current.version + 1
        now = _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO scenario_versions VALUES (?, ?, ?, ?)",
                (scenario_id, version, json.dumps(manifest), now),
            )
            db.execute(
                "UPDATE scenarios SET version = ?, updated_at = ? WHERE id = ?",
                (version, now, scenario_id),
            )
        return self.scenario(scenario_id)

    def scenario(self, scenario_id: str) -> Scenario:
        with self._connect() as db:
            row = db.execute(
                "SELECT s.id, s.name, s.version, s.updated_at, v.manifest FROM scenarios s "
                "JOIN scenario_versions v ON v.scenario_id = s.id AND v.version = s.version "
                "WHERE s.id = ?",
                (scenario_id,),
            ).fetchone()
        if row is None:
            raise UnknownRecord(f"no scenario {scenario_id!r}")
        manifest: Manifest = json.loads(row[4])
        return Scenario(
            id=row[0],
            name=row[1],
            version=row[2],
            manifest=manifest,
            credits=self._credits(manifest),
            updated_at=row[3],
        )

    def scenarios(self) -> list[Scenario]:
        with self._connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM scenarios ORDER BY updated_at, id")]
        return [self.scenario(i) for i in ids]

    def history(self, scenario_id: str) -> list[int]:
        with self._connect() as db:
            versions = [
                r[0]
                for r in db.execute(
                    "SELECT version FROM scenario_versions WHERE scenario_id = ? ORDER BY version",
                    (scenario_id,),
                )
            ]
        if not versions:
            raise UnknownRecord(f"no scenario {scenario_id!r}")
        return versions

    def _credits(self, manifest: Manifest) -> tuple[Credit, ...]:
        """A credit for every attribution-licensed library asset the manifest references."""
        paths = _referenced_paths(manifest)
        credits: list[Credit] = []
        for asset in self.assets():
            if not any(
                path.startswith(f"library/{asset.source}/{asset.asset_id}/") for path in paths
            ):
                continue
            verdict = check_licence(asset.licence)
            if verdict.spdx is not None and verdict.spdx.startswith("CC-BY"):
                credits.append(
                    Credit(asset.ref, asset.title, asset.author, asset.licence, asset.page_url)
                )
        return tuple(credits)


def _referenced_paths(manifest: Manifest) -> Sequence[str]:
    paths: list[str] = []
    models = manifest.get("models")
    for model in models if isinstance(models, list) else []:
        if isinstance(model, dict) and isinstance(model.get("glb"), str):
            paths.append(model["glb"])
    materials = manifest.get("materials")
    for material in materials.values() if isinstance(materials, dict) else []:
        if isinstance(material, dict):
            paths += [
                v
                for k, v in material.items()
                if k in ("base_color", "normal", "roughness", "arm") and isinstance(v, str)
            ]
    return paths


__all__ = [
    "Credit",
    "LicenceRefused",
    "Scenario",
    "ScenarioInvalid",
    "ScenarioStore",
    "StoredAsset",
    "StoredFile",
    "UnknownRecord",
]
