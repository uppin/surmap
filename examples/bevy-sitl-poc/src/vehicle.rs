//! Vehicles that drive (docs/simulation/bevy-simulation.md § *Vehicles*). A vehicle's behaviour
//! tree says where it should go; `Drive` turns that into motion a real vehicle could make —
//! speed eased within its class's acceleration and braking, heading turned at most at its turn
//! rate. Pure, so a recording replays identically. Every number lives in
//! `assets/vehicle/<class>.vehicle.json`, never here.

use std::f32::consts::{PI, TAU};

use bevy::math::Vec2;
use serde::Deserialize;

use crate::behaviour::{Goal, Runner, Tree, World};
use crate::wind::WindModel;

pub mod scene;

/// The approach speed keeps the bearing to the goal turning at most this share of the turn rate,
/// so the heading always catches up with the bearing and a vehicle never circles a goal behind it.
const BEARING_SHARE: f32 = 0.5;

/// What a `vehicle` element is; picks `vehicle/<class>.vehicle.json`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VehicleClass {
    Car,
    Bus,
    Truck,
    Train,
}

impl VehicleClass {
    /// The class file, relative to the asset root.
    pub fn file(self) -> String {
        format!("vehicle/{}.vehicle.json", self.kind())
    }

    /// The ground-truth kind tracks carry (`car`, `bus`, …).
    pub fn kind(self) -> &'static str {
        match self {
            Self::Car => "car",
            Self::Bus => "bus",
            Self::Truck => "truck",
            Self::Train => "train",
        }
    }
}

/// A class's look and limits (`assets/vehicle/<class>.vehicle.json`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VehicleDef {
    /// The class glTF (asset path).
    pub glb: String,
    pub length_m: f32,
    pub width_m: f32,
    pub height_m: f32,
    /// glTF node-name prefixes of the wheels, spun about their axle.
    #[serde(default)]
    pub wheel_nodes: Vec<String>,
    #[serde(default)]
    pub wheel_radius_m: Option<f32>,
    pub max_speed_m_s: f32,
    pub accel_m_s2: f32,
    pub brake_m_s2: f32,
    pub turn_rate_deg_s: f32,
    /// Turns the model about up so its nose points along the vehicle's forward (−Z in the
    /// renderer): 180 for a glTF whose nose is +Z.
    #[serde(default)]
    pub model_yaw_deg: f32,
    /// Scales the class glTF uniformly, for a model authored off real metres (a bus from a
    /// pack whose units are not metres). 1 for a model already in metres.
    #[serde(default = "unit_scale")]
    pub model_scale: f32,
    /// Trains: the carriage glTF and the distance between consecutive carriages' centres.
    #[serde(default)]
    pub carriage_glb: Option<String>,
    #[serde(default)]
    pub carriage_spacing_m: Option<f32>,
}

fn unit_scale() -> f32 {
    1.0
}

impl VehicleDef {
    /// Parse and validate: every size, scale and limit > 0, a wheel radius when wheels are named,
    /// a carriage spacing > 0 when a carriage glTF is named.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let def: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        let positive = [
            ("model_scale", def.model_scale),
            ("length_m", def.length_m),
            ("width_m", def.width_m),
            ("height_m", def.height_m),
            ("max_speed_m_s", def.max_speed_m_s),
            ("accel_m_s2", def.accel_m_s2),
            ("brake_m_s2", def.brake_m_s2),
            ("turn_rate_deg_s", def.turn_rate_deg_s),
        ];
        if let Some((name, value)) = positive.iter().find(|(_, value)| !(*value > 0.0)) {
            return Err(format!("{name} must be > 0, not {value}"));
        }
        if !def.wheel_nodes.is_empty() && !def.wheel_radius_m.is_some_and(|r| r > 0.0) {
            return Err("wheel_radius_m must be > 0 when wheel_nodes name the wheels".into());
        }
        if def.carriage_glb.is_some() && !def.carriage_spacing_m.is_some_and(|s| s > 0.0) {
            return Err("carriage_spacing_m must be > 0 when carriage_glb names a carriage".into());
        }
        for path in std::iter::once(&def.glb).chain(def.carriage_glb.iter()) {
            if !(path.ends_with(".glb") || path.ends_with(".gltf")) {
                return Err(format!("{path:?} must be a glTF file"));
            }
        }
        Ok(def)
    }
}

/// A vehicle's motion state: where it is, the way it points (ENU radians, counter-clockwise
/// from east), how fast it goes, and the ground it has covered.
#[derive(Debug, Clone, PartialEq)]
pub struct Drive {
    pub position: Vec2,
    pub heading_rad: f32,
    pub speed_m_s: f32,
    /// Distance travelled, m — turns the wheels.
    pub odometer_m: f32,
    /// The travelled path, oldest first — the track carriages follow.
    trail: Vec<Vec2>,
}

impl Drive {
    pub fn new(position: Vec2, heading_rad: f32) -> Self {
        Self { position, heading_rad, speed_m_s: 0.0, odometer_m: 0.0, trail: vec![position] }
    }

    /// One tick toward `goal` within `def`'s limits: speed eases to the goal's speed (capped at
    /// `max_speed_m_s`) at `accel_m_s2`, and brakes at `brake_m_s2` to stop on a stopping goal;
    /// the heading turns at most `turn_rate_deg_s`, and speed is held low enough that the turn
    /// never circles the goal. No goal: brake to a stop.
    pub fn step(&mut self, def: &VehicleDef, goal: Option<Goal>, dt: f32) {
        let target = match goal {
            Some(goal) => {
                self.turn_toward(goal.point, def.turn_rate_deg_s.to_radians() * dt);
                self.approach_speed(def, goal)
            }
            None => 0.0,
        };
        self.speed_m_s = ease(self.speed_m_s, target, def, dt);
        let stride = self.speed_m_s * dt;
        if stride > 0.0 {
            self.position += Vec2::from_angle(self.heading_rad) * stride;
            self.odometer_m += stride;
            self.trail.push(self.position);
        }
    }

