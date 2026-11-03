# Initial discovery — agent tools for disaster scenarios

**Changeset:** `2026-11-03-sim-scenario-agent-tools.md`

## Asset sources (probed live, 2026-11-03)

- **Sketchfab Data API v3** — `GET https://api.sketchfab.com/v3/search?type=models&q=<q>&downloadable=true&license=<cc0|by>`
  answers without auth; each result carries `license.label` and `isDownloadable`. Licence slugs
  (`/v3/licenses`): `by, by-sa, by-nd, by-nc, by-nc-sa, by-nc-nd, cc0, free-st, st, ed`.
  `GET /v3/models/{uid}/download` needs a user token (401 without), returns glTF/GLB/USDZ links.
  Hits (CC BY, downloadable): "collapsed building" 24, "rubble" 24, "burnt tree" 19,
  "flood debris" 15, "fallen tree" 24, "wildfire" 24, "destroyed house" 24; CC0 hits are rare
  (mostly Smithsonian scans).
- **Poly Haven** — `https://api.polyhaven.com/assets?t=models|textures|hdris`, no key, all CC0.
  Disaster-useful: `dead_tree_trunk`, `dead_tree_trunk_02`, `tree_stump_01/02`,
  `dry_branches_medium_01`, `bark_debris_01`, boulders/rocks (42), `modular_chainlink_fence`;
  textures `burned_ground_01`, `rubble`, `brick_gravel`, 37 mud; HDRIs `kloofendal_overcast`,
  `kloofendal_misty_morning`, smoky `poolbeg`.
- **ambientCG** — `https://ambientcg.com/api/v2/full_json?type=Material&q=<q>`, no key, CC0;
  rubble ground (`Ground107/108/111`), 31 mud, 16 bark; no burnt/ash material.
- Rejected: Poly Pizza (API key, low-poly), Kenney/Quaternius (stylised), Smithsonian (CC0 but
  museum objects), Objaverse (per-object licences, uneven quality).

## Particles

`bevy_hanabi` 0.18.0 depends on `bevy ^0.18` (0.19 → 0.19, 0.20 → 0.20). GPU compute particles;
needs WebGPU on wasm. `bevy_enoki` 0.6 is 2D; `bevy_firework` 0.10 targets Bevy 0.19.

## Agent tools

Tools are proto rpcs (`proto/surmap/agent/v1/*.proto`), generated with `scripts/gen_agent_rpc.py`
into `src/surmap/agent/proto/` (checked in), contracts via `surmap.agent.contracts`, handlers in
`src/surmap/agent/tools/`, wired as `ServiceModule`s in `src/surmap/agent/services.py`
(`docs/agent.md`). No SQLite is used anywhere in `src/` today.

## Licence bar

No published hackathon rule on assets was found. `HACKATHON.md` practice: third-party data
downloaded on demand, SHA-256 pinned, not re-hosted, credited in the third-party table.
