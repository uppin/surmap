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
from pathlib import Path, PurePosixPath

from surmap.simulation.asset_sources import AssetHit, AssetKind, AssetSource
from surmap.simulation.licences import check_licence
from surmap.simulation.scenario_manifest import Manifest, ScenarioInvalid, validate_manifest
from surmap.simulation.sim_assets import load_asset_pins

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
        assets_dir: Path | None = None,
    ) -> None:
        self._assets_dir = None if assets_dir is None else Path(assets_dir)
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
    def assets_dir(self) -> Path | None:
        """The simulation's own assets (preset files), when the store knows where they are."""
        return self._assets_dir

    @property
    def db_path(self) -> Path:
        """The SQLite file the scenarios live in (the fleet log store shares it)."""
        return self._db_path

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

    def adopt(self, brought: Sequence[tuple[StoredAsset, Mapping[str, bytes]]]) -> None:
        """Catalogue assets brought from another station, each with the bytes of its files (by
        `library/…` path). All are checked before any is written: every licence must pass, every
        file match its SHA-256 and lie under its asset's `library/<source>/<id>/`."""
        for asset, files in brought:
            verdict = check_licence(asset.licence)
            if not verdict.accepted:
                raise LicenceRefused(f"{asset.ref}: {verdict.reason}")
            prefix = f"library/{asset.source}/{asset.asset_id}/"
            for file in asset.files:
                self._library_file(file.path)
                if not file.path.startswith(prefix):
                    raise ValueError(f"{asset.ref}: {file.path} is outside {prefix}")
                if hashlib.sha256(files[file.path]).hexdigest() != file.sha256:
                    raise ValueError(f"{asset.ref}: {file.path} does not match its SHA-256")
        for asset, files in brought:
            self._write_adopted(asset, files)

    def _write_adopted(self, asset: StoredAsset, files: Mapping[str, bytes]) -> None:
        for file in asset.files:
            target = self._library_file(file.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[file.path])
        with self._connect() as db:
            db.execute("DELETE FROM asset_files WHERE ref = ?", (asset.ref,))
            db.execute(
                "INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    asset.ref,
                    asset.source,
                    asset.asset_id,
                    asset.kind,
                    asset.title,
                    asset.author,
                    asset.licence,
                    asset.page_url,
                    asset.entry,
                    _now(),
                ),
            )
            db.executemany(
                "INSERT INTO asset_files VALUES (?, ?, ?, ?, ?)",
                [(asset.ref, f.path, f.sha256, f.bytes, "bundle") for f in asset.files],
            )

    def library_file(self, path: str) -> Path | None:
        """Where the `library/…` file `path` is on disk, when it is there."""
        try:
            target = self._library_file(path)
        except ValueError:
            return None
        return target if target.is_file() else None

    def _library_file(self, path: str) -> Path:
        """`library/…` `path` under the library directory; `ValueError` when it would leave it."""
        parts = PurePosixPath(path).parts
        if len(parts) < 2 or parts[0] != "library" or any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"{path} is not a file of the library")
        return self._library.joinpath(*parts[1:])

    def store_floor_texture(self, png: bytes, texture_path: str) -> str:
        """Write a stitched map-floor PNG under the library; returns its asset path."""
        relative = texture_path.removeprefix("library/")
        target = self._library / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(png)
        return texture_path

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
        return self._insert_scenario(name, self._presets[preset])

    def import_scenario(self, name: str, manifest: Manifest) -> Scenario:
        """A new scenario called `name` whose version 1 is `manifest` (validated)."""
        validate_manifest(manifest)
        return self._insert_scenario(name, manifest)

    def _insert_scenario(self, name: str, manifest: Manifest) -> Scenario:
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
                (scenario_id, json.dumps(manifest), now),
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
        paths = referenced_paths(manifest)
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
        credits += self._pinned_credits(manifest)
        floor = manifest.get("map_floor")
        if isinstance(floor, dict) and floor.get("attribution") == "© OpenStreetMap contributors":
            credits.append(
                Credit(
                    "openstreetmap",
                    "OpenStreetMap map floor",
                    "OpenStreetMap contributors",
                    "ODbL",
                    "https://www.openstreetmap.org/copyright",
                )
            )
        return tuple(credits)

    def _pinned_credits(self, manifest: Manifest) -> list[Credit]:
        """A credit for every attribution-licensed pinned asset the manifest shows: as a model,
        or as the model of a vehicle class it drives."""
        if self._assets_dir is None:
            return []
        shown = set(referenced_paths(manifest))
        shown |= set(vehicle_model_paths(manifest, self._assets_dir))
        return [
            Credit(pin.path, pin.title, pin.author, pin.license, pin.source)
            for pin in load_asset_pins(self._assets_dir / "assets.lock.json")
            if pin.path in shown
            and pin.license.startswith("CC-BY")
            and pin.title is not None
            and pin.author is not None
        ]


def vehicle_model_paths(manifest: Manifest, assets_dir: Path) -> Sequence[str]:
    """The model of each vehicle class the manifest's elements drive."""
    elements = manifest.get("elements")
    classes = {
        element["class"]
        for element in (elements if isinstance(elements, list) else [])
        if isinstance(element, dict)
        and element.get("kind") == "vehicle"
        and isinstance(element.get("class"), str)
    }
    paths: list[str] = []
    for vehicle_class in sorted(classes):
        class_file = assets_dir / "vehicle" / f"{vehicle_class}.vehicle.json"
        if not class_file.is_file():
            continue
        spec: object = json.loads(class_file.read_text(encoding="utf-8"))
        if isinstance(spec, dict) and isinstance(spec.get("glb"), str):
            paths.append(spec["glb"])
    return paths


def referenced_paths(manifest: Manifest) -> Sequence[str]:
    """Every asset path the manifest's models and materials name."""
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
    floor = manifest.get("map_floor")
    if isinstance(floor, dict) and isinstance(floor.get("texture"), str):
        paths.append(floor["texture"])
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
    "referenced_paths",
]
