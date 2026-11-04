//! The simulation's own drones, docked on the scene's nests and flown by the kinematic autopilot
//! from the fleet log. One drone at a time is "viewed": its eyes are the stereo feed and its pose
//! is what a recording writes. A scene without nests keeps the legacy `Drone` and the survey loop.

pub mod autopilot;
#[cfg(target_arch = "wasm32")]
pub mod bridge_wasm;
pub mod link;
#[cfg(target_arch = "wasm32")]
pub mod link_wasm;
pub mod log;
pub mod stream;

#[cfg(test)]
mod tests;

use std::collections::HashMap;

use bevy::app::AppExit;
use bevy::prelude::*;
use bevy_rapier3d::prelude::{Collider, RigidBody};

use crate::actors::bevy_yaw;
use crate::calibration::CameraProfile;
use crate::flight::{FlightPose, SurveyLoop};
use crate::shots::RunMode;
use crate::wildfire::SimClock;
use crate::world::{enu, Nests};
use crate::{attach_drone_parts, Drone, Rotor};

#[cfg(test)]
use autopilot::state_at;
use autopilot::{Autopilot, DroneState, Home, Phase};
use log::{FleetCommand, FleetLog};

/// A docked drone's body centre stands this far over its pad's deck, m: half the frame's height
/// and a little more, so the drone rests on the deck.
pub const BODY_OFFSET_M: f32 = 0.1;
/// How far from a pad's centre the slots of a nest with several drones lie, m: far enough that
/// two bodies, rotors included, clear each other, near enough that all stay on the 2.4 m pad.
const SLOT_M: f32 = 0.6;

/// A fleet drone's body, by its nest drone id.
#[derive(Component, Debug, Clone, PartialEq)]
pub struct FleetDrone {
    pub id: String,
}

/// A fleet drone's rotor; it spins while the drone is off its pad.
#[derive(Component)]
pub struct FleetRotor;

/// The drone whose eyes are shown; `None` without a fleet.
#[derive(Resource, Debug, Clone, Default, PartialEq)]
pub struct ActiveDrone(pub Option<String>);

/// The scene's fleet: its log and one autopilot per drone, in nest order.
#[derive(Resource, Debug, Clone)]
pub struct Fleet {
    pub log: FleetLog,
    pub autopilots: Vec<Autopilot>,
}

impl Fleet {
    /// One autopilot per drone of `log`, each docked on its home.
    pub fn new(log: FleetLog) -> Self {
        let autopilots = log.drones().iter().map(|(id, home)| Autopilot::new(id, *home)).collect();
        Self { log, autopilots }
    }

    /// The drone viewed at `t_s`: the first drone, switched by each `set_active` at its `at_s`.
    pub fn active_at(&self, t_s: f32) -> Option<&str> {
        let switched = self
            .log
            .entries()
            .iter()
            .take_while(|entry| entry.at_s <= t_s)
            .filter_map(|entry| match &entry.command {
                FleetCommand::SetActive { drone } => Some(drone.as_str()),
                _ => None,
            })
            .last();
        switched.or_else(|| self.log.drones().first().map(|(id, _)| id.as_str()))
    }

    /// Where drone `id` was at the last moment the fleet advanced to.
    pub fn state_of(&self, id: &str) -> Option<DroneState> {
        self.autopilots.iter().find(|pilot| pilot.id() == id).map(Autopilot::state)
    }

    /// Advances every drone to `t_s`, applying the log's new entries.
    pub fn advance(&mut self, t_s: f32) {
        for pilot in &mut self.autopilots {
            pilot.advance(&self.log, t_s);
        }
    }
}

/// Every drone of every nest with its home on the nest's pad, nest by nest in scene order.
pub fn homes(nests: &Nests) -> Vec<(String, Home)> {
    nests
        .0
        .iter()
        .flat_map(|nest| {
            let (sin, cos) = nest.yaw_deg.to_radians().sin_cos();
            let slots = slots(nest.drone_ids.len());
            nest.drone_ids.iter().enumerate().map(move |(i, id)| {
                let [east, north] = slots.get(i).copied().unwrap_or([0.0, 0.0]);
                let [x, y, z] = nest.pad_enu;
                (id.clone(), Home { pad_enu: [x + east * cos - north * sin, y + east * sin + north * cos, z], yaw_deg: nest.yaw_deg })
            })
        })
        .collect()
}

