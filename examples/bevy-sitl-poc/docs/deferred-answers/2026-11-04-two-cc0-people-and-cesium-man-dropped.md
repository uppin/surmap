# 2026-11-04 — The shipped people are two CC0 models; Cesium Man's pin and credit are dropped

**Kind:** Technical
**Source:** the rigged-people changeset, wrapped into `docs/simulation/changelog/2026-11-04-sim-rigged-people.md` (PR #107, stack `#sim-traffic` node 2/3)
**Asked by:** orchestrator (`/yolo-pr-stack`), relayed to `[G]` n2 — Sonnet 5.5, under `#yolo`
**Packages:** bevy-sitl-poc
**Status:** Awaiting review

## Question

The developer chose "two models: one for sitting, one for waving" (option 2b). Main ships Cesium Man
(CC-BY-4.0). Does Cesium Man stay pinned?

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) **(picked)** | Drop the pin and the doc credit | Nothing uses it; the people are CC0 only |
| b) | Keep it as a per-person `glb` option | An unused CC-BY asset with a credit to maintain |

**Asker's pick:** a).

## Decision

`models/cesium_man/CesiumMan.glb` is removed from `assets.lock.json` and from the credit in
`docs/simulation/bevy-simulation.md`; the #111 changelog stays as history. The shipped figure is
`models/person/wave.glb` (Quaternius, poly.pizza/m/qJ2gsTUBHL: idle, walk, run, wave, death held as
lying; the shirt takes the coat) and `models/person/sit.glb` (poly.pizza/m/9kF7eTDbhO: sit; the
model's single material is tinted by `coat_tint`; scale 0.346 brings its 5.2 m rest height to 1.8 m).
The model's own skin is kept: replacing it with the library skin read as grey.

## What was built on it

`assets/behaviour/person.figure.json`, `assets/assets.lock.json`, `docs/simulation/bevy-simulation.md`.

## To override

Re-pin Cesium Man in the lock and point `model` at it with `rig` omitted; the main test
`the_shipped_figure_wears_a_humanoid_pinned_with_an_open_licence` accepts either licence.
