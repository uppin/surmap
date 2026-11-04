"""A scenario as a portable zip bundle: its latest manifest and the library assets it uses.

`scenario.json` holds the record — `format`, `format_version`, the scenario's id, name and
version, its manifest, and every library asset the manifest references with each file's path,
SHA-256 and size — and each of those files sits in the zip at its `library/…` path. Another
station imports it without fetching anything: every file must match its hash and stay inside the
library, every asset's licence must still pass `check_licence`, and every `library/…` path the
manifest names must be in the bundle or already on the station.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping

from surmap.simulation.scenario_manifest import Manifest, ScenarioInvalid, validate_manifest
from surmap.simulation.scenario_store import (
    LicenceRefused,
    Scenario,
    ScenarioStore,
    StoredAsset,
    StoredFile,
    referenced_paths,
)

BUNDLE_FORMAT = "surmap-scenario-bundle"
BUNDLE_FORMAT_VERSION = 1
RECORD = "scenario.json"
SUFFIX = ".surmap-sim.zip"


class BundleInvalid(ValueError):
    """A file that is not a scenario bundle this station can import."""


def export_bundle(store: ScenarioStore, scenario_id: str) -> bytes:
    """`scenario_id`'s latest version as a bundle; `UnknownRecord` when there is no such one."""
    scenario = store.scenario(scenario_id)
    assets = _used_assets(store, scenario.manifest)
    record = {
        "format": BUNDLE_FORMAT,
        "format_version": BUNDLE_FORMAT_VERSION,
        "id": scenario.id,
        "name": scenario.name,
        "version": scenario.version,
        "manifest": scenario.manifest,
        "assets": [_asset_record(asset) for asset in assets],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(RECORD, json.dumps(record, indent=2))
        for asset in assets:
            for file in asset.files:
                on_disk = store.library_file(file.path)
                if on_disk is not None:
                    archive.writestr(file.path, on_disk.read_bytes())
    return buffer.getvalue()


def import_bundle(store: ScenarioStore, data: bytes, *, into: str | None = None) -> Scenario:
    """Store the bundle's assets and its manifest: as the next version of `into`, or as a new
    scenario under the bundle's name. `BundleInvalid` says what is wrong with it;
    `UnknownRecord` when `into` is not a scenario."""
    target = None if into is None else store.scenario(into)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BundleInvalid("not a SurMap scenario bundle (not a zip file)") from exc
    with archive:
        record = _record(archive)
        manifest = record["manifest"]
        assert isinstance(manifest, dict)
        assets = [_asset(raw) for raw in _list(record, "assets")]
        bundled = {file.path for asset in assets for file in asset.files}
        missing = [
            path
            for path in referenced_paths(manifest)
            if path.startswith("library/")
            and path not in bundled
            and store.library_file(path) is None
        ]
        if missing:
            raise BundleInvalid(f"the manifest uses {', '.join(missing)}, which it does not carry")
        brought = [(asset, _files(asset, archive)) for asset in assets]
    try:
        validate_manifest(manifest)
    except ScenarioInvalid as exc:
        raise BundleInvalid(f"its manifest is invalid: {exc}") from exc
    try:
        store.adopt(brought)
    except (LicenceRefused, ValueError) as exc:
        raise BundleInvalid(str(exc)) from exc
    if target is None:
        return store.import_scenario(str(record["name"]), manifest)
    return store.save(target.id, manifest)


def _files(asset: StoredAsset, archive: zipfile.ZipFile) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for file in asset.files:
        try:
            files[file.path] = archive.read(file.path)
        except KeyError as exc:
            raise BundleInvalid(f"{asset.ref}: {file.path} is missing from the bundle") from exc
    return files


def _used_assets(store: ScenarioStore, manifest: Manifest) -> list[StoredAsset]:
    paths = referenced_paths(manifest)
    return [
        asset
        for asset in store.assets()
        if any(path.startswith(f"library/{asset.source}/{asset.asset_id}/") for path in paths)
    ]


def _asset_record(asset: StoredAsset) -> dict[str, object]:
    return {
        "ref": asset.ref,
        "source": asset.source,
        "asset_id": asset.asset_id,
        "kind": asset.kind,
        "title": asset.title,
        "author": asset.author,
        "licence": asset.licence,
        "page_url": asset.page_url,
        "entry": asset.entry,
        "files": [{"path": f.path, "sha256": f.sha256, "bytes": f.bytes} for f in asset.files],
    }


def _record(archive: zipfile.ZipFile) -> Mapping[str, object]:
    try:
        record = json.loads(archive.read(RECORD))
    except (KeyError, ValueError) as exc:
        raise BundleInvalid(f"not a SurMap scenario bundle (no readable {RECORD})") from exc
    if not isinstance(record, dict) or record.get("format") != BUNDLE_FORMAT:
        raise BundleInvalid("not a SurMap scenario bundle")
    if record.get("format_version") != BUNDLE_FORMAT_VERSION:
        raise BundleInvalid(
            f"bundle format version {record.get('format_version')!r} is not supported "
            f"(this station reads {BUNDLE_FORMAT_VERSION})"
        )
    if not isinstance(record.get("name"), str) or not isinstance(record.get("manifest"), dict):
        raise BundleInvalid("the bundle's record has no name or manifest")
    return record


def _asset(raw: object) -> StoredAsset:
    if not isinstance(raw, dict):
        raise BundleInvalid("an asset record is not an object")
    try:
        files = tuple(
            StoredFile(path=str(f["path"]), sha256=str(f["sha256"]), bytes=int(f["bytes"]))
            for f in raw["files"]
        )
        kind = raw["kind"]
        if kind not in ("model", "texture", "hdri"):
            raise ValueError(f"unknown asset kind {kind!r}")
        return StoredAsset(
            ref=str(raw["ref"]),
            source=str(raw["source"]),
            asset_id=str(raw["asset_id"]),
            kind=kind,
            title=str(raw["title"]),
            author=str(raw["author"]),
            licence=str(raw["licence"]),
            page_url=str(raw["page_url"]),
            entry=str(raw["entry"]),
            files=files,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BundleInvalid(f"an asset record is malformed: {exc}") from exc


def _list(record: Mapping[str, object], key: str) -> list[object]:
    value = record.get(key, [])
    if not isinstance(value, list):
        raise BundleInvalid(f"the bundle's {key} is not a list")
    return value


__all__ = ["BUNDLE_FORMAT", "SUFFIX", "BundleInvalid", "export_bundle", "import_bundle"]
