"""Write the simulation bundle's third-party notices beside the `trunk build` output.

Run after every `trunk build` (it empties `dist/`), before serving or deploying the page:

    (cd examples/bevy-sitl-poc && trunk build index.html --release)
    uv run python scripts/sim_notices.py

The crates are the PoC's normal dependencies for `wasm32-unknown-unknown`, resolved from its
`Cargo.lock` (`cargo metadata --locked`); the deploy refuses a page without the file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from surmap.simulation.crate_notices import crate_notices, render_notices

POC = Path(__file__).resolve().parents[1] / "examples" / "bevy-sitl-poc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--poc", type=Path, default=POC, help="the Bevy PoC crate")
    parser.add_argument("--dist", type=Path, default=None, help="default: <poc>/dist")
    args = parser.parse_args()
    dist: Path = args.dist or args.poc / "dist"
    output = subprocess.run(
        [
            "cargo",
            "metadata",
            "--locked",
            "--format-version",
            "1",
            "--filter-platform",
            "wasm32-unknown-unknown",
        ],
        cwd=args.poc,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    notices = crate_notices(json.loads(output))
    dist.mkdir(parents=True, exist_ok=True)
    target = dist / "THIRD_PARTY_LICENSES.md"
    target.write_text(render_notices(notices), encoding="utf-8")
    print(f"{target}: {len(notices)} crates")


if __name__ == "__main__":
    main()
