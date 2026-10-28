# Disaster-response world (Gazebo Harmonic)

A fictional civilian city block after an earthquake and a flood, for the
SurMap search-and-rescue demo. The drone is still flown by PX4. SurMap
only reads stereo and GPS. Nothing here is a real incident, and nothing
here is a military model.

The stereo airframe and the capture → EuRoC bridge are
[px4-sitl.md](px4-sitl.md). This page is the world, the scoring file,
and the launch.

## Launch on WSL2 (WSLg)

Windows 11 WSLg is what shows the Gazebo window on the Windows desktop.
From the SurMap repo:

```bash
echo "$DISPLAY"          # :0 on WSLg
echo "$WAYLAND_DISPLAY"  # wayland-0 on WSLg

./scripts/launch_disaster_sitl.sh
```

That is the one command. It symlinks the stereo model, the world, and
the textures into `~/PX4-Autopilot` and runs:

```bash
PX4_GZ_WORLD=disaster_block PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500
```

PX4 opens `Tools/simulation/gz/worlds/disaster_block.sdf` and spawns
`x500_surmap_stereo_0`. It also starts the Gazebo GUI (`gz sim -g`)
unless `HEADLESS` is set. This script does not set `HEADLESS`.

`~/PX4-Autopilot` must already be the checkout that builds
`px4_sitl_default`, same as the stereo runbook. If it lives elsewhere:

```bash
PX4_AUTOPILOT_ROOT=/path/to/PX4-Autopilot ./scripts/launch_disaster_sitl.sh
```

The x500 mesh still comes from `~/src/PX4-gazebo-models/models`, which
the script puts on `GZ_SIM_RESOURCE_PATH`.

Leave the PX4 terminal open. The `pxh>` prompt is in that terminal.
The Gazebo window is a separate process on the WSLg desktop.

World only, no drone (the drone appears when PX4 spawns it):

```bash
export GZ_SIM_RESOURCE_PATH="$(pwd)/docs/simulation/gz:$(pwd)/docs/simulation/gz/worlds:${GZ_SIM_RESOURCE_PATH:-}"
gz sim -r docs/simulation/gz/worlds/disaster_block.sdf
```

This host checklist was checked against PX4 `main` (`px4-rc.gzsim`,
which launches `gz sim -g` when `HEADLESS` is unset). It has not been
executed on the machine that added the world: that VM has no `gz` binary.

## Survey plan

`docs/simulation/gz/worlds/disaster_block_survey.plan` is a
QGroundControl plan. SurMap does not upload it.

The stereo cameras look forward, along the body +X axis (see the stereo
model). At 12 m above home the ground enters the lower edge of the
frame about 20 m ahead, and the tallest building is 8 m, so the
lawnmower clears the roofs. Cruise speed is 4 m/s. Yaw is left unset
so PX4 faces the next waypoint and the cameras look along the leg.

| Item | Value |
|---|---|
| Altitude | 12 m above home |
| Speed | 4 m/s |
| Lanes (east, m) | −24, −12, 0, 12, 24 |
| Each lane (north, m) | 18 → 100, alternating direction |
| Ends with | return to launch |

With SITL running and QGroundControl connected to it:

1. Plan view → open `docs/simulation/gz/worlds/disaster_block_survey.plan`
2. Upload the plan from QGroundControl
3. Start the mission from QGroundControl

Home is the PX4 SITL anchor. The helipad is the world origin, south of
the block. The block itself runs north from about 14 m to 104 m.

## What is in the block

Map frame is Gazebo ENU: +x east, +y north, +z up. The origin is the
spherical-coordinate anchor, which is also PX4 home.

| Place | Where |
|---|---|
| Helipad | origin. Visual only, so the spawn contact matches PX4's default ground |
| Avenue | centre x = 0, about y = 14 to 104, 12 m wide |
| Cross street | centre y = 60, across the avenue |
| Intact brick block | south-west, 8 m tall |
| Partial collapse, rubble, tilted slab | south-east, remnant 4.6 m |
| Low intact block | north-west, 4.4 m |
| Rubble field and tilted slab | north-east |
| Flood | south avenue, about y = 28 to 42 |
| Debris and a fallen pole | east cross street, centre (18, 60) |
| Fallen pole and rubble | north avenue, centre (0, 84) |
| Parked cars | west curb near y = 50, east curb near y = 70 |
| Overturned car | beside the south-east collapse |
| Car in the flood | on the flooded avenue |

