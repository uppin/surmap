"""Openly licensed disaster datasets, downloaded on demand into a local cache.

Two sources, both fetched over plain HTTPS with ``urllib`` (no extra
dependencies), both cached outside the repository and never committed:

* **Boreal Forest Fire** (Finnish Geospatial Research Institute FGI,
  National Land Survey of Finland, with the University of Jyväskylä;
  CC BY 4.0), published on Fairdata Etsin as
  dataset ``1dce1023-493a-4d63-a906-f2a44f831898``. The file list comes
  from the public Metax v3 API; each file is fetched through a one-time
  download URL that Etsin's open download endpoint signs for open-access
  datasets (no login). Every file is SHA-256 checked against Metax.
  Default cache: ``~/.cache/surmap/boreal-fire``.
* **NOAA Emergency Response Imagery, 2025 California fires** (NOAA NGS
  Remote Sensing Division, CC0-1.0, InPort item 74399): NOAA's own
  28 January 2025 flight over the Eaton and Palisades burn areas, as
  Cloud-Optimized GeoTIFF tiles in the public ``noaa-eri-pds`` S3 bucket
  (anonymous HTTPS). The Maxar imagery linked from the same NOAA page is
  *not* used. Default cache: ``~/.cache/surmap/noaa-eri-2025``.

Downloads are resumable and skip what is already cached: a finished file
is only ever renamed into place from ``<name>.part`` after its size (and
checksum, where the source publishes one) matched. NOAA ``.part`` files
are resumed with an HTTP range request; the Fairdata download service
does not honour ranges, so a Boreal ``.part`` file is restarted.

Each cache folder gets an ``ATTRIBUTION.md`` with the licence and credit.
All network access goes through ``Transport``, so tests never open a socket.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

USER_AGENT = "surmap-datasets"
_CHUNK = 1 << 20


class DatasetError(RuntimeError):
    """A listing, download, or checksum problem with a remote dataset."""


# --------------------------------------------------------------------------- transport


@dataclass(frozen=True)
class Stream:
    """An open download: HTTP ``status`` (200 whole body, 206 partial) and its chunks."""

    status: int
    chunks: Iterable[bytes]


class Transport(Protocol):
    def fetch(self, url: str, *, json_body: Mapping[str, object] | None = None) -> bytes:
        """GET ``url`` (or POST ``json_body`` as JSON) and return the whole body."""
        ...

    def stream(self, url: str, *, start: int = 0) -> Stream:
        """GET ``url`` as chunks, asking for bytes from ``start`` on when it is above 0."""
        ...


class UrllibTransport:
    """``Transport`` over ``urllib`` with a fixed user agent and timeout."""

    def __init__(self, timeout_s: float = 120.0) -> None:
        self._timeout_s = timeout_s

    def fetch(self, url: str, *, json_body: Mapping[str, object] | None = None) -> bytes:
        headers = {"User-Agent": USER_AGENT}
        data = None
        if json_body is not None:
            data = json.dumps(dict(json_body)).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise DatasetError(f"HTTP {exc.code} from {_redact(url)}") from exc
        if not isinstance(payload, bytes):
            raise DatasetError(f"{_redact(url)} did not return bytes")
        return payload

    def stream(self, url: str, *, start: int = 0) -> Stream:
        headers = {"User-Agent": USER_AGENT}
        if start > 0:
            headers["Range"] = f"bytes={start}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=self._timeout_s)
        except urllib.error.HTTPError as exc:
            raise DatasetError(f"HTTP {exc.code} from {_redact(url)}") from exc

        def chunks() -> Iterator[bytes]:
            with response:
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        return
                    yield chunk

        return Stream(status=int(response.status), chunks=chunks())


def _redact(url: str) -> str:
    """``url`` without its query string (Fairdata download tokens live there)."""
    return url.split("?", 1)[0]


# --------------------------------------------------------------------------- plan + download


@dataclass(frozen=True)
class RemoteFile:
    """One file to cache: where it goes, where it comes from, and how to check it."""

    relpath: str
    size: int
    source: str
    sha256: str | None = None
    md5: str | None = None


@dataclass(frozen=True)
class Plan:
    """The files one command would download, in order, under ``root``."""

    dataset: str
    root: Path
    files: tuple[RemoteFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def cached(self, item: RemoteFile) -> bool:
        target = safe_target(self.root, item.relpath)
        return target.is_file() and target.stat().st_size == item.size

    def missing_bytes(self) -> int:
        return sum(item.size for item in self.files if not self.cached(item))


@dataclass(frozen=True)
class DownloadResult:
    downloaded: int
    skipped: int
    bytes_written: int


Resolve = Callable[[RemoteFile], str]
Log = Callable[[str], None]


def _quiet(_: str) -> None:
    pass


def safe_target(root: Path, relpath: str) -> Path:
    """``root / relpath``, refusing absolute paths and ``..`` from a remote listing."""
    pure = PurePosixPath(relpath)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise DatasetError(f"unsafe path in remote listing: {relpath!r}")
    return root.joinpath(*pure.parts)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    raise AssertionError("unreachable")


def download_plan(
    plan: Plan,
    transport: Transport,
    *,
    resolve: Resolve | None = None,
    resumable: bool = True,
    log: Log = _quiet,
    retries: int = 2,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    """Fetch every file of ``plan`` not already cached; verify, then rename into place.

    ``resolve`` turns a file into the URL to stream (default: its ``source``);
    Fairdata needs a fresh signed URL per request. ``resumable`` continues a
    ``.part`` file with a range request; a server that answers 200 instead of
    206 restarts it from zero. A failed file is retried ``retries`` times
    (with a fresh URL and a short back-off) before its error is raised.
    """
    plan.root.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = written = 0
    for number, item in enumerate(plan.files, start=1):
        target = safe_target(plan.root, item.relpath)
        if plan.cached(item):
            skipped += 1
            continue
        log(f"[{number}/{len(plan.files)}] {item.relpath} ({human_size(item.size)})")
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(retries + 1):
            try:
                written += _fetch_one(item, target, transport, resolve, resumable)
                break
            except (OSError, DatasetError) as exc:
                if attempt == retries:
                    raise
                log(f"  retrying {item.relpath} after {type(exc).__name__}: {exc}")
                sleep(2.0 * (attempt + 1))
        downloaded += 1
    return DownloadResult(downloaded=downloaded, skipped=skipped, bytes_written=written)


def _fetch_one(
    item: RemoteFile,
    target: Path,
    transport: Transport,
    resolve: Resolve | None,
    resumable: bool,
) -> int:
    part = target.with_name(target.name + ".part")
    start = part.stat().st_size if resumable and part.is_file() else 0
    if start > item.size:
        start = 0
    url = resolve(item) if resolve is not None else item.source
    stream = transport.stream(url, start=start)
    if stream.status == 206 and start > 0:
        mode = "ab"
    elif stream.status in (200, 206):
        start, mode = 0, "wb"
    else:
        raise DatasetError(f"HTTP {stream.status} for {item.relpath}")
    written = 0
    with part.open(mode) as out:
        for chunk in stream.chunks:
            out.write(chunk)
            written += len(chunk)
    size = part.stat().st_size
    if size != item.size:
        raise DatasetError(
            f"{item.relpath}: got {size} bytes, expected {item.size}; "
            f"{part.name} kept, rerun to resume"
        )
    if item.sha256 is not None and _digest(part, "sha256") != item.sha256:
        part.unlink()
        raise DatasetError(f"{item.relpath} failed SHA-256 verification; removed")
    if item.md5 is not None and _digest(part, "md5") != item.md5:
        part.unlink()
        raise DatasetError(f"{item.relpath} failed MD5 verification; removed")
    part.replace(target)
    return written


def _digest(path: Path, name: str) -> str:
    digest = hashlib.new(name)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def write_attribution(root: Path, text: str) -> Path:
    """Write ``ATTRIBUTION.md`` into the dataset's cache folder."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "ATTRIBUTION.md"
    path.write_text(text, encoding="utf-8")
    return path


