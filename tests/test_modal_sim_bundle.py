"""The deploy-time preflight for the simulation the agent's Modal app ships.

`check_sim_bundle` runs where the app is deployed, before the image uploads the PoC's `dist/`
and `assets/`: it refuses a page built before its sources last changed, and pinned assets that
were never fetched, naming the command that fixes each.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from surmap.survey.modal_hosting import SimBundleError, check_sim_bundle

BUILT_AT = 1_800_000_000.0
EDITED_AFTER = BUILT_AT + 60


class PocDir:
    """A `examples/bevy-sitl-poc` stand-in: sources, a `trunk` build, pinned assets."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._write("index.html", at=BUILT_AT - 60)
        self._write("Cargo.toml", at=BUILT_AT - 60)
        self._write("Cargo.lock", at=BUILT_AT - 60)
        self._write("src/main.rs", at=BUILT_AT - 60)
        self._write("assets/scene.json", at=BUILT_AT - 60)
        self.pin("textures/asphalt_2k.jpg")

    def built(self) -> PocDir:
        self._write("dist/index.html", at=BUILT_AT)
        self._write("dist/bevy-sitl-poc_bg.wasm", at=BUILT_AT)
        return self

    def edited(self, relative: str) -> PocDir:
        self._write(relative, at=EDITED_AFTER)
        return self

    def fetched(self) -> PocDir:
        self._write("assets/textures/asphalt_2k.jpg", at=BUILT_AT - 60)
        return self

    def pin(self, path: str) -> None:
        pins = [{"path": path, "url": "", "sha256": "", "license": "CC0-1.0", "source": ""}]
        self._write("assets/assets.lock.json", at=BUILT_AT - 60, text=json.dumps({"assets": pins}))

    def _write(self, relative: str, *, at: float, text: str = "") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        os.utime(path, (at, at))


@pytest.fixture
def poc(tmp_path: Path) -> PocDir:
    return PocDir(tmp_path / "bevy-sitl-poc")


def test_a_page_built_after_its_sources_with_every_pinned_asset_fetched_is_shipped(
    poc: PocDir,
) -> None:
    # Given a build newer than every source and every pinned asset on disk
    poc.built().fetched()

    # Then the preflight lets the deploy go ahead
    check_sim_bundle(poc.root)


def test_a_page_never_built_is_refused_with_the_trunk_command(poc: PocDir) -> None:
    # Given the assets fetched but no `trunk build` output
    poc.fetched()

    # Then the deploy stops and says how to build the page
    with pytest.raises(SimBundleError, match="trunk build index.html --release"):
        check_sim_bundle(poc.root)


def test_a_page_built_before_a_source_last_changed_is_refused_as_stale(poc: PocDir) -> None:
    # Given a build, then a change to the page's Rust source
    poc.built().fetched().edited("src/fleet/stream.rs")

    # Then the deploy refuses the stale WASM, naming the newer source
    with pytest.raises(SimBundleError, match=r"older than src/fleet/stream\.rs"):
        check_sim_bundle(poc.root)


def test_a_page_built_before_its_lock_file_changed_is_refused_as_stale(poc: PocDir) -> None:
    # Given a build, then a dependency bump in Cargo.lock
    poc.built().fetched().edited("Cargo.lock")

    # Then the deploy refuses it too
    with pytest.raises(SimBundleError, match=r"older than Cargo\.lock"):
        check_sim_bundle(poc.root)


def test_a_pinned_asset_never_fetched_is_refused_with_the_fetch_command(poc: PocDir) -> None:
    # Given a current build but the pinned texture not fetched
    poc.built()

    # Then the deploy stops, naming the missing file and the fetch script
    with pytest.raises(
        SimBundleError, match=r"textures/asphalt_2k\.jpg.*scripts/fetch_sim_assets\.py"
    ):
        check_sim_bundle(poc.root)