    /// The pose (ENU place, heading) of each of `cars` carriages, the k-th `k × spacing_m` behind
    /// the vehicle along its travelled path.
    pub fn carriage_poses(&self, cars: u32, spacing_m: f32) -> Vec<(Vec2, f32)> {
        (1..=cars).map(|k| self.behind(k as f32 * spacing_m)).collect()
    }

    /// Whether the goal lies ahead of the drive's current heading.
    pub fn is_ahead_of(&self, point: Vec2) -> bool {
        (point - self.position).dot(Vec2::from_angle(self.heading_rad)) > 0.0
    }

    /// Turns the heading toward `point` by at most `max_turn_rad`.
    fn turn_toward(&mut self, point: Vec2, max_turn_rad: f32) {
        let to_goal = point - self.position;
        if to_goal == Vec2::ZERO {
            return;
        }
        let error = wrap(to_goal.to_angle() - self.heading_rad);
        self.heading_rad = wrap(self.heading_rad + error.clamp(-max_turn_rad, max_turn_rad));
    }

    /// The speed the goal allows: its own speed, the class's top speed, and the bearing limit — a
    /// goal ahead may be closed at any speed, a goal to the side or behind only at the speed whose
    /// turn keeps the bearing behind the heading. A stopping goal is also closed no faster than a
    /// stopping distance allows, and never faster than `BEARING_SHARE` of its distance per turn
    /// rate: the body creeps onto it, so a discrete tick cannot carry it past.
    fn approach_speed(&self, def: &VehicleDef, goal: Goal) -> f32 {
        let to_goal = goal.point - self.position;
        let distance = to_goal.length();
        let error = wrap(to_goal.to_angle() - self.heading_rad);
        let turn_rate = def.turn_rate_deg_s.to_radians();
        let creep = BEARING_SHARE * turn_rate * distance;
        let bearing_cap = if error.cos() > 0.0 {
            creep / error.sin().abs().max(1e-6)
        } else {
            creep
        };
        let mut speed = goal.speed_m_s.min(def.max_speed_m_s).min(bearing_cap);
        if goal.stop {
            speed = speed
                .min((2.0 * def.brake_m_s2 * distance).sqrt())
                .min(creep);
        }
        speed
    }

    /// The place `back_m` behind the drive along its travelled path, and the heading there. Past
    /// the path's start it runs on straight back along the first leg.
    fn behind(&self, back_m: f32) -> (Vec2, f32) {
        let mut remaining = back_m;
        for leg in self.trail.windows(2).rev() {
            let (from, to) = (leg[0], leg[1]);
            let length = from.distance(to);
            let heading = (to - from).to_angle();
            if remaining <= length {
                return (to - Vec2::from_angle(heading) * remaining, heading);
            }
            remaining -= length;
        }
        let heading = self
            .trail
            .windows(2)
            .next()
            .map_or(self.heading_rad, |leg| (leg[1] - leg[0]).to_angle());
        (self.trail[0] - Vec2::from_angle(heading) * remaining, heading)
    }
}

/// Speed eased toward `target`: up at the class's acceleration, down at its braking.
fn ease(speed: f32, target: f32, def: &VehicleDef, dt: f32) -> f32 {
    if target > speed {
        (speed + def.accel_m_s2 * dt).min(target)
    } else {
        (speed - def.brake_m_s2 * dt).max(target)
    }
}

/// `angle` folded into [-π, π).
fn wrap(angle: f32) -> f32 {
    (angle + PI).rem_euclid(TAU) - PI
}

/// A wheel's rotation (rad) after rolling `distance_m`.
pub fn wheel_angle(distance_m: f32, radius_m: f32) -> f32 {
    distance_m / radius_m
}

/// A vehicle's tree and its motion: the tree proposes, `Drive` disposes. The runner is kept at
/// the vehicle's real place, so path ends and `near_object` see where the vehicle is.
pub struct VehicleBody {
    pub runner: Option<Runner>,
    pub drive: Drive,
}

impl VehicleBody {
    pub fn new(tree: Option<Tree>, position: Vec2, heading_rad: f32) -> Self {
        let calm = WindModel { from_deg: 0.0, speed_m_s: 0.0, gust_m_s: 0.0 };
        Self { runner: tree.map(|tree| Runner::new(tree, position, calm)), drive: Drive::new(position, heading_rad) }
    }

    /// One tick of the tree, then of the drive. A path point a vehicle drives past (it cannot
    /// turn onto it) counts as reached: the runner is placed on it, so the tree moves on.
    pub fn tick(&mut self, def: &VehicleDef, world: &World, dt: f32) {
        let goal = self.runner.as_mut().and_then(|runner| {
            runner.tick(world, dt);
            runner.goal()
        });
        let was_ahead = goal.is_some_and(|g| self.drive.is_ahead_of(g.point));
        self.drive.step(def, goal, dt);
        let passed = goal.filter(|g| !g.stop && was_ahead && !self.drive.is_ahead_of(g.point));
        if let Some(runner) = self.runner.as_mut() {
            runner.position = passed.map_or(self.drive.position, |g| g.point);
        }
    }
}

#[cfg(test)]
mod tests;
