"""Pinned runtime assets: the lock file, the fetcher and the shipped scene."""

import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import pytest

from surmap.simulation.sim_assets import (
    AssetHashMismatch,
    AssetPin,
    _default_opener,
    fetch_assets,
    load_asset_pins,
    manifest_asset_paths,
)

POC = Path(__file__).parent.parent / "examples" / "bevy-sitl-poc"


def a_lock_file(tmp_path: Path, assets: list[dict[str, object]]) -> Path:
    path = tmp_path / "assets.lock.json"
    path.write_text(json.dumps({"assets": assets}), encoding="utf-8")
    return path


def an_asset(path: str, sha256: str) -> dict[str, object]:
    return {
        "path": path,
        "url": f"https://assets.example/{path}",
        "sha256": sha256,
        "license": "CC0-1.0",
        "source": "https://assets.example/",
    }


class CountingOpener:
    """An injected downloader that serves fixed bytes and counts its calls."""

    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.payloads[url]


def test_the_lock_file_loads_into_typed_pins(tmp_path: Path) -> None:
    # Given a lock file pinning one model by its hash
    digest = hashlib.sha256(b"glb-bytes").hexdigest()
    lock = a_lock_file(tmp_path, [an_asset("models/car.glb", digest)])

    # When the pins are loaded
    pins = load_asset_pins(lock)

    # Then the pin carries path, URL, hash, licence and source
    assert pins == (
        AssetPin(
            path="models/car.glb",
            url="https://assets.example/models/car.glb",
            sha256=digest,
            license="CC0-1.0",
            source="https://assets.example/",
        ),
    )


def test_a_pin_escaping_the_assets_directory_is_refused(tmp_path: Path) -> None:
    # Given a pin whose path climbs out of the assets directory
    lock = a_lock_file(tmp_path, [an_asset("../secret.glb", "0" * 64)])

    # When the pins are loaded, Then a value error is raised
    with pytest.raises(ValueError):
        load_asset_pins(lock)


def test_an_absolute_pin_path_is_refused(tmp_path: Path) -> None:
    # Given a pin whose path is absolute
    lock = a_lock_file(tmp_path, [an_asset("/tmp/secret.glb", "0" * 64)])

    # When the pins are loaded, Then a value error is raised
    with pytest.raises(ValueError):
        load_asset_pins(lock)


def test_fetch_downloads_a_pinned_file_and_verifies_its_hash(tmp_path: Path) -> None:
    # Given a pin for bytes the opener serves
    pin = AssetPin(
        path="models/car.glb",
        url="https://assets.example/models/car.glb",
        sha256=hashlib.sha256(b"glb-bytes").hexdigest(),
        license="CC0-1.0",
        source="https://assets.example/",
    )
    opener = CountingOpener({pin.url: b"glb-bytes"})

    # When the assets are fetched
    fetch_assets((pin,), tmp_path / "assets", opener=opener)

    # Then the file is on disk with the pinned bytes, fetched exactly once
    assert (tmp_path / "assets" / "models" / "car.glb").read_bytes() == b"glb-bytes"
    assert opener.calls == [pin.url]


def test_fetch_skips_a_file_already_present_with_the_right_hash(tmp_path: Path) -> None:
    # Given the pinned file already fetched, byte for byte
    pin = AssetPin(
        path="models/car.glb",
        url="https://assets.example/models/car.glb",
        sha256=hashlib.sha256(b"glb-bytes").hexdigest(),
        license="CC0-1.0",
        source="https://assets.example/",
    )
    target = tmp_path / "assets" / "models" / "car.glb"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"glb-bytes")
    opener = CountingOpener({pin.url: b"other-bytes"})

    # When the assets are fetched again
    fetch_assets((pin,), tmp_path / "assets", opener=opener)

    # Then nothing is downloaded and the file is untouched
    assert opener.calls == []
    assert target.read_bytes() == b"glb-bytes"


def test_a_hash_mismatch_leaves_no_file_behind(tmp_path: Path) -> None:
    # Given a pin whose hash the served bytes do not match
    pin = AssetPin(
        path="models/car.glb",
        url="https://assets.example/models/car.glb",
        sha256=hashlib.sha256(b"expected-bytes").hexdigest(),
        license="CC0-1.0",
        source="https://assets.example/",
    )
    opener = CountingOpener({pin.url: b"served-bytes"})

    # When the assets are fetched, Then the mismatch is raised and no file remains
    with pytest.raises(AssetHashMismatch):
        fetch_assets((pin,), tmp_path / "assets", opener=opener)
    assert not (tmp_path / "assets" / "models" / "car.glb").exists()


def test_fetch_extracts_the_named_member_of_a_downloaded_zip(tmp_path: Path) -> None:
    # Given a zip download whose pinned member is the model inside it
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("model.glb", b"glb-inside-zip")
        archive.writestr("readme.txt", b"not the model")
    pin = AssetPin(
        path="models/car.glb",
        url="https://assets.example/car.zip",
        sha256=hashlib.sha256(b"glb-inside-zip").hexdigest(),
        license="CC0-1.0",
        source="https://assets.example/",
        member="model.glb",
    )
    opener = CountingOpener({pin.url: buffer.getvalue()})

    # When the assets are fetched
    fetch_assets((pin,), tmp_path / "assets", opener=opener)

    # Then the extracted member, not the zip, is the file on disk
    assert (tmp_path / "assets" / "models" / "car.glb").read_bytes() == b"glb-inside-zip"


