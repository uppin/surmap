# Changeset: simulation scenarios on the station — asset search/download, SQLite store, served scenes

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 4 — two packages (`surmap.agent` tools + server routes, `surmap.simulation` store
and sources) and a small Bevy change, three external asset APIs behind one seam, SQLite

PRD: `PRD-2026-11-03-sim-scenario-agent-tools.md` · Discovery:
`2026-11-03-sim-scenario-agent-tools-initial-discovery.md`

## Workflow

- [wf 1] ✅ 2026-11-03 `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery; scope split 3 ways (developer, 2026-11-03)
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [x] Build and baseline healthy (Step 7) — mypy 409 files clean; pytest 1780 passed, 33 skipped
- [wf 2] ✅ 2026-11-03 `/plan-red` Red — acceptance and failing lower-tier tests, committed · 6 Python files red on missing modules; 4 Rust tests red on stubs/fixture
  - [x] Acceptance tests written and failing for the right reason — `tests/test_sim_scenario_e2e.py` (4)
  - [x] Unit/integration tests written and failing — licences, sources, store, manifest, handlers; Rust `shots`, `scene_manifest`
  - [x] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] `surmap.simulation.licences` — CC0 and CC BY 3.0/4.0 accepted; NC, ND, SA, Sketchfab `free-st`/`st`/`ed` and unknown refused with the reason
  - [ ] `surmap.simulation.asset_sources` — `PolyHaven`, `AmbientCg`, `Sketchfab` behind one `AssetSource` protocol and an injectable `Fetch` (URL → bytes); search hits and download file lists normalised to `AssetHit` / `AssetFile`
  - [ ] `surmap.simulation.scenario_store` — SQLite (`PRAGMA user_version` migrations): `assets`, `asset_files`, `scenarios`, `scenario_versions`; downloads land under `<store>/library/<source>/<asset_id>/` with SHA-256; every scenario edit is a new version
  - [ ] `surmap.simulation.scenario_manifest` — Python validation mirroring `scene_manifest.rs` (version, unique ids, known materials, relative paths, glTF models, ≤ 1 scatter); a scenario's `credits` derive from the CC BY assets it uses
  - [ ] Presets: `earthquake-block` (#89's shipped `scene.json`), `empty-lot` (camera, environment, ground only)
  - [ ] `SimulationTools` proto + generated code + contracts; handlers over the store; mounted on the agent server and bound as agent tools
  - [ ] Agent-server HTTP: `GET /sim/` (the built page when `--sim-dist` is set), `GET /sim/assets/scenarios/<id>.json`, `GET /sim/assets/library/…`, the PoC's static `assets/` beneath; `--sim-db`, `--sim-library`
  - [ ] Bevy: `?scenario=<id>` (wasm) / `--scenario <id>` (native) loads `scenarios/<id>.json` instead of `scene.json`
  - [ ] Gates green; `cargo test --locked`; `cargo check --target wasm32-unknown-unknown`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (scripted agent session log; the published scenario rendered natively from the station-served files)
  - [ ] `docs/agent.md` — Simulation tools; `docs/simulation/bevy-simulation.md` — scenarios served by the station
  - [ ] `HACKATHON.md` — ambientCG and Sketchfab rows + the licence policy
  - [ ] `docs/simulation/changelog/2026-11-03-sim-scenario-agent-tools.md`
  - [ ] Lint (`--no-cache`), type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster`: `main ← (n1 #89, merged) ← n2 #91 (this) ← n3 weather + wildfire ← n4 behaviour trees`.

### Green wave