def _cache_root(env: str, name: str) -> Path:
    configured = os.environ.get(env, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "surmap" / name


def _natural(text: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text))


def _json(raw: bytes, what: str) -> object:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetError(f"{what} reply was not JSON") from exc


# --------------------------------------------------------------------------- Boreal Forest Fire

BOREAL_NAME = "boreal-fire"
BOREAL_DATASET_ID = "1dce1023-493a-4d63-a906-f2a44f831898"
BOREAL_DOI = "10.23729/fd-72c6cf74-b8eb-3687-860d-bf93a1ab94c9"
BOREAL_ETSIN_URL = f"https://etsin.fairdata.fi/dataset/{BOREAL_DATASET_ID}"
BOREAL_PAPER_DOI = "10.1038/s41597-025-05634-0"
BOREAL_FILES_URL = (
    f"https://metax.fairdata.fi/v3/datasets/{BOREAL_DATASET_ID}/files?pagination=false"
)
BOREAL_AUTHORIZE_URL = "https://etsin.fairdata.fi/api/download/authorize"
BOREAL_PREFIX = "/Boreal-Forest-Fire/"
BOREAL_SUBSETS = {
    "bbox": "Boreal-Forest-Fire-Subset-A",
    "videos": "Boreal-Forest-Fire-Subset-B",
    "segmentation": "Boreal-Forest-Fire-Subset-C",
    "notebook": "Visualisation-And-Coordinate-Conversion-Notebook",
}
BOREAL_SITES = ("empty", "evo", "heinola", "karkkila", "ruokolahti")
BOREAL_SPLITS = ("train", "valid", "test")
BOREAL_ATTRIBUTION = f"""\
# Boreal Forest Fire dataset (cached by surmap)

Licence: Creative Commons Attribution 4.0 International (CC BY 4.0),
https://creativecommons.org/licenses/by/4.0/

Dataset: Pesonen, J., Raita-Hakola, A.-M., Joutsalainen, J., Hakala, T.,
Akhtar, W., Karjalainen, V., Koivumäki, N., Markelin, L., Suomalainen, J.,
Alves de Oliveira, R., Pölönen, I., Honkavaara, E. (2025). "Boreal Forest
Fire: UAV-collected Wildfire Detection and Smoke Segmentation Dataset".
Finnish Geospatial Research Institute FGI, National Land Survey of Finland.
Fairdata, https://doi.org/{BOREAL_DOI} ({BOREAL_ETSIN_URL}).

Data descriptor: Pesonen, J. et al. "Boreal Forest Fire: UAV-collected
Wildfire Detection and Smoke Segmentation Dataset". Scientific Data 12, 1419
(2025), https://doi.org/{BOREAL_PAPER_DOI}

Files in this folder are unmodified copies from Fairdata IDA, downloaded on
demand by surmap's scripts/download_disaster_data.py. They are not part of
the surmap repository and are not redistributed by it.
"""


