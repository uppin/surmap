# Gazebo disaster world — what it is

A plain-language overview of the civilian search-and-rescue scene in
Gazebo Harmonic with PX4 SITL. The scene is fictional. It is not a real
incident and it is not a military model. SurMap only reads stereo and
GPS. It does not arm the vehicle or upload a mission.

The longer runbook is [disaster-world.md](disaster-world.md). The stereo
airframe and the capture → EuRoC bridge are
[px4-sitl.md](px4-sitl.md).

## The block

`docs/simulation/gz/worlds/disaster_block.sdf` is one city block after
an earthquake and a flood. Map axes are Gazebo ENU: +x east, +y north,
+z up. The origin is the PX4 SITL spherical anchor (the same numbers as
PX4's default world, so the compass and home match a stock SITL):
latitude 47.397971057728974, longitude 8.546163739800146, elevation
488 m, heading 0, WGS84.

What is in the file:

- A helipad at the origin, kept clear, so the spawn contact matches PX4's default ground.
- An avenue along x = 0 and a cross street around y = 60.
- Pancaked buildings: floor plates, a partial wall, a slab tipped into the street, a broken wall standing in the flood, and one remaining roof.
- Two rubble mounds (south-west and north-east) made of rotated concrete blocks and beams, spilling into the streets.
- A muddy flood, about 32 m by 36 m, centred near (10, 38), with planks, a beam, a crate and a tire on it.
- Debris: broken poles, drooping wires, planks and tires.
- Cars at odd angles, including one overturned, one partly buried, and one in the flood.
- Dry brown dirt, with ash-grey dust around the collapses. Not a grass lawn.
- Smoke columns at the south-east and north-east collapses: stacked grey translucent cylinders, a fire marker, and a Harmonic particle emitter. The runbook says PX4's server config does not load that plugin, so the cylinders are what an overview still shows if the emitter stays dark.

Textures are original 256×256 images next to the world
(`disaster_block_materials/`). Nothing is downloaded from Gazebo Fuel.

## People

Survivors are SDF primitives in the same world file. Standing figures
use a collision box 1.75 m tall; the head sphere sits at 1.62 m with
radius 0.13 m, so the top of the head is about 1.75 m. Clothing colours
in the SDF are orange (`0.95 0.42 0.05`) or yellow (`0.96 0.82 0.08`).

The survivor list is the `people` array in
`docs/simulation/gz/worlds/disaster_block_ground_truth.json`. Do not
assume a fixed count: PR notes have said six people and the world file
has since been edited. Score whatever that array contains. In this
commit the array is:

| Id | Pose in the JSON | Feet (`map_enu_m`) |
|---|---|---|
| `survivor_standing_avenue_south` | standing | (−3.5, 16, 0) |
| `survivor_lying_flood_edge` | lying | (−5, 54, 0) |
| `survivor_waving_on_rubble` | waving | (−4, 42, 2.2) |
| `survivor_standing_rooftop` | standing | (−14, 86, 3.4) |
| `survivor_lying_north_blockage` | lying | (−1, 72, 0) |
| `survivor_waving_plaza` | waving | (−2, 64, 0) |
| `survivor_waving_northeast_rubble` | waving | (6, 76, 1.8) |

`z` is the feet: 0 on the street, higher on a mound or roof. Each
person also has WGS84 `latitude_deg`, `longitude_deg`, and
`altitude_m`. The same file lists roads as passable, flooded, or
blocked. `load_disaster_ground_truth()` reads the file and rejects a
fix that does not match its map offset. It does not send a flight
command.

## The drone and the cameras

The airframe is `x500_surmap_stereo`: PX4's x500 quadrotor plus the
SurMap stereo model `surmap_stereo_cam`, fixed 0.12 m forward and
0.242 m up on `base_link`. The cameras look forward, along the body +X
axis.

From `docs/simulation/gz/surmap_stereo_cam/model.sdf`:

| | |
|---|---|
| Sensors | `left_camera`, `right_camera` |
| Image | 640×480, RGB |
| Horizontal FOV | 1.3962634 rad |
| Baseline | 0.07 m along Y. Gazebo is forward-left-up, so the left eye is at Y = +0.035 |
| Rate | 20 Hz |
| Clip | 0.05 m to 300 m |

The EuRoC export writes that left eye at Y = −baseline/2, because the
EuRoC body +Y points right. Both numbers are the same camera. See
`docs/simulation/px4-sitl.md`.

## The lawnmower

`docs/simulation/gz/worlds/disaster_block_survey.plan` is a
QGroundControl plan. SurMap does not upload it. Cruise speed in the
file is 4 m/s. The mission items store altitude 5 m above home. The
runbook's lanes are east −24, −16, −8, 0, 8, 16, 24 m, each running
north from 18 m to 100 m and alternating direction, then return to
launch. At 5 m the forward cameras see the street about 8 m ahead, in a
strip about 13 m wide, so the 8 m lane spacing overlaps. Solid roofs
top out at 3.4 m. Yaw is left unset so PX4 faces the next waypoint.

With SITL running, an operator opens the plan in QGroundControl,
uploads it from there, and starts it from there.

## How launch works

`scripts/launch_disaster_sitl.sh` does four things:

1. Requires `~/PX4-Autopilot` (or `PX4_AUTOPILOT_ROOT`) to already be a checkout that builds `px4_sitl_default`.
2. Puts the SurMap gz directory, the worlds directory, and `~/src/PX4-gazebo-models/models` on `GZ_SIM_RESOURCE_PATH`.
3. Symlinks `x500_surmap_stereo`, `disaster_block.sdf`, and `disaster_block_materials` into PX4's `Tools/simulation/gz/` tree.
4. Runs `PX4_GZ_WORLD=disaster_block PX4_SIM_MODEL=x500_surmap_stereo make px4_sitl gz_x500`.

It does not set `HEADLESS`, so PX4's `px4-rc.gzsim` also starts the
Gazebo GUI (`gz sim -g`) when that script is the one on PX4 `main`.
The `pxh>` prompt stays in the PX4 terminal. The script does not arm
the vehicle.

## How a flight becomes a EuRoC session

SurMap's SLAM path consumes an EuRoC `mav0/` tree, not a Gazebo topic.

1. Bridge the two cameras (and GPS) to ROS 2. Topic names depend on the spawned model `x500_surmap_stereo_0`.
2. `scripts/ros2/dump_sitl_capture.py` only subscribes. It writes `calibration.json`, `frames.jsonl`, `gps.csv`, and images. The layout is in `docs/simulation/px4-sitl.md`.
3. `uv run python scripts/export_sitl_session.py --capture <dir> --output <euroc>` calls `load_sitl_capture` and `export_euroc_session`. That writes `mav0/cam0`, `mav0/cam1`, a stationary IMU, and optional GPS. An existing `mav0/` is replaced.

The checked-in stand-in for that dump is `tests/fixtures/sitl_capture_tiny/`.
It is a tiny capture, not a recording of this disaster block. The
offline mission demo exports that fixture when Gazebo is not what the
command is driving.

## What is verified, and what is not

Recorded in the repo:

- `docs/simulation/px4-sitl.md` marks Gazebo Harmonic, a built `px4_sitl_default` under `~/PX4-Autopilot`, and ROS 2 Jazzy as present on a WSL host. It also says the stereo spawn line was checked against PX4 `main` and was not launched from this repo.
- `docs/simulation/disaster-world.md` says the launch checklist was checked against PX4 `main` (`px4-rc.gzsim` starts `gz sim -g` when `HEADLESS` is unset) and was not executed on the machine that added the world, because that VM has no `gz` binary.
- Unit tests load the ground-truth JSON, check it against the SDF poses, and export the tiny capture to EuRoC. They do not start Gazebo.
- PR #18's test plan still leaves the operator WSL run unchecked.

Not recorded in the committed notes: a screenshot of this world, a PX4
console line "Ready for takeoff", a flown lawnmower, a ROS 2 dump of
this block, or RTAB-Map tracking those frames. The host checklist
skill (`.agents/skills/px4-sitl-test/SKILL.md`) marks the launch,
camera topics, and bridge as unverified until someone runs them on the
WSL machine.

Ginas's WSL, as reported for this demo and not pasted into the runbook
above, has shown the world rendering and PX4 reaching Ready for
takeoff. Treat that as an operator report until it is written into
`docs/simulation/disaster-world.md` with the console text.
