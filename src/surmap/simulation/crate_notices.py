"""The third-party notices of the simulation's WASM bundle, read from `cargo metadata`.

MIT, BSD, ISC and Zlib ask for their copyright notice wherever the code is redistributed, and the
page the agent serves at `/sim/` redistributes every crate the PoC links. The crates are the ones
the PoC reaches through normal dependencies (dev-only ones never reach the bundle); each one's
licence files carry its copyright lines, so their text is what the notice quotes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# A crate's licence files: LICENSE, LICENSE-MIT, LICENCE.txt, COPYING, NOTICE, UNLICENSE, ...
_LICENCE_FILE = re.compile(r"^(UN)?(LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)([-._].*)?$", re.I)


@dataclass(frozen=True)
class CrateNotice:
    name: str
    version: str
    licence: str
    # (file name, text) of each licence file the crate ships, in name order.
    texts: tuple[tuple[str, str], ...]


def crate_notices(metadata: Mapping[str, object]) -> tuple[CrateNotice, ...]:
    """Every crate the root package links through normal dependencies, by name and version."""
    packages = {str(p["id"]): p for p in _dicts(metadata.get("packages"))}
    resolve = metadata.get("resolve")
    if not isinstance(resolve, dict) or not isinstance(resolve.get("root"), str):
        raise ValueError("cargo metadata carries no resolved root package")
    edges = {str(node["id"]): _normal_deps(node) for node in _dicts(resolve.get("nodes"))}
    root: str = resolve["root"]
    linked: set[str] = set()
    pending = list(edges.get(root, ()))
    while pending:
        pkg_id = pending.pop()
        if pkg_id not in linked:
            linked.add(pkg_id)
            pending += edges.get(pkg_id, ())
    notices = [_notice(packages[pkg_id]) for pkg_id in linked if pkg_id in packages]
    return tuple(sorted(notices, key=lambda n: (n.name, n.version)))


def render_notices(notices: Sequence[CrateNotice]) -> str:
    """`THIRD_PARTY_LICENSES.md`: every crate with its declared licence, then each distinct licence
    text once, under the crates that ship it (most crates share the same Apache text)."""
    lines = [
        "# Third-party licences — SurMap simulation (WASM bundle)",
        "",
        f"This bundle links {len(notices)} third-party Rust crates. Each is listed with the",
        "licence it declares; the licence files they ship follow, each distinct text once.",
        "",
        "## Crates",
        "",
    ]
    shippers: dict[str, list[str]] = {}
    for notice in notices:
        lines.append(f"- {notice.name} {notice.version} — {notice.licence}")
        if not notice.texts:
            lines.append("  (no licence file is shipped with this crate)")
        for file_name, text in notice.texts:
            shippers.setdefault(text, []).append(f"{notice.name} {notice.version} ({file_name})")
    lines += ["", "## Licence texts", ""]
    for text, crates in shippers.items():
        lines += [f"### {', '.join(crates)}", "", "```text", text.rstrip("\n"), "```", ""]
    return "\n".join(lines)


def _dicts(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _normal_deps(node: Mapping[str, object]) -> list[str]:
    """The ids `node` depends on for its own code, not only for its tests or build script."""
    return [
        str(dep["pkg"])
        for dep in _dicts(node.get("deps"))
        if any(kind.get("kind") is None for kind in _dicts(dep.get("dep_kinds")))
    ]


def _notice(package: Mapping[str, object]) -> CrateNotice:
    crate_dir = Path(str(package["manifest_path"])).parent
    found = {
        path for path in crate_dir.iterdir() if path.is_file() and _LICENCE_FILE.match(path.name)
    }
    # A crate with a custom licence names its file in `license-file`, wherever it lives.
    declared = package.get("license_file")
    if isinstance(declared, str) and (crate_dir / declared).is_file():
        found.add(crate_dir / declared)
    files = sorted(found)
    licence = package.get("license")
    return CrateNotice(
        name=str(package["name"]),
        version=str(package["version"]),
        licence=licence if isinstance(licence, str) else "unspecified",
        texts=tuple(
            (path.name, path.read_text(encoding="utf-8", errors="replace")) for path in files
        ),
    )