def boreal_cache_dir() -> Path:
    """``$SURMAP_BOREAL_CACHE`` when set, otherwise ``~/.cache/surmap/boreal-fire``."""
    return _cache_root("SURMAP_BOREAL_CACHE", BOREAL_NAME)


def boreal_listing(transport: Transport) -> list[RemoteFile]:
    """Every file of the dataset, from Metax, as cache-relative ``RemoteFile`` s."""
    payload = _json(transport.fetch(BOREAL_FILES_URL), "Metax")
    if isinstance(payload, dict):
        payload = payload.get("results")
    if not isinstance(payload, list):
        raise DatasetError("Metax file listing was not a list")
    files: list[RemoteFile] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise DatasetError("Metax file entry was not an object")
        pathname, size, checksum = entry.get("pathname"), entry.get("size"), entry.get("checksum")
        if not isinstance(pathname, str) or not isinstance(size, int):
            raise DatasetError("Metax file entry had no pathname or size")
        if not pathname.startswith(BOREAL_PREFIX):
            raise DatasetError(f"unexpected Boreal path {pathname!r}")
        sha256 = None
        if isinstance(checksum, str) and checksum.startswith("sha256:"):
            sha256 = checksum.removeprefix("sha256:").lower()
        relpath = pathname.removeprefix(BOREAL_PREFIX)
        files.append(RemoteFile(relpath=relpath, size=size, source=pathname, sha256=sha256))
    return files


