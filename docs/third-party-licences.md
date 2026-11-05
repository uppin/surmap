# Third-party licences

SurMap is licensed under Apache-2.0 ([LICENSE](../LICENSE),
[NOTICE](../NOTICE)). This page records the licences of the code that
SurMap depends on and of the external pieces it runs, and what each
one means for the repository. Provenance and credits for datasets,
models and assets are in [HACKATHON.md](../HACKATHON.md).

Last audited on 5 Nov 2026, against `uv.lock`,
`examples/bevy-sitl-poc/Cargo.lock` and `web/agent-chat/package.json`.

## Summary

None of the dependencies is strong copyleft (GPL, AGPL), so none of
them restricts SurMap's own licence. The obligations that remain:

- **Notices.** MIT, BSD, ISC and Zlib require their copyright
  notices when the code is redistributed. Both shipped bundles carry them
  in a `THIRD_PARTY_LICENSES.md` next to their `index.html`:
  - The agent-chat build writes its file through Vite's `build.license`.
  - The Bevy WASM bundle's file is written by `scripts/sim_notices.py` after
    `trunk build`. It reads `cargo metadata`, so it covers the crates linked for
    `wasm32-unknown-unknown` and quotes each distinct licence text once.
  - The Modal deploy refuses either page without its file
    (`check_chat_bundle`, `check_sim_bundle`).
- **MPL-2.0** (certifi, pathspec, and parts of orjson and tqdm) is
  file-level copyleft. It is met as long as SurMap uses these
  packages unmodified from PyPI.
- **Restricted data and weights** (KITTI, NTU VIRAL, SAM 3.1)
  are covered in their own sections below.

## Python (`uv.lock`)

`uv sync --group dev --all-extras` installs 105 third-party distributions.

| Licence | Count |
|---|---|
| MIT or MIT-like (MIT-CMU, PSF) | 52 |
| Apache-2.0, alone or dual with MIT or BSD | 30 |
| BSD-2-Clause or BSD-3-Clause | 16 |
| MPL-2.0 alone or combined (`certifi`, `pathspec`, `orjson`, `tqdm`) | 4 |
| Other | 3 (below) |

- `meta-sam-parser` (runtime): Meta's **SAM License**, a custom
  licence. It permits use, modification and redistribution, and
  carries Meta's acceptable-use terms.
- `apsw`: declared "any-OSI" (its upstream licence is zlib-style).
- `protobuf-py-ext`: has no licence metadata. It is part of
  [bufbuild/protobuf-py](https://github.com/bufbuild/protobuf-py),
  which is Apache-2.0.
- Optional extras: `opencv-python-headless` (`calibration`) is
  Apache-2.0, and `modal` (`modal`) is Apache-2.0.

To reproduce, run
`importlib.metadata.distributions()` in `uv run python` and read each
package's `License-Expression`, or its `License ::` classifiers when
that field is missing.

## Rust (`examples/bevy-sitl-poc`)

`cargo metadata --locked` lists 589 crates. All of them are permissive
(MIT, Apache-2.0, BSD, Zlib, ISC, Unicode-3.0, CC0, Unlicense), alone
or as a choice. Three offer copyleft only as one alternative, and the
permissive option is taken:

| Crate | Declared | Used under |
|---|---|---|
| `r-efi` 5.3.0, 6.0.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later | MIT OR Apache-2.0 |
| `self_cell` 1.3.0 | Apache-2.0 OR GPL-2.0-only | Apache-2.0 |

The crate itself is `MIT OR Apache-2.0`, as its `Cargo.toml` declares.

## JavaScript (`web/agent-chat`)

The direct dependencies are permissive. Most are MIT (React, three,
Radix, Vite, Tailwind, Vitest). The others are `lucide-react` (ISC),
`maplibre-gl` and `pmtiles` (BSD-3-Clause), and `@bufbuild/*`,
`@connectrpc/*` and TypeScript (Apache-2.0). The transitive tree in
`yarn.lock` has not been scanned. To scan it, run `yarn licenses list`
after an install.

## Run, not linked

These are separate processes, containers or simulators. SurMap does
not redistribute them.

| Piece | Licence | Note |
|---|---|---|
| RTAB-Map (`introlab3it/rtabmap` image) | BSD-3-Clause | The image bundles OpenCV, PCL and other libraries under their own licences. SurMap pulls the image and does not re-host it. `scripts/build_rtabmap_stream.py` links a tool against `librtabmap` locally, inside the container. |
| PX4 | BSD-3-Clause | SITL only |
| Gazebo Harmonic, ROS 2 Jazzy | Apache-2.0 | Simulation host |
| Ollama, Docker | MIT, Apache-2.0 | Optional tools |

## Models

| Model | Licence | In the repo? |
|---|---|---|
| SAM 3.1 `facebook/sam3.1` | SAM License (gated on Hugging Face) | No. Downloaded with `HF_TOKEN`. CI uses `tests/fixtures/sam3_fake/` |
| Coral EfficientDet-Lite0, SSD MobileNet V2, SSDLite MobileDet | Apache-2.0 | No. Fetched by `scripts/fetch_coral_model.py` |
| Muse Wonder, Muse Voice, Muse Spark Open | Provider terms (Meta Model API, Baseten, Modal) | No. Called over an API |

## Data and assets

| Item | Licence | In the repo? |
|---|---|---|
| KITTI raw | CC BY-NC-SA 3.0 | No. Downloaded on demand |
| NTU VIRAL | CC BY-NC-SA 4.0 | No. Downloaded on demand |
| EuRoC MAV, LADI v2, Boreal Forest Fire | CC BY 4.0 or research terms | No. Downloaded on demand |
| NOAA emergency imagery, Poly Haven, ambientCG, OpenGameArt fire, Poly Pizza (Quaternius) | CC0-1.0 | No. Fetched and SHA-256 pinned |
| *Car Concept* by Eric Chadwick, Darmstadt Graphics Group GmbH (Khronos glTF-Sample-Assets) | CC-BY-4.0 | No. Fetched and pinned. The pin carries the credit, which shows on the `/sim/` page and in the chat's simulation pane for every scenario that shows the model |
| *Bus* by Poly by Google (Poly Pizza) | CC-BY-3.0 | No. Fetched and pinned, credited like *Car Concept* |
| Sketchfab models picked by the agent | CC0 or CC BY (licence gate refuses NC/ND/SA) | No. Stored in the station library |
| `tests/fixtures/bevy_sim_*`, `sitl_capture_tiny`, Gazebo materials | Rendered by this repository's simulations | Yes. Apache-2.0 with the rest of the repo |
| `tests/fixtures/plane_stereo` | Rendered by `scripts/render_plane_stereo_fixture.py` from Poly Haven `rocks_ground_02` (CC0-1.0) | Yes. Apache-2.0 with the rest of the repo |

The NC-licensed dev-console scenes restrict commercial use of those
scenes only. ETH3D frames were committed as a test fixture until
2026-11-05, when they were replaced; they remain in the git history. They do not restrict
SurMap's code.