/// Where each of `count` drones sits on its pad, east and north of the centre before the pad's yaw.
fn slots(count: usize) -> Vec<[f32; 2]> {
    let s = SLOT_M;
    match count {
        0 | 1 => vec![[0.0, 0.0]],
        2 => vec![[-s, 0.0], [s, 0.0]],
        3 => vec![[-s, -s], [s, -s], [0.0, s]],
        _ => vec![[-s, -s], [s, -s], [-s, s], [s, s]],
    }
}

/// What the eyes follow and a recording writes at `t_s`.
#[derive(Debug, Clone, PartialEq)]
pub struct Viewed {
    /// The active fleet drone; `None` for the legacy drone.
    pub drone_id: Option<String>,
    /// The rig pose, in Bevy coordinates.
    pub pose: FlightPose,
}

/// A drone's rig pose, in Bevy coordinates: its reference point plus the body offset, facing its heading.
fn pose_of(state: &DroneState) -> FlightPose {
    let [x, y, z] = state.position_enu;
    FlightPose { position: enu(x, y, z) + Vec3::Y * BODY_OFFSET_M, yaw_rad: bevy_yaw(Vec2::from_angle(state.yaw_deg.to_radians())) }
}

/// The viewed rig pose at `t_s`, purely from time: the active fleet drone's autopilot pose, else
/// the survey loop's. The drone is replayed from its pad; this is the definition `ViewedPoses`
/// must equal.
#[cfg(test)]
pub fn viewed_pose(fleet: Option<&Fleet>, t_s: f32) -> Viewed {
    viewed_with(fleet, t_s, |home, id, log| state_at(home, id, log, t_s))
}

/// The viewed pose at `t_s`, the active drone's state coming from `state_of`.
fn viewed_with(fleet: Option<&Fleet>, t_s: f32, state_of: impl FnOnce(Home, &str, &FleetLog) -> DroneState) -> Viewed {
    let drone = fleet.and_then(|fleet| {
        let id = fleet.active_at(t_s)?;
        let (_, home) = fleet.log.drones().iter().find(|(drone, _)| drone == id)?;
        Some((id, state_of(*home, id, &fleet.log)))
    });
    match drone {
        Some((id, state)) => Viewed { drone_id: Some(id.to_owned()), pose: pose_of(&state) },
        None => Viewed { drone_id: None, pose: SurveyLoop::disaster_block().pose_at(t_s) },
    }
}

/// What a recording asks for, frame after frame: one autopilot per drone, advanced to each
/// frame's moment instead of replayed from `t = 0`. A moment earlier than the last replays.
#[derive(Debug, Default)]
pub struct ViewedPoses(HashMap<String, Autopilot>);

impl ViewedPoses {
    /// The viewed rig pose at `t_s`.
    pub fn viewed(&mut self, fleet: Option<&Fleet>, t_s: f32) -> Viewed {
        viewed_with(fleet, t_s, |home, id, log| self.0.entry(id.to_owned()).or_insert_with(|| Autopilot::new(id, home)).advance(log, t_s))
    }
}

/// The body a camera follows: the active fleet drone's, else the legacy drone's.
pub fn viewed_body<'a>(active: Option<&str>, fleet: impl IntoIterator<Item = (&'a FleetDrone, &'a Transform)>, legacy: Option<&'a Transform>) -> Option<&'a Transform> {
    active.and_then(|id| fleet.into_iter().find(|(drone, _)| drone.id == id).map(|(_, body)| body)).or(legacy)
}

/// The body transform that puts the rig of `pose` where the pose says, the way the survey loop
/// places the legacy drone: the body is the pose less the rig's mount offset.
fn body_transform(pose: FlightPose, mount_offset: Vec3) -> Transform {
    let rotation = Quat::from_rotation_y(pose.yaw_rad);
    Transform { translation: pose.position - rotation * mount_offset, rotation, ..default() }
}

fn phase_label(phase: Phase) -> &'static str {
    match phase {
        Phase::Docked => "DOCKED",
        Phase::Climbing => "CLIMBING",
        Phase::Cruising => "CRUISING",
        Phase::Detouring => "DETOURING",
        Phase::Hovering => "HOVERING",
        Phase::Returning => "RETURNING",
        Phase::Landing => "LANDING",
    }
}