def test_a_manifest_names_its_hdri_textures_and_models(tmp_path: Path) -> None:
    # Given a scene manifest with one of each kind of asset
    scene = tmp_path / "scene.json"
    scene.write_text(
        json.dumps(
            {
                "version": 1,
                "environment": {"hdri": "hdri/sky.hdr"},
                "materials": {
                    "asphalt": {
                        "base_color": "textures/asphalt.jpg",
                        "normal": "textures/asphalt_n.png",
                    }
                },
                "models": [{"glb": "models/car.glb"}],
            }
        ),
        encoding="utf-8",
    )

    # When its asset paths are collected
    paths = manifest_asset_paths(scene)

    # Then every referenced path is named exactly once
    assert paths == {
        "hdri/sky.hdr",
        "textures/asphalt.jpg",
        "textures/asphalt_n.png",
        "models/car.glb",
    }


def test_every_asset_of_the_shipped_scene_is_pinned() -> None:
    # Given the shipped scene and its lock file
    scene = POC / "assets" / "scene.json"
    lock = POC / "assets" / "assets.lock.json"

    # When the scene's assets are compared with the pins
    referenced = manifest_asset_paths(scene)
    pinned = {pin.path for pin in load_asset_pins(lock)}

    # Then adding content stayed a manifest edit: every asset is pinned
    assert referenced <= pinned


def test_a_pin_carries_the_attribution_its_licence_asks_for(tmp_path: Path) -> None:
    # Given a lock file pinning an attribution-licensed model with its credit
    credited = {
        **an_asset("models/car.glb", "0" * 64),
        "license": "CC-BY-4.0",
        "attribution": "Car Concept by Eric Chadwick (CC-BY-4.0)",
    }

    # When it is loaded
    (pin,) = load_asset_pins(a_lock_file(tmp_path, [credited]))

    # Then the pin keeps the credit
    assert pin.attribution == "Car Concept by Eric Chadwick (CC-BY-4.0)"


def test_every_attribution_licensed_pin_of_the_simulation_credits_its_author() -> None:
    # Given the simulation's lock file
    pins = load_asset_pins(POC / "assets" / "assets.lock.json")

    # When the CC BY pins are checked for a credit
    uncredited = [p.path for p in pins if p.license.startswith("CC-BY") and not p.attribution]

    # Then every one of them names its author
    assert uncredited == []


def test_every_gltf_a_vehicle_class_names_is_pinned() -> None:
    # Given every vehicle class file of the shipped simulation and its lock file
    lock = POC / "assets" / "assets.lock.json"
    pinned = {pin.path for pin in load_asset_pins(lock)}

    # When the glTFs the class files name are collected
    named: set[str] = set()
    for path in sorted((POC / "assets" / "vehicle").glob("*.vehicle.json")):
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        for key in ("glb", "carriage_glb"):
            value = raw.get(key)
            if isinstance(value, str):
                named.add(value)

    # Then a vehicle never names a model the fetcher would not fetch
    assert named <= pinned


def rust_assets_embedded_outside_tests() -> tuple[str, ...]:
    offenders: list[str] = []
    for source in sorted((POC / "src").glob("*.rs")):
        production = source.read_text(encoding="utf-8").split("#[cfg(test)]", 1)[0]
        for macro in ("include_bytes!", "include_str!"):
            marker = f'{macro}("'
            start = production.find(marker)
            if start != -1 and "assets/" in production[start : start + 120]:
                offenders.append(source.name)
    return tuple(offenders)


def test_the_page_never_copies_the_assets_directory_into_the_bundle() -> None:
    # Given the page the trunk build ships
    page = (POC / "index.html").read_text(encoding="utf-8")

    # When it is checked for a bundle copy of the runtime assets
    copied = "assets/" in page

    # Then the assets stay beside the bundle, fetched at runtime
    assert not copied


def test_no_rust_source_embeds_the_assets_directory_outside_tests() -> None:
    # Given every Rust source of the PoC, test modules excluded
    offenders = rust_assets_embedded_outside_tests()

    # When they are checked for embedded asset bytes
    embedded = offenders

    # Then the WASM never grows when a model is dropped into assets/
    assert embedded == ()


class _Response:
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return b"glb-bytes"


def test_the_default_downloader_names_the_site_a_cdn_requires_as_referer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a pinned file on a CDN that refuses hot-linked requests
    sent: list[urllib.request.Request] = []

    def serve(request: urllib.request.Request) -> _Response:
        sent.append(request)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", serve)

    # When the default downloader fetches it
    _default_opener("https://static.poly.pizza/car.glb")

    # Then the request names the site that serves the page as its referer
    assert sent[0].get_header("Referer") == "https://poly.pizza/"


def test_a_credited_pin_keeps_the_title_and_author_its_credit_line_names(tmp_path: Path) -> None:
    # Given a lock file pinning a CC BY model with its title and author
    credited = {
        **an_asset("models/car.glb", "0" * 64),
        "license": "CC-BY-4.0",
        "attribution": "Car Concept by Eric Chadwick (CC-BY-4.0)",
        "title": "Car Concept",
        "author": "Eric Chadwick",
    }

    # When it is loaded
    (pin,) = load_asset_pins(a_lock_file(tmp_path, [credited]))

    # Then the pin names what to credit and whom
    assert (pin.title, pin.author) == ("Car Concept", "Eric Chadwick")


def test_every_attribution_licensed_pin_of_the_simulation_names_its_title_and_author() -> None:
    # Given the simulation's lock file
    pins = load_asset_pins(POC / "assets" / "assets.lock.json")

    # When the CC BY pins are checked for a title and an author
    untitled = [
        p.path for p in pins if p.license.startswith("CC-BY") and not (p.title and p.author)
    ]

    # Then every one of them can be credited on screen
    assert untitled == []
