---
name: flying-the-fleet
description: How to task the simulation's drones with the fleet tools: launch them on routes, re-plan, send detours, choose the active drone, recall them and read the fleet log. Simulation only; real aircraft are never commanded.
---

# Flying the fleet

The fleet tools task the **simulation's** drones: the drones that live in a scenario's drone
nests and fly in the station's Bevy simulation. Nothing here reaches PX4 or any real flight
controller, and you never command a real aircraft. If the person asks you to fly a real vehicle,
say that these tools only fly simulated drones, and decline.

Load this skill before launching, re-routing or recalling a drone. Positions are ENU metres
(east, north, up) on the simulated block, the same frame as `get_scenario`.

## 1. See the fleet

1. `list_nests(scenario_id)` gives each nest, its pad and the ids of its drones
   (`nest-sw-d1`, `nest-sw-d2`, ...). A scenario with no nests has no drones: say so, and offer
   to have a nest added with the simulation skill.
2. `list_drones(scenario_id)` gives each drone's phase, position, speed and the waypoints it has
   left, and which drone is active. Read `linked` first. When it is `false`, no simulation page is
   running for the scenario, every drone is shown docked on its pad, and every command that
   reaches the page fails `UNAVAILABLE`. Ask the person to open the scenario page with the fleet
   link on, and give the URL: `/sim/?scenario=<scenario_id>&fleet=1`. Then list again.

## 2. Plan the route

Read the scene with `get_scenario` and plan the waypoints over it:

- Keep clear of building footprints and collapsed buildings; fly over them, not through them.
- Every waypoint is 5-60 m up and within 500 m east and north of the origin.
- A speed is 0.5-8 m/s; leave it out for the default of 5 m/s.
- `on_complete` is `ROUTE_END_RETURN` (the default: fly back, land and dock) or
  `ROUTE_END_HOVER` (hold at the last waypoint, for a drone that is to stay on station).

## 3. Launch, then confirm

`launch_drone(scenario_id, drone_id, route)` takes off a **docked** drone. The answer carries the
command's `seq` and the simulation time `at_s` it took effect, not the flight: call `list_drones`
again to see the drone climbing, and keep calling it to follow the flight. Tell the person which
drone you launched and from which nest.

## 4. Adjust mid-flight

- `add_detour(drone_id, waypoints)` sends an airborne drone to those waypoints first, then it
  resumes the route it was flying. Use it for a closer look at something.
- `set_route(drone_id, route)` replaces the remaining route, flown from where the drone is now.
  Use it to re-plan.
- Both need a drone in flight. A docked or landing drone is refused with `not_flying`; launch
  it first.
- `recall_drone(drone_id)` flies an airborne drone back above its nest, lands and docks it. A
  docked drone is refused with `already_docked`.

## 5. Choose whose camera matters

`set_active_drone(drone_id)` makes a drone the active one. Only the active drone's camera is on
screen and processed, so call it on the drone whose view matters now, and say which drone you
switched to. It works on a docked drone too.

## 6. Detect objects on the active drone's camera

`set_onboard_model(scenario_id, onboard_model)` makes the station run an on-board detector model
(a name from `list_onboard_models`) on the active drone's frames; `"none"` stops it. The
simulation preview then outlines each detection on the drone's camera view, with a label card
(`<class> #<track> <score>%`) beside it. The model recognises only its listed classes (people and
vehicles, not debris, buildings or fire), so pick one when the person is looking for those.
The choice holds for the scenario: `streaming: false` means no page streams it yet, and the
model starts when one does. A model the station has no files for fails `FAILED_PRECONDITION`.

## 7. Finish

Recall drones that are no longer needed, and confirm with `list_drones` that they are `DOCKED`.
`get_fleet_log(scenario_id)` returns the latest fleet session's applied commands as the replay
file the simulation reads (pass `session_id` for an earlier session). Offer it when the person
wants to replay the flight.

## When a command fails

The message says why; relay it in plain words and do not retry blindly.

| Code | Meaning | What to do |
|---|---|---|
| `NOT_FOUND` | The scenario or the drone does not exist. | Check the ids with `list_scenarios` / `list_nests`. |
| `INVALID_ARGUMENT` | The station refused it, and the message leads with the rule: `no_waypoints`, `height_out_of_range`, `out_of_bounds`, `speed_out_of_range`, `not_docked`, `not_flying` or `already_docked`. | Fix the route or pick a drone in the right phase (`list_drones`), then send it again. |
| `FAILED_PRECONDITION` | The simulation itself refused it; the message is its own reason. | Report the reason. `list_drones` shows the drone's real phase. |
| `UNAVAILABLE` | No simulation page is linked. | Ask the person to open the scenario page with `&fleet=1`, then retry. |
| `DEADLINE_EXCEEDED` | The page did not answer in time. The command may or may not have applied. | `list_drones` before sending anything again. |
