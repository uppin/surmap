# 2026-11-04 — which CC0 boat and ship models the vessels pin

**Kind:** Product
**Source:** `docs/simulation/1-WIP/2026-11-04-sim-water-vessels.md` (PR #109, stack `#sim-traffic` node n3 3/3)
**Asked by:** `/green` row 3, `[G]` n3, Claude Opus 5.5 subagent under `#yolo`
**Status:** Awaiting review

## Question

The changeset names Kenney's *Watercraft Kit* (CC0) as the source of the boat and ship glTFs, "or
equivalent". Kenney's download page returned 403 to a scripted fetch, and `fetch_sim_assets.py` can
only pin a plain URL. Which CC0 models should the vessels pin?

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) | Kenney *Watercraft Kit* (the changeset's name) | Would need a zip member pin or a manual download; not reachable by the fetch script as it stands |
| b) **(picked)** | Quaternius *Boat* and *Ship* from poly.pizza (`models/quaternius/boat.glb`, `models/quaternius/ship.glb`), licence CC0-1.0 on each model page | Pinned by URL and sha256 in `assets.lock.json`; fetched and verified by `scripts/fetch_sim_assets.py` |
| c) | Poly by Google *Boat* / *Sailboat* (poly.pizza) | Rejected: CC BY 3.0, not CC0 (the asset rule forbids it) |

**Asker's pick:** b) — the only option that is CC0, pinnable by the fetch script, and the same
publisher family as the car, truck and train already pinned.

## What was built on it

- `examples/bevy-sitl-poc/assets/assets.lock.json`: two entries, the boat pinned at sha256
  `263e5d46f79e8b37afecd0db9056b22dc33c6456074d260589285d1891192335` and the ship at
  `b3cfa69180926216867e1060f442c6de8db405d60edd777ad658e1a162f5ae67`.
- `examples/bevy-sitl-poc/assets/vehicle/boat.vehicle.json` (`model_scale` 0.56, so the hull is 5 m) and
  `ship.vehicle.json` (`model_scale` 3.9, so the hull is 60 m).

## To override

Swap the two `glb` paths and their lock entries, and re-tune `model_scale`, `model_yaw_deg` and the
`length_m`/`width_m`/`height_m` in the class files. Nothing else depends on the model identity. The
detector scores in the changeset's Verification would have to be re-recorded.
