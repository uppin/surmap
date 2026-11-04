# 2026-11-04 — Boats and ships on the water (#sim-traffic 3/3, PR #109)

- `boat` and `ship` vehicle classes (Quaternius, CC0, sha256-pinned) ride a `water: true` box,
  driven by the same trees and `Drive` limits as the road classes.
- A pure kinematic sea state (`sea.rs`): wind-driven wave height and period give each vessel
  heave, pitch and roll by its class's `wave_response`. The model's keel sits on the surface
  (`keel_below_origin_m`).
- Vessels are validated in the renderer and the station. A vessel starts on water, steers only to
  water, and may not `wander` or `flee_from_fire`. A road or rail class may not start on water.
- `add_element`'s `box` takes `water`, and `vehicle_class` takes `boat` / `ship`.
- Preset `flood-rescue`: two rescue boats shuttling along a flooded channel.
- Detector scoring: `boat` and `ship` map to COCO `boat`. Both are under the 20 % bar; the open
  TODO is `src/surmap/docs/todo/2026-11-04-vessels-detectors-miss.md`.
- Decided without review:
  - the vessel asset source (Quaternius instead of Kenney, whose download refuses a scripted
    fetch): `docs/simulation/deferred-answers/2026-11-04-vessel-asset-source.md`;
  - the sea constants;
  - the sea following the base wind, not the live wind;
  - no ship in the preset, because the channel is 10 m wide and the ship's beam is 20.7 m.