def _boreal_sample(item: RemoteFile) -> tuple[str, str, str] | None:
    """``(subset, site or split, stem)`` for a data file; None for always-included files."""
    parts = item.relpath.split("/")
    subset = parts[0]
    inner = parts[1:]
    if len(inner) < 2 or inner[0] == "Video-Ground-Truth":
        return None
    stem = PurePosixPath(inner[-1]).stem
    if subset == BOREAL_SUBSETS["segmentation"]:
        return (subset, inner[1] if len(inner) >= 3 else "", stem)
    return (subset, inner[0].split("-", 1)[0].lower(), stem)


def select_boreal(
    files: Sequence[RemoteFile],
    *,
    subsets: Sequence[str],
    sites: Sequence[str] = (),
    splits: Sequence[str] = (),
    limit: int | None = None,
) -> list[RemoteFile]:
    """Files of ``subsets``, filtered by site (bbox/videos) or split (segmentation).

    ``limit`` counts samples, not files: an image keeps its label and masks,
    a video counts once. Ground-truth tables and counts files always come along.
    """
    unknown = [name for name in subsets if name not in BOREAL_SUBSETS]
    if unknown:
        raise DatasetError(f"unknown Boreal subset(s): {', '.join(unknown)}")
    if limit is not None and limit < 1:
        raise DatasetError("--limit must be at least 1")
    dirs = {BOREAL_SUBSETS[name] for name in subsets}
    seg = BOREAL_SUBSETS["segmentation"]
    chosen = [item for item in files if item.relpath.split("/", 1)[0] in dirs]
    always: list[RemoteFile] = []
    samples: dict[tuple[str, str, str], list[RemoteFile]] = {}
    for item in chosen:
        key = _boreal_sample(item)
        if key is None:
            always.append(item)
            continue
        subset, group, _ = key
        if subset == seg and splits and group not in splits:
            continue
        if subset != seg and sites and group not in sites:
            continue
        samples.setdefault(key, []).append(item)
    keys = sorted(samples, key=lambda key: tuple(_natural(part) for part in key))
    if limit is not None:
        keys = keys[:limit]
    picked = sorted(always, key=lambda item: _natural(item.relpath))
    for key in keys:
        picked.extend(sorted(samples[key], key=lambda item: _natural(item.relpath)))
    return picked


def boreal_resolver(transport: Transport) -> Resolve:
    """A fresh signed Fairdata download URL per file (each URL works once)."""

    def resolve(item: RemoteFile) -> str:
        reply = _json(
            transport.fetch(
                BOREAL_AUTHORIZE_URL,
                json_body={"cr_id": BOREAL_DATASET_ID, "file": item.source},
            ),
            "Etsin download authorize",
        )
        url = reply.get("url") if isinstance(reply, dict) else None
        if not isinstance(url, str) or not url.startswith("https://download.fairdata.fi"):
            raise DatasetError(f"Etsin did not authorize a download for {item.relpath}")
        return url

    return resolve


def boreal_plan(
    transport: Transport,
    *,
    subsets: Sequence[str] = ("segmentation",),
    sites: Sequence[str] = (),
    splits: Sequence[str] = (),
    limit: int | None = None,
    cache_dir: Path | None = None,
) -> Plan:
    files = select_boreal(
        boreal_listing(transport), subsets=subsets, sites=sites, splits=splits, limit=limit
    )
    root = cache_dir if cache_dir is not None else boreal_cache_dir()
    return Plan(dataset=BOREAL_NAME, root=root, files=tuple(files))


def boreal_subset_sizes(files: Sequence[RemoteFile]) -> dict[str, tuple[int, int]]:
    """``{subset name: (file count, bytes)}`` over a listing."""
    sizes: dict[str, tuple[int, int]] = {}
    for name, folder in BOREAL_SUBSETS.items():
        inside = [item for item in files if item.relpath.split("/", 1)[0] == folder]
        sizes[name] = (len(inside), sum(item.size for item in inside))
    return sizes


BOREAL_PACKAGES_URL = f"https://etsin.fairdata.fi/api/download/requests?cr_id={BOREAL_DATASET_ID}"
PACKAGE_DIR = "packages"


