# Changeset: agent tools for disaster scenarios — asset search/download, weather, animated wildfire, behaviour trees

**Date**: 2026-11-03
**Status**: 🚧 In Progress
**Type**: Feature
**Behaviour**: adds
**Complexity**: 5 — three packages (`surmap.agent`, a new station simulation store, the Bevy PoC),
three external asset APIs, SQLite, GPU particles on WebGPU, licence gating

PRD: `PRD-2026-11-03-sim-scenario-agent-tools.md` · Discovery:
`2026-11-03-sim-scenario-agent-tools-initial-discovery.md`

## Workflow

- [wf 1] ⏳ `/plan-red` Plan — PRD, changeset, initial discovery · PRD + this file + discovery
  - [x] Record initial discovery
  - [x] Cross-check `src/surmap/docs/todo/` and `src/surmap/docs/code-issues/`
  - [x] Create/update PRD documentation
  - [x] Create changeset
  - [ ] Visual spec for fire, smoke, rain and burnt ground (planner) — `2026-11-03-sim-scenario-visual-spec.md`
  - [ ] Build and baseline healthy (Step 7)
- [wf 2] ⬜ `/plan-red` Red — acceptance and failing lower-tier tests, committed ·
  - [ ] Acceptance tests written and failing for the right reason
  - [ ] Unit/integration tests written and failing
  - [ ] Tests committed with the changeset
