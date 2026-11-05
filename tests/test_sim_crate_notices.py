"""The third-party notices of the simulation's WASM bundle, read from `cargo metadata`.

The bundle links every crate the PoC reaches through normal dependencies; each one's licence
files (and the licence it declares) go into the `THIRD_PARTY_LICENSES.md` shipped beside it.
"""

from __future__ import annotations

from pathlib import Path

from surmap.simulation.crate_notices import CrateNotice, crate_notices, render_notices

ROOT_ID = "path+file:///poc#bevy-sitl-poc@0.1.0"


class Registry:
    """A cargo registry stand-in: crate source dirs and the metadata `cargo` would print."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._packages: list[dict[str, object]] = []
        self._nodes: dict[str, list[dict[str, object]]] = {ROOT_ID: []}
        self._add_package(ROOT_ID, "bevy-sitl-poc", "0.1.0", "MIT OR Apache-2.0")

    def crate(self, name: str, licence: str, files: dict[str, str] | None = None) -> str:
        pkg_id = f"registry+https://github.com/rust-lang/crates.io-index#{name}@1.0.0"
        for file_name, text in (files or {}).items():
            path = self._root / f"{name}-1.0.0" / file_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self._add_package(pkg_id, name, "1.0.0", licence)
        self._nodes[pkg_id] = []
        return pkg_id

    def depends(self, parent: str, child: str, kind: str | None = None) -> Registry:
        name = child.split("#")[1].split("@")[0]
        edge: dict[str, object] = {
            "name": name,
            "pkg": child,
            "dep_kinds": [{"kind": kind, "target": None}],
        }
        self._nodes[parent].append(edge)
        return self

    def metadata(self) -> dict[str, object]:
        nodes = [{"id": pkg_id, "deps": deps} for pkg_id, deps in self._nodes.items()]
        return {"packages": self._packages, "resolve": {"root": ROOT_ID, "nodes": nodes}}

    def _add_package(self, pkg_id: str, name: str, version: str, licence: str) -> None:
        manifest = self._root / f"{name}-{version}" / "Cargo.toml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.touch()
        self._packages.append(
            {
                "id": pkg_id,
                "name": name,
                "version": version,
                "license": licence,
                "manifest_path": str(manifest),
            }
        )


def names(notices: tuple[CrateNotice, ...]) -> list[str]:
    return [notice.name for notice in notices]


def test_the_crates_the_bundle_links_are_listed_without_the_poc_itself(tmp_path: Path) -> None:
    # Given the PoC depending on serde, which depends on serde_derive
    registry = Registry(tmp_path)
    serde = registry.crate("serde", "MIT OR Apache-2.0")
    derive = registry.crate("serde_derive", "MIT OR Apache-2.0")
    registry.depends(ROOT_ID, serde).depends(serde, derive)

    # When the notices are collected
    notices = crate_notices(registry.metadata())

    # Then both crates are listed, by name, and the PoC is not
    assert names(notices) == ["serde", "serde_derive"]


def test_a_dev_only_dependency_never_reaches_the_bundle(tmp_path: Path) -> None:
    # Given a crate the PoC uses only in its tests
    registry = Registry(tmp_path)
    registry.depends(ROOT_ID, registry.crate("insta", "Apache-2.0"), kind="dev")

    # When the notices are collected
    notices = crate_notices(registry.metadata())

    # Then it is not listed
    assert names(notices) == []


def test_a_crate_carries_the_text_of_each_licence_file_it_ships(tmp_path: Path) -> None:
    # Given a crate shipping an MIT licence with its copyright line and an Apache one
    registry = Registry(tmp_path)
    files = {
        "LICENSE-MIT": "Copyright (c) 2020 The Bevy Contributors\n\nPermission is hereby granted",
        "LICENSE-APACHE": "Apache License\nVersion 2.0, January 2004",
        "README.md": "not a licence",
    }
    registry.depends(ROOT_ID, registry.crate("bevy", "MIT OR Apache-2.0", files))

    # When the notices are collected
    (bevy,) = crate_notices(registry.metadata())

    # Then both licence files are kept, in name order, and the README is not
    assert [name for name, _ in bevy.texts] == ["LICENSE-APACHE", "LICENSE-MIT"]
    assert "Copyright (c) 2020 The Bevy Contributors" in dict(bevy.texts)["LICENSE-MIT"]


def test_the_rendered_file_names_every_crate_its_licence_and_its_texts(tmp_path: Path) -> None:
    # Given one crate with a licence file and one that ships none
    registry = Registry(tmp_path)
    copyright_line = "Copyright (c) 2019 Ryan Leckey"
    with_file = registry.crate("smallvec", "MIT", {"LICENSE": copyright_line})
    registry.depends(ROOT_ID, with_file)
    registry.depends(ROOT_ID, registry.crate("nonmax", "MIT OR Apache-2.0"))

    # When the notices are rendered
    text = render_notices(crate_notices(registry.metadata()))

    # Then each crate is listed with its declared licence, and the shipped text is quoted
    assert "- smallvec 1.0.0 — MIT\n" in text
    assert f"### smallvec 1.0.0 (LICENSE)\n\n```text\n{copyright_line}\n```" in text
    assert (
        "- nonmax 1.0.0 — MIT OR Apache-2.0\n  (no licence file is shipped with this crate)" in text
    )


def test_a_licence_text_two_crates_share_is_quoted_once_under_both(tmp_path: Path) -> None:
    # Given two crates shipping the very same Apache text
    registry = Registry(tmp_path)
    apache = {"LICENSE-APACHE": "Apache License\nVersion 2.0, January 2004"}
    registry.depends(ROOT_ID, registry.crate("bevy_app", "Apache-2.0", apache))
    registry.depends(ROOT_ID, registry.crate("bevy_ecs", "Apache-2.0", apache))

    # When the notices are rendered
    text = render_notices(crate_notices(registry.metadata()))

    # Then the text appears once, naming both crates
    assert text.count("Version 2.0, January 2004") == 1
    assert "### bevy_app 1.0.0 (LICENSE-APACHE), bevy_ecs 1.0.0 (LICENSE-APACHE)" in text
