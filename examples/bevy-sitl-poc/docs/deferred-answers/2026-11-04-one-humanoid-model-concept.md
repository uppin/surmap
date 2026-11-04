# 2026-11-04 — One humanoid model concept: n2's rig merged into main's `FigureModel`

**Kind:** Technical
**Source:** `docs/simulation/1-WIP/2026-11-04-sim-rigged-people.md` (PR #107, stack `#sim-traffic` node 2/3)
**Asked by:** orchestrator (`/yolo-pr-stack`), relayed to `[G]` n2 — Sonnet 5.5, under `#yolo`
**Packages:** bevy-sitl-poc
**Status:** Awaiting review

## Question

After the rebase onto main (#111) a figure had two humanoid concepts: main's
`FigureDef.model: Option<FigureModel>` (one glTF, posed from its first clip) and n2's
`FigureDef.rig: Option<RigDef>` plus `pose_rigs`, with parallel components (`StandIn` /
`FallbackBody`, `PersonLook` / `FigureCoat`).

## Options as asked

| | Option | Consequence |
|---|---|---|
| a) **(picked)** | `FigureModel` gains an optional `rig` (named clips, speeds, coat slots) and the figure gains `pose_models`; a model without a rig is main's degenerate case | One model field; main's JSON, tests and names keep working |
| b) | Keep both fields | Two ways to dress a person; the rebase's accidental state |

**Asker's pick:** a) — main's names win (`FallbackBody`, `FigureCoat`, `coat_tint`, `body_m`); n2's
duplicates are gone (`StandIn`, `PersonLook`; a `FigureSkin` stays for skin slots).

## Decision

`RigDef` no longer carries `glb` (the model's `glb` is the file; `FigureModel.scale` is the model's
own, and `rig.standing_height_m` is its height at that scale). `pose_rigs` became `pose_models`
(error messages name `pose_models`). `FigureDef::rig_for` became `model_for`. A rigged model is
spawned by `actors/rig.rs`, which removes the capsule once the rig is on screen; a rigless model
still goes through `attach_bodies` / `pose_figures`. n2's red tests keep their assertions; they
moved to the merged names and JSON shape. Main's tests pass unchanged except that struct literals
of `FigureModel` gained `rig: None`; none asserts the shipped figure is Cesium Man.

## What was built on it

`src/actors.rs`, `src/actors/rig.rs`, `src/figure_anim.rs`, `src/world.rs`,
`assets/behaviour/person.figure.json`.

## To override

Flatten `rig` back into `FigureModel` fields, or restore `FigureDef.rig`; the pure functions in
`figure_anim.rs` take a `RigDef` either way.