- [wf 3] ⬜ `/green` Green — implement until every red test passes ·
  - [ ] Licence policy: `cc0` and `cc-by` (3.0/4.0) accepted; NC, ND, SA, "standard"/editorial refused with the reason
  - [ ] Source adapters: Poly Haven (models, textures, HDRIs; public API), ambientCG (materials; public API v2), Sketchfab Data API v3 (anonymous search with `license=cc0|by&downloadable=true`; download with `SKETCHFAB_API_TOKEN`)
  - [ ] Station store: SQLite `simulation.sqlite` — `assets`, `asset_files` (path, sha256, bytes), `attributions`, `scenarios` (versioned JSON); migrations; one writer
  - [ ] RPC: `SimulationTools` proto (`search_assets`, `download_asset`, `list_assets`, `create_scenario`, `add_model`, `set_weather`, `add_fire`, `get_scenario`, `list_scenarios`, `publish_scenario`) with execution policies; generated code checked in; handlers on the station store
  - [ ] Scenario manifest (PoC, runtime-loaded, no WASM rebuild): `weather` (rain, fog visibility, wind), `fires` (ignition, start, spread rate, wind-driven ellipse, max radius, smoke), `?scenario=<id>` loads `assets/scenarios/<id>.json`; `credits` rendered in the page
  - [ ] Animated fire, smoke, embers and rain with `bevy_hanabi` 0.18 (planned dependency), exactly per the scenario visual spec; burnt ground behind the front
  - [ ] Ground truth: the fire perimeter at each frame's `t_ns` in the capture (`fire_perimeter.jsonl`)
  - [ ] Behaviour trees (developer request 2026-11-03): per-object declarative trees in the scenario JSON (`behaviours`: `sequence`, `selector`, `parallel`, `repeat`, `condition` — `near_fire`, `near_object`, `time_after`, `reached` — and actions `move_to`, `follow_path`, `wander`, `flee_from_fire`, `idle`, `play_animation`), interpreted each tick in the PoC (no WASM rebuild); agent tools `set_behaviour`, `update_behaviour_node`, `get_behaviour`; trees validated on the station before publish; moving objects' poses recorded as ground truth (`object_tracks.jsonl`)
  - [ ] Scenario presets the agent can start from: `earthquake-block` (#89's scene), `wildfire-edge`, `flood-street`
- [wf 4] ⬜ `/pr-wrap` Wrap — validate, clean up, verification, docs ·
  - [ ] Verification executed — result recorded (agent session log + screenshots of a wildfire scenario built only through tools)
  - [ ] `docs/agent.md` — Simulation tools section; `docs/simulation/bevy-simulation.md` — scenarios, weather, fire
  - [ ] `HACKATHON.md` — third-party rows for Poly Haven, ambientCG, Sketchfab (+ licence policy), `bevy_hanabi`
  - [ ] `docs/simulation/changelog/2026-11-03-sim-scenario-agent-tools.md`
  - [ ] Lint, type-check and tests green
  - [ ] Every TODO row decided
  - [ ] Docs wrapped, 1-WIP deleted, rows carried into the wrap commit and PR body; `gh pr ready`

## Stack Context

Stack slug `sim-disaster`: `main ← n1 feat/bevy-sim-photoreal-rtabmap-stream (#89) ← n2 feat/sim-scenario-agent-tools (this)`.

### Green wave

**Wave:** 2 of 2 · **Node:** n2 · **Concurrent with:** none · **Blocks:** nothing ·
**Needs:** n1 (#89) — the runtime scene manifest, `AssetServer` loading, the asset lock/fetch
(`sim_assets`) and the screenshot mode. **Greenable independently?** no.

### Inherited Dependencies — do not implement here

The scene manifest, runtime GLB loading, photo-real materials and lighting, the stereo stream and
bridge all belong to n1 (#89). This layer extends the manifest; it never re-implements n1's parts.

## Background

The survey agent can run demos and inspect results but cannot make the world it surveys. The
developer wants the agent to build simulations for different disaster scenarios: search and download
models, and declare rain, fog and fire — wildfires with animated fire and smoke included — with the
station's SQLite database behind the RPC backend.

## State A (before)

- One hand-made scene (`assets/scene.json`, #89); no scenarios, weather, fire, or particles.
- Assets are pinned by hand in `assets.lock.json`; no search, no catalogue, no attribution store.
- No `SimulationTools` service; the station has no database.

## State B (after)

- **Asset sources (planner choice, 2026-11-03)** — the three with free search + free download and
  disaster coverage: **Sketchfab** (CC0/CC BY filter; collapsed buildings, rubble, burnt trees, flood
  debris, destroyed houses — 15–24 downloadable hits per query), **Poly Haven** (CC0; dead/fallen
  trees, stumps, branches, rocks, `burned_ground_01`, `rubble`, misty/overcast HDRIs), **ambientCG**
  (CC0; rubble ground, mud, bark).
- **Licence gate**: only CC0 and CC BY enter the catalogue; CC BY assets carry author, title,
  source URL and licence into `attributions`, the scenario's `credits`, and the page's credits panel.
  Assets are downloaded on demand into the station cache, SHA-256 recorded, never committed.
- **`SimulationTools`** (agent tools, station RPC, SQLite-backed) as listed under Green.
- **Scenario JSON** = #89's manifest + `weather`, `fires`, `credits`; the agent publishes it to the
  served `assets/scenarios/`; the page loads it with `?scenario=` — no WASM rebuild.
- **Behaviour trees**: objects (survivors, vehicles, props) carry a declarative tree the agent writes and edits through tools; the sim interprets it at runtime, so changing behaviour never rebuilds the WASM. Moving objects stay out of the static map (architecture §1) and their tracks are ground truth.
- **Wildfire**: fire fronts spread over time (wind-driven ellipse), flames + embers + smoke plumes
  as `bevy_hanabi` GPU particles, burnt ground behind the front, fire perimeter as ground truth.

## Verification

- **V1** — acceptance: an agent session (fake LLM scripted tool calls, real store and handlers)
  searches, downloads (sources faked at the HTTP seam), builds `wildfire-edge` with weather and two
  fires, publishes it; the published JSON validates in the PoC's manifest tests; NC/ND assets are
  refused. Live-source smoke tests are gated by env (`SURMAP_LIVE_ASSET_SOURCES=1`).
- **V4** (screenshots, planner review) — wildfire scenario at t = 0, 30, 90 s: fire front, smoke
  plume, burnt ground; rain scenario.

## Prerequisites

- Deferred-work scan: no `src/surmap/docs/todo/` or `code-issues/` item in this path
  (`private-reach-agent-tools-workspace.md` is about `surmap.agent.tools.workspace`; this layer adds a
  new tools module and does not reach into the workspace's private state — ℹ noted).
- n1 (#89) Green must land first (wave 2).

## Decisions & Trade-offs

- SQLite (stdlib `sqlite3`) on the station: no new dependency, one file, one writer.
- Sketchfab download needs a free account token: search works anonymously, so the agent can browse;
  download without `SKETCHFAB_API_TOKEN` returns a clear error naming the variable.
- **Planned dependency**: `bevy_hanabi = "0.18"` in the PoC (GPU particles; WebGPU-only, which the
  PoC already is). No Python dependency added.
- Poly Pizza, Kenney, Quaternius excluded (stylised, clashes with #89's photo-real target);
  Smithsonian and Objaverse not adapted in this layer (museum objects / uneven quality).