def boreal_packages(transport: Transport) -> dict[str, RemoteFile]:
    """Ready-made Fairdata zip packages, keyed by the one folder they hold.

    Fairdata keeps zips that earlier visitors asked for; only finished ones
    covering exactly one folder are listed. The zip is a ``RemoteFile`` under
    ``packages/`` whose ``source`` is the package name. Nothing is requested
    or generated on the server.
    """
    payload = _json(transport.fetch(BOREAL_PACKAGES_URL), "Etsin package list")
    entries = payload.get("partial") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}
    packages: dict[str, RemoteFile] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("status") != "SUCCESS":
            continue
        name, size, scope = entry.get("package"), entry.get("size"), entry.get("scope")
        checksum = entry.get("checksum")
        if not isinstance(name, str) or not isinstance(size, int) or not isinstance(scope, list):
            continue
        if len(scope) != 1 or not isinstance(scope[0], str):
            continue
        sha256 = None
        if isinstance(checksum, str) and checksum.startswith("sha256:"):
            sha256 = checksum.removeprefix("sha256:").lower()
        folder = scope[0].removeprefix(BOREAL_PREFIX).rstrip("/")
        packages.setdefault(
            folder,
            RemoteFile(relpath=f"{PACKAGE_DIR}/{name}", size=size, source=name, sha256=sha256),
        )
    return packages


def boreal_package_plan(
    transport: Transport,
    *,
    subsets: Sequence[str] = ("segmentation",),
    cache_dir: Path | None = None,
) -> tuple[Plan, list[RemoteFile]]:
    """One zip per whole subset, skipping subsets already fully cached.

    Returns the plan of zips and the dataset files they should unpack to.
    """
    unknown = [name for name in subsets if name not in BOREAL_SUBSETS]
    if unknown:
        raise DatasetError(f"unknown Boreal subset(s): {', '.join(unknown)}")
    root = cache_dir if cache_dir is not None else boreal_cache_dir()
    listing = boreal_listing(transport)
    available = boreal_packages(transport)
    zips: list[RemoteFile] = []
    expected: list[RemoteFile] = []
    for name in subsets:
        folder = BOREAL_SUBSETS[name]
        inside = [item for item in listing if item.relpath.split("/", 1)[0] == folder]
        expected.extend(inside)
        probe = Plan(dataset=BOREAL_NAME, root=root, files=tuple(inside))
        if all(probe.cached(item) for item in inside):
            continue
        package = available.get(folder)
        if package is None:
            raise DatasetError(
                f"Fairdata has no ready-made package for {folder}; run without --package"
            )
        zips.append(package)
    return Plan(dataset=BOREAL_NAME, root=root, files=tuple(zips)), expected


def boreal_package_resolver(transport: Transport) -> Resolve:
    """A signed one-time URL for a ready-made package zip."""

    def resolve(item: RemoteFile) -> str:
        reply = _json(
            transport.fetch(
                BOREAL_AUTHORIZE_URL,
                json_body={"cr_id": BOREAL_DATASET_ID, "package": item.source},
            ),
            "Etsin download authorize",
        )
        url = reply.get("url") if isinstance(reply, dict) else None
        if not isinstance(url, str) or not url.startswith("https://download.fairdata.fi"):
            raise DatasetError(f"Etsin did not authorize package {item.source}")
        return url

    return resolve


def extract_package(
    zip_path: Path, root: Path, expected: Sequence[RemoteFile], *, log: Log = _quiet
) -> int:
    """Unpack a Fairdata zip into ``root``; sizes must match the Metax listing.

    Members are written via ``.part`` and renamed; files already cached with
    the right size are left alone. Returns the number of files written.
    """
    sizes = {item.relpath: item.size for item in expected}
    written = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relpath = info.filename.removeprefix(BOREAL_PREFIX.lstrip("/"))
            if relpath not in sizes:
                raise DatasetError(f"{zip_path.name} holds unexpected file {info.filename!r}")
            target = safe_target(root, relpath)
            if target.is_file() and target.stat().st_size == sizes[relpath]:
                continue
            if info.file_size != sizes[relpath]:
                raise DatasetError(f"{relpath}: zip size {info.file_size} != {sizes[relpath]}")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            with archive.open(info) as source, part.open("wb") as out:
                for block in iter(lambda: source.read(_CHUNK), b""):
                    out.write(block)
            part.replace(target)
            written += 1
    log(f"unpacked {written} files from {zip_path.name}")
    return written


