---
name: building-a-simulation-scene
description: A subagent's procedure for building a simulation scene with the simulation tools. Pass it as the skill of start_subagent; the main agent does not load it itself.
---

# Building a simulation scene

You are building one scenario for the station's Bevy simulation, from the brief the main agent
gave you. Work through the steps below with the simulation tools, check the result, and finish
with a short report. Every edit makes a new scenario version; an invalid edit fails with the
reason and changes nothing, so read the error, fix the argument and retry — never repeat a
failing call unchanged.

## 1. Start from the right scenario

- **A change to an existing scene**: `get_scenario` with the id from the brief, and read its
  manifest before you edit.
- **A new scene**: `create_scenario` with the brief's name and the closest preset —
  `earthquake-block` (collapsed city block), `empty-lot` (sky and bare ground), `wildfire-edge`
  (pine stands in dry grass, a fire at their upwind edge), `wildfire-evacuation` (the edge with
  people who flee), `earthquake-fleet` (the block with three drone nests: two on open ground, one
  on a roof), `flood-street` (the block in rain and fog), `district-showcase` (the four
  building districts) or `downtown-blaze` (a downtown block with a burning glass tower). A preset
  that already holds most of the brief saves many edits; remove what does not fit with
  `remove_element`, `remove_fire` or `remove_district`.

Positions are ENU metres (east, north, up) from the scene origin; yaw is counter-clockwise from
east; the wind's direction is where it blows *from*, clockwise from north (270 is a westerly).

## 2. Build it

- **Buildings.** `list_building_presets` once, then `set_district` for areas of one character
  (`old-town`, `downtown`, `industrial`, `suburban`) and `style_building` for the buildings the
  brief singles out (facade, roof, roof shape, floors, glazing). Collapsed buildings, roads,
  ground and water are `add_element` boxes and elements.
- **People.** `add_element` with a `person` per person the brief asks for, then give each a
  behaviour with `set_behaviour` — e.g. a `selector` that runs `flee_from_fire` when `near_fire`
  and otherwise `wander`s. Read a tree back with `get_behaviour`; change one node with
  `update_behaviour_node`.
- **Drone nests.** When the brief asks for drones, place 2-4 nests far apart with `add_element`
  and a `drone_nest`: `position` is the pad's centre — open ground (`up` 0) or the flat top of a
  standing building (`up` = its roof height; a pad inside a building is refused) — never on water,
  within 500 m east and north of the origin, at least 6 m from any other nest. `drones` is 1-4
  (default 1) and names them `<id>-d1` … `<id>-dN`; `yaw_deg` is the way docked drones face. Nests
  are scene data only: a scenario holds at most 8, and placing one flies nothing. Then
  `get_scenario` to check each nest and its drone ids.
- **Weather and fire.** `set_weather` for rain, fog and the one wind every tree, flame and smoke
  plume follows; `add_fire` for a wildfire (ignition, start time, spread rate, maximum radius);
  `add_building_fire` for a fire inside a building on a floor that building has.
- **Assets.** Only when the brief needs a model the elements cannot make (a particular vehicle, a
  prop): `list_assets` first — the library may have it — else `search_assets`, then
  `download_asset` on a hit whose licence is accepted (CC0 or CC BY only; a refused hit cannot be
  fetched), then `add_model` with the asset's ref. Give `ground_truth_kind` (e.g. `car`) to a
  model the survey should be scored on finding. A download may run as a job: `wait_for_jobs`
  before you place it.

Make the edits the brief asks for and no others; when the brief leaves a detail open, choose a
plain default and mention it in your report.

## 3. When you need the main agent

- A decision the brief does not settle and no plain default fits: finish your turn with the
  question as your final answer, saying what you have built so far. The main agent answers with a
  new message and you continue from there.
- Something it must know now while you keep working (a requested asset has no accepted licence,
  so you are using a stand-in): `message_main_agent` with one or two sentences, then carry on.

Do not message it to report progress — your final answer reaches it anyway.

## 4. Check and report

Before you answer, `get_scenario` and read the latest version back: every element, nest, district,
fire and behaviour the brief asked for is in the manifest. Then finish with a report of a few
lines:

- the scenario id, its version and its URL;
- what is in it — the preset, districts, people and their behaviour, weather, fires and when they
  start;
- the defaults you chose, and anything you could not do and why;
- the credits of any CC BY asset it uses.
