---
name: using-the-map
description: How to use the map tools: place and move objects, navigate the camera, draw routes and load layers.
---

# Using the map

The map tools edit the display map the person is looking at: GLB shapes placed on it,
the camera, drawn route paths, and data layers. Map edits change only what the person
sees. A route here is a drawn path, never a flight plan, and no map tool commands a
vehicle — if the person asks for flight or navigation of a real vehicle, say the map
cannot do that and offer to draw the path instead.

Load this skill before placing, moving or drawing anything on the map, then work
through the tools below. Read the scene back with `get_map_scene` after a change when
the result matters: every change bumps the scene `revision`, and the chat UI redraws
when it changes, so the revision in a tool's reply is the proof the edit landed.

## Scenes

Every map tool takes an optional `scene_id`; leave it out unless the person names a
scene — the tools then use the `default` scene. Ids you choose (`object_id`,
`route_id`) are how later calls refer to the thing; give deliberate ids when the
person will ask about the thing again, and reuse the id a tool returned rather than
inventing a new one. Placing an object or route with an id that is already on the map
fails with ALREADY_EXISTS — move or remove the existing one, or pick another id.

## Placing and moving objects

- `add_map_object` places a GLB shape: a `label` (what it is, e.g. "debris pile"), a
  `geometry_uri` (a `surmap-glb://` URI from a survey result, or an http(s) URL), and a
  `position`. Optional `rotation_deg` turns it about the vertical axis, clockwise from
  north; `scale` is uniform, 1 as modelled, and must be positive.
- `move_map_object` changes only the fields you give — position, `rotation_deg`, or
  `scale`; the rest keep their values. Use it instead of removing and re-placing.
- `remove_map_object` takes a placed object off the map.
- `list_map_objects` lists what is placed, in the order it was added; `get_map_scene`
  returns objects, camera, routes and layers together.

Positions are WGS84: `lon` −180..180, `lat` −90..90, optional `alt_m`. A position off
the world fails with INVALID_ARGUMENT; an object the scene does not have fails with
NOT_FOUND. When the person names a place rather than coordinates, use coordinates
from the conversation (a survey object's geometry, the current camera centre from
`get_map_scene`) and say which you used — do not invent coordinates silently.

## Navigating the camera

`navigate_map` moves the view, never a vehicle. Give only the fields that change:
`centre`, `zoom` (0 the whole world to 22 a building), `pitch_deg` (0..85 tilt from
straight down) or `bearing_deg` (clockwise from north). Moving the camera is how you
show the person what you just placed: after placing an object away from the current
view, navigate to it.

## Drawing routes

- `show_route` draws a new path from at least two `waypoints`, joined in the order
  given; give a `name` that says what the path shows (e.g. "cleared corridor") and an
  optional CSS `color` (amber by default).
- `update_route` replaces a route's waypoints, name or colour; an empty waypoint list
  keeps the current path.
- `clear_route` removes a drawn route.

A route needs at least two waypoints — one point is not a path, so ask for the other
end or draw to a named second point. Always describe a route as drawn: "I've drawn
the corridor on the map", never as something a vehicle will fly.

## Layers

`list_map_layers` lists the catalogue with each layer's loaded state on this scene. A
fresh scene already loads the defaults, OpenStreetMap among them. `load_map_layer`
draws a catalogue layer (loading one already loaded leaves it as it is);
`unload_map_layer` stops drawing one, the OpenStreetMap base included. An unknown
layer id fails with NOT_FOUND — list the layers first when unsure which exist.
Loading a layer is a view change: do it when the person asks to see that data, and
say which layer you loaded.

## A worked order

To put a surveyed object on the map and show it: place it with `add_map_object` using
its `geometry_uri` and position, `navigate_map` to its position at a zoom where it
fills the view, then `get_map_scene` and report the revision. To show a path between
two surveyed objects: `show_route` with their positions in order, then describe the
line as drawn.