# --------------------------------------------------------------------------- NOAA ERI 2025

NOAA_NAME = "noaa-eri-2025"
NOAA_BUCKET_URL = "https://noaa-eri-pds.s3.amazonaws.com"
NOAA_EVENT = "2025_California_Fires/"
NOAA_FLIGHT = "20250128a_RGB"
NOAA_PREFIX = f"{NOAA_EVENT}{NOAA_FLIGHT}/"
NOAA_INPORT_URL = "https://www.fisheries.noaa.gov/inport/item/74399"
NOAA_INDEX_URL = "https://storms.ngs.noaa.gov/storms/2025_eri/index.html"
# Tiles are named by their north-west corner, 45 arc-seconds a side
# (e.g. 20250128aC1180215w341200n.tif: 118°02'15"W, 34°12'00"N).
NOAA_TILE_DEG = 45 / 3600
_TILE_NAME = re.compile(r"^20250128aC(\d{3})(\d{2})(\d{2})w(\d{2})(\d{2})(\d{2})n\.tif$")
# The NOAA tiles fall into two clusters; these are their extents
# (west, south, east, north) in WGS 84 degrees, read from the tile names.
NOAA_FIRES: dict[str, tuple[float, float, float, float]] = {
    "palisades": (-118.7625, 34.0125, -118.4375, 34.1),
    "eaton": (-118.2, 34.15, -117.975, 34.225),
}
NOAA_ATTRIBUTION = f"""\
# NOAA Emergency Response Imagery, 2025 California fires (cached by surmap)

Licence: CC0-1.0 (Creative Commons Zero 1.0 Universal Public Domain Dedication),
https://creativecommons.org/publicdomain/zero/1.0/
Data access constraints: none (NOAA InPort item 74399, {NOAA_INPORT_URL}).

Source: National Geodetic Survey (NGS) Remote Sensing Division, NOAA.
"2025 NOAA NGS Emergency Response Imagery: California Fires", imagery
acquired 28 January 2025, ~7.5 cm ground sample distance, distributed via
the NOAA Open Data Dissemination program on AWS (s3://noaa-eri-pds/{NOAA_PREFIX}).
Index: {NOAA_INDEX_URL}

Citation (from InPort): National Geodetic Survey, 2026: 2025 NOAA NGS
Emergency Response Imagery: California Fires [InPort metadata record],
{NOAA_INPORT_URL}.

NOAA asks for attribution of unaltered NOAA data and that no endorsement by
or affiliation with NOAA be stated or implied. NOAA's metadata notes that
conditions may have changed since acquisition and that the data are not for
critical applications without awareness of their limitations.

Only NOAA's own tiles are cached here; the Maxar Open Data imagery linked from
the same NOAA page (CC BY-NC 4.0) is not used. Files are unmodified copies,
not part of the surmap repository and not redistributed by it.
"""


@dataclass(frozen=True)
class NoaaTile:
    item: RemoteFile
    bbox: tuple[float, float, float, float]


def noaa_cache_dir() -> Path:
    """``$SURMAP_NOAA_ERI_CACHE`` when set, otherwise ``~/.cache/surmap/noaa-eri-2025``."""
    return _cache_root("SURMAP_NOAA_ERI_CACHE", NOAA_NAME)


def tile_bbox(name: str) -> tuple[float, float, float, float] | None:
    """``(west, south, east, north)`` of a tile from its file name, or None."""
    match = _TILE_NAME.match(name)
    if match is None:
        return None
    lon_d, lon_m, lon_s, lat_d, lat_m, lat_s = (int(group) for group in match.groups())
    west = -(lon_d + lon_m / 60 + lon_s / 3600)
    north = lat_d + lat_m / 60 + lat_s / 3600
    return (west, north - NOAA_TILE_DEG, west + NOAA_TILE_DEG, north)