People stand in the open streets, in orange, red, or yellow, so they
are not hidden behind a facade:

| Id | Pose |
|---|---|
| `survivor_standing_avenue_south` | standing, south of the flood |
| `survivor_lying_flood_edge` | lying, just north of the water |
| `survivor_standing_collapse` | standing, west of the east debris |
| `survivor_waving_plaza` | waving, north side of the crossing |
| `survivor_waving_east_corner` | waving, just west of the east debris |
| `survivor_lying_north_blockage` | lying, south of the north pole |

Roads the scorer should know:

| Id | Kind | Passable for a ground vehicle |
|---|---|---|
| `avenue_south_clear` | passable | yes |
| `cross_west_clear` | passable | yes |
| `avenue_flood` | flooded | no |
| `cross_east_debris` | blocked | no |
| `avenue_north_pole` | blocked | no |

The drone flies over all of these. "Passable" is about the road, not
about the airframe.

## Ground truth

`docs/simulation/gz/worlds/disaster_block_ground_truth.json`

Each person and each road above has:

- `map_enu_m` — x east, y north, z up, metres, model origin on the ground
- `latitude_deg`, `longitude_deg`, `altitude_m` — WGS84

The world's spherical coordinates, and the JSON anchor, are the PX4
SITL default (so the compass and home match a stock world):

| Field | Value |
|---|---|
| surface | `EARTH_WGS84` |
| frame | `ENU`, heading 0 |
| latitude | 47.397971057728974 |
| longitude | 8.546163739800146 |
| elevation | 488 m |

A fix is that anchor plus the local ENU offset, using the WGS84
meridional radius for north and the prime-vertical radius for east.
`altitude_m` is elevation plus z. Plan altitudes are different: they
are metres above home, not ellipsoidal height.

```python
from surmap.simulation import load_disaster_ground_truth

truth = load_disaster_ground_truth()
for person in truth.people:
    print(person.id, person.pose, person.latitude_deg, person.longitude_deg)
```

`load_disaster_ground_truth` rejects a fix that does not match its map
offset. The same module reads model poses out of the SDF
(`world_model_poses`) and the QGroundControl plan (`load_survey_plan`).
None of those functions send a flight command.

## Assets and licences

No Gazebo Fuel models. The world does not download anything at launch.

| Asset | Source | Licence |
|---|---|---|
| Buildings, roads, water, rubble, slabs, poles, cones, cars, people | SDF box, sphere, and cylinder primitives in `docs/simulation/gz/worlds/disaster_block.sdf` | Original geometry written for this repo |
| `disaster_block_materials/*.png` (brick, asphalt, concrete, rubble, dirt) | Original 256×256 procedural textures committed next to the world | Original; no upstream texture |
| Physics step 0.004 s, gravity, magnetic field `6e-06 2.3e-05 -4.2e-05`, and the WGS84 anchor | Same numbers as [PX4-gazebo-models `worlds/default.sdf`](https://github.com/PX4/PX4-gazebo-models/blob/main/worlds/default.sdf) | PX4-gazebo-models is BSD-3-Clause. Copied so SITL's compass and home match the stock world. The scene around them is not from that file |

Diffuse colours are set as well as the albedo maps, so a missing texture
still reads as brick, asphalt, or clothing. The maps are paths relative
to the world file (`disaster_block_materials/...`). The launch script
symlinks that directory beside the world symlink, because PX4 opens the
symlink path.

## After it is flying

Capture and EuRoC export are unchanged. Follow
[px4-sitl.md](px4-sitl.md) from the bridge step: discover the
`left_camera` and `right_camera` topics on `x500_surmap_stereo_0` and
dump with `scripts/ros2/dump_sitl_capture.py`. Score detections against
the JSON above. The dump script still only subscribes.