**Wave:** 1 of 2 · **Node:** n2 · **Concurrent with:** none · **Blocks:** n3, n4 — the store, the
scenario tools and `/sim/` serving · **Needs:** n1 (#89, merged): the declarative manifest and
its element kinds. **Greenable independently?** yes.

## Background

#89 made the Bevy simulation fully declarative. The developer wants the survey agent to build
simulations for different disaster scenarios: search and download licence-compatible GLB
assets, compose scenes, persist them in the station's SQLite database and serve them from the
station over RPC/agent tools (2026-11-03: "created simulation scenes should be persisted and
accessible via RPC/agentic tools and served by the station server"). Weather, the animated
wildfire and behaviour trees follow as n3 and n4 (developer chose the three-way split).

## State A (before)

- One hand-made `assets/scene.json`; no scenarios, no catalogue, no attribution store.
- The agent server serves survey/map tools and frames, GLBs and dataset thumbnails over HTTP.

## State B (after)

### Licence policy (`surmap.simulation.licences`)

`check_licence(raw) -> LicenceVerdict(accepted, spdx, reason)`: accepts `CC0-1.0`, `CC-BY-4.0`,
`CC-BY-3.0` (Sketchfab `cc0`/`by`, Poly Haven and ambientCG are CC0); refuses everything else
with a reason naming the clause (NC: non-commercial; ND: no derivatives; SA: share-alike would
bind the scenario; `free-st`/`st`/`ed`: not an open licence).

### Sources (`surmap.simulation.asset_sources`)

```python
class AssetSource(Protocol):
    name: str                                   # "polyhaven" | "ambientcg" | "sketchfab"
    def search(self, query: str, kind: AssetKind, limit: int) -> list[AssetHit]: ...
    def files(self, asset_id: str, kind: AssetKind) -> list[AssetFile]: ...
```

`AssetHit(source, asset_id, kind, title, author, licence, page_url, preview_url)`;
`AssetFile(path, url)` with `path` relative to the asset's folder. Poly Haven: the 2K glTF
entry + includes for models, 2K `diff`/`nor_gl`/`arm` JPGs for textures, the 2K `.hdr` for
HDRIs. ambientCG: the 2K-JPG zip members (`_Color`, `_NormalGL`, `_Roughness`) — materials only.
Sketchfab: search `type=models&downloadable=true&license=<cc0|by>`; files from
`/v3/models/{uid}/download` (the GLB) with `Authorization: Token $SKETCHFAB_API_TOKEN`, refused
with a clear error naming the variable when unset. All HTTP goes through `Fetch`.

### Store (`surmap.simulation.scenario_store.ScenarioStore(db_path, library_dir)`)

`record_hit`, `download(source, hit) -> StoredAsset` (licence-gated, files hashed),
`assets()`, `asset(ref)`, `create_scenario(name, preset) -> Scenario`, `scenario(id)`,
`scenarios()`, `save(id, manifest) -> Scenario` (validates, new version), `history(id)`.
`Scenario(id, name, version, manifest, credits, updated_at)`. Asset refs are `"<source>:<id>"`.
A downloaded model is referenced from a manifest as `library/<source>/<id>/<entry file>`.

### Tools (`proto/surmap/agent/v1/simulation_tools.proto`, service `SimulationTools`)

| Tool | Does | Execution |
|---|---|---|
| `search_assets` | query + kind (+ sources) across the three sources; licence verdict per hit | SYNC · 20 s · FAIL |
| `download_asset` | fetch an accepted hit into the library | SYNC · 60 s · DETACH |
| `list_assets` | the library | SYNC · 10 s · FAIL |
| `create_scenario` | from a preset | SYNC · 10 s · FAIL |
| `add_model` | a library model at an ENU pose, collider, optional ground-truth kind | SYNC · 10 s · FAIL |
| `add_element` | one `box` / `building` / `collapsed_building` / `person` | SYNC · 10 s · FAIL |
| `remove_element` | by id (element or model) | SYNC · 10 s · FAIL |
| `get_scenario` | manifest JSON, version, credits, the URL the page loads | SYNC · 10 s · FAIL |
| `list_scenarios` | id, name, version, updated | SYNC · 10 s · FAIL |

### Serving (agent server)

`/sim/assets/scenarios/<id>.json` (the latest version), `/sim/assets/library/<source>/<id>/…`,
and `/sim/assets/…` from the PoC's static assets; `/sim/` serves the built page when
`--sim-dist` points at a `trunk build` output. The page's `?scenario=<id>` makes Bevy load
`scenarios/<id>.json` from the same origin, so library paths resolve with no CORS.

## Verification

- **V1** — acceptance: a scripted agent session (fake LLM tool calls through the real agent
  runtime and handlers; sources faked at `Fetch`) searches, refuses an NC hit, downloads a CC BY
  model, creates `earthquake-block`, adds the model and a building, and `GET
  /sim/assets/scenarios/<id>.json` returns the new version with the model's library path and
  the CC BY credit; the library file is served byte-identical to its recorded SHA-256. Rust:
  a scenario JSON written by the Python store validates in `scene_manifest.rs`
  (`tests/fixtures/sim_scenario/earthquake-block.json`). Live-source smoke tests gated by
  `SURMAP_LIVE_ASSET_SOURCES=1`.
- **V4** — a scenario built through the tools, rendered natively from the station-served files
  (`--scenario <id>` with the store's library), screenshot attached to the PR.

## Prerequisites

- Deferred-work scan: nothing in this path. `private-reach-agent-tools-workspace.md` concerns
  `tools/workspace.py`, which this change does not touch.

## Decisions & Trade-offs

- SQLite via stdlib `sqlite3`; one connection per call, WAL, one writer — no new dependency.
- Sketchfab search is anonymous; download needs a free account token (`SKETCHFAB_API_TOKEN`).
- Every edit is a version; `scenarios/<id>.json` serves the latest. No separate "publish".
- Weather, fire and behaviour trees are **n3 / n4**, not here (developer's split).