def list_bucket(transport: Transport, prefix: str, *, strip: str = "") -> list[RemoteFile]:
    """Every object under ``prefix`` (ListObjectsV2, anonymous, all pages).

    Each ``relpath`` is the object key without the leading ``strip``.
    """
    files: list[RemoteFile] = []
    token: str | None = None
    while True:
        query = {"list-type": "2", "prefix": prefix}
        if token is not None:
            query["continuation-token"] = token
        raw = transport.fetch(f"{NOAA_BUCKET_URL}/?{urllib.parse.urlencode(query)}")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise DatasetError("S3 listing was not XML") from exc
        ns = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""
        for node in root.iter(f"{ns}Contents"):
            key = node.findtext(f"{ns}Key")
            size = node.findtext(f"{ns}Size")
            etag = (node.findtext(f"{ns}ETag") or "").strip('"')
            if key is None or size is None or key.endswith("/"):
                continue
            md5 = etag.lower() if re.fullmatch(r"[0-9a-fA-F]{32}", etag) else None
            files.append(
                RemoteFile(
                    relpath=key.removeprefix(strip),
                    size=int(size),
                    source=f"{NOAA_BUCKET_URL}/{urllib.parse.quote(key)}",
                    md5=md5,
                )
            )
        if (root.findtext(f"{ns}IsTruncated") or "").lower() != "true":
            return files
        token = root.findtext(f"{ns}NextContinuationToken")
        if not token:
            raise DatasetError("S3 listing was truncated without a continuation token")


def noaa_tiles(files: Iterable[RemoteFile]) -> list[NoaaTile]:
    tiles: list[NoaaTile] = []
    for item in files:
        bbox = tile_bbox(PurePosixPath(item.relpath).name)
        if bbox is not None:
            tiles.append(NoaaTile(item=item, bbox=bbox))
    return tiles


def _intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def select_noaa(
    files: Sequence[RemoteFile],
    *,
    fire: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int | None = None,
    max_tile_bytes: int | None = None,
    include_index: bool = True,
) -> list[RemoteFile]:
    """GeoTIFF tiles touching ``bbox`` (or the ``fire`` area), plus the tile index.

    Tiles are ordered north to south, then west to east. ``limit`` caps the
    number of tiles; ``max_tile_bytes`` skips the larger ones (they reach 1.6 GB).
    """
    if bbox is None:
        if fire is None:
            raise DatasetError("pick a --fire or a --bbox")
        if fire not in NOAA_FIRES:
            raise DatasetError(f"unknown fire {fire!r}; choose {', '.join(NOAA_FIRES)}")
        bbox = NOAA_FIRES[fire]
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise DatasetError("--bbox must be WEST SOUTH EAST NORTH with west<east, south<north")
    if limit is not None and limit < 1:
        raise DatasetError("--limit must be at least 1")
    tiles = [
        tile
        for tile in noaa_tiles(files)
        if _intersects(tile.bbox, bbox)
        and (max_tile_bytes is None or tile.item.size <= max_tile_bytes)
    ]
    tiles.sort(key=lambda tile: (-tile.bbox[3], tile.bbox[0]))
    if limit is not None:
        tiles = tiles[:limit]
    picked: list[RemoteFile] = []
    if include_index:
        picked.extend(
            item
            for item in files
            if PurePosixPath(item.relpath).name.startswith("tile_index_")
            and PurePosixPath(item.relpath).suffix in {".shp", ".shx", ".dbf", ".prj"}
        )
    picked.extend(tile.item for tile in tiles)
    return picked


def noaa_plan(
    transport: Transport,
    *,
    fire: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int | None = None,
    max_tile_bytes: int | None = None,
    cache_dir: Path | None = None,
) -> Plan:
    # Mosaic tiles and the tile index sit at the top of the flight folder;
    # raw/ (un-mosaicked frames) is skipped.
    listing = [
        item
        for item in list_bucket(transport, NOAA_PREFIX, strip=NOAA_EVENT)
        if item.relpath.count("/") == 1
    ]
    files = select_noaa(listing, fire=fire, bbox=bbox, limit=limit, max_tile_bytes=max_tile_bytes)
    root = cache_dir if cache_dir is not None else noaa_cache_dir()
    return Plan(dataset=NOAA_NAME, root=root, files=tuple(files))