/// The status text: the active drone's phase, legs left and flight data, then every drone and its
/// phase (the active one marked `>`).
pub fn fleet_status(active: Option<&str>, drones: &[(&str, DroneState)]) -> String {
    let headline = match active.and_then(|id| drones.iter().find(|(drone, _)| *drone == id)) {
        Some((id, state)) => format!(
            "FLEET  {id}  {}  {} left  alt {:.1} m  speed {:.1} m/s  yaw {:.0} deg",
            phase_label(state.phase),
            match state.legs_left {
                1 => "1 leg".to_owned(),
                n => format!("{n} legs"),
            },
            state.position_enu[2],
            Vec3::from(state.velocity_enu).length(),
            state.yaw_deg,
        ),
        None => "FLEET  no drone active".to_owned(),
    };
    let list = drones.iter().map(|(id, state)| format!("{} {id} · {}", if Some(*id) == active { ">" } else { " " }, phase_label(state.phase)));
    std::iter::once(headline).chain(list).collect::<Vec<_>>().join("\n")
}

/// After the world is built: one kinematic body (frame and four rotors) per `Nests` drone id,
/// docked on its pad and tagged `FleetDrone`, the fleet's log (`--fleet-log`, else empty) and
/// the first drone active; the legacy `Drone` is despawned when the scene has nests.
pub(crate) fn spawn_fleet(
    mut commands: Commands,
    nests: Option<Res<Nests>>,
    legacy: Query<Entity, With<Drone>>,
    mode: Res<RunMode>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut exit: MessageWriter<AppExit>,
    mut done: Local<bool>,
) {
    let (false, Some(nests)) = (*done, nests) else { return };
    *done = true;
    let homes = homes(&nests);
    let Some((first, _)) = homes.first() else { return };
    let first = first.clone();
    let log = match &mode.fleet_log {
        None => FleetLog::new(homes.clone()),
        Some(path) => match std::fs::read_to_string(path).map_err(|e| e.to_string()).and_then(|text| FleetLog::from_jsonl(homes.clone(), &text)) {
            Ok(log) => log,
            Err(why) => {
                error!("--fleet-log {}: {why}", path.display());
                exit.write(AppExit::error());
                return;
            }
        },
    };
    for refusal in log.refused() {
        warn!("fleet log: command {} at {} s refused: {:?}", refusal.seq, refusal.at_s, refusal.reason);
    }
    for entity in &legacy {
        commands.entity(entity).despawn();
    }
    for (id, home) in homes {
        let docked = DroneState { position_enu: home.pad_enu, velocity_enu: [0.0; 3], yaw_deg: home.yaw_deg, phase: Phase::Docked, target: None, legs_left: 0 };
        let body = commands
            .spawn((
                FleetDrone { id: id.clone() },
                Name::new(format!("Drone {id}")),
                RigidBody::KinematicPositionBased,
                Collider::cuboid(0.18, 0.08, 0.18),
                body_transform(pose_of(&docked), Vec3::ZERO),
                Visibility::default(),
            ))
            .id();
        for rotor in attach_drone_parts(&mut commands, &mut meshes, &mut materials, body) {
            commands.entity(rotor).insert(FleetRotor);
        }
    }
    commands.insert_resource(Fleet::new(log));
    commands.insert_resource(ActiveDrone(Some(first)));
}

/// Poses every fleet drone from its autopilot at `SimClock::now()`, and switches the active
/// drone at each `set_active`.
pub fn fly_fleet(
    clock: SimClock,
    fleet: Option<ResMut<Fleet>>,
    active: Option<ResMut<ActiveDrone>>,
    rig: Option<Res<CameraProfile>>,
    mut drones: Query<(&FleetDrone, &mut Transform)>,
) {
    let Some(mut fleet) = fleet else { return };
    let t_s = clock.now();
    fleet.advance(t_s);
    if let Some(mut active) = active {
        let now = fleet.active_at(t_s).map(str::to_owned);
        if active.0 != now {
            active.0 = now;
        }
    }
    let mount_offset = rig.map_or(Vec3::ZERO, |rig| rig.mount_offset());
    for (drone, mut body) in &mut drones {
        if let Some(state) = fleet.state_of(&drone.id) {
            *body = body_transform(pose_of(&state), mount_offset);
        }
    }
}

/// Spins the rotors of every drone that is off its pad.
pub fn spin_fleet_rotors(time: Res<Time>, fleet: Option<Res<Fleet>>, drones: Query<&FleetDrone>, mut rotors: Query<(&ChildOf, &Rotor, &mut Transform), With<FleetRotor>>) {
    let Some(fleet) = fleet else { return };
    for (parent, rotor, mut transform) in &mut rotors {
        let airborne = drones.get(parent.parent()).ok().and_then(|drone| fleet.state_of(&drone.id)).is_some_and(|state| state.phase != Phase::Docked);
        if airborne {
            transform.rotate_y(rotor.0 * time.delta_secs());
        }
    }
}
