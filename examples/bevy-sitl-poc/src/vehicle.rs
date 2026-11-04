//! Vehicles that drive (docs/simulation/bevy-simulation.md § *Vehicles*). A vehicle's behaviour
//! tree says where it should go; `Drive` turns that into motion a real vehicle could make —
//! speed eased within its class's acceleration and braking, heading turned at most at its turn
//! rate. Pure, so a recording replays identically. Every number lives in
//! `assets/vehicle/<class>.vehicle.json`, never here.

#![allow(dead_code)]

use bevy::math::Vec2;
use serde::Deserialize;

use crate::behaviour::{Goal, Runner, Tree, World};
use crate::wind::WindModel;

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
        // TODO(pr-1): implement
        todo!("vehicle class file path")
    }

    /// The ground-truth kind tracks carry (`car`, `bus`, …).
    pub fn kind(self) -> &'static str {
        // TODO(pr-1): implement
        todo!("vehicle class kind")
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
    /// Trains: the carriage glTF and the distance between consecutive carriages' centres.
    #[serde(default)]
    pub carriage_glb: Option<String>,
    #[serde(default)]
    pub carriage_spacing_m: Option<f32>,
}

impl VehicleDef {
    /// Parse and validate: every size and limit > 0, a wheel radius when wheels are named, a
    /// carriage spacing > 0 when a carriage glTF is named.
    pub fn from_json(text: &str) -> Result<Self, String> {
        // TODO(pr-1): implement
        let _ = text;
        todo!("VehicleDef::from_json")
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
        // TODO(pr-1): implement
        let _ = (def, goal, dt, &self.trail);
        todo!("Drive::step")
    }

    /// The pose (ENU place, heading) of each of `cars` carriages, the k-th `k × spacing_m` behind
    /// the vehicle along its travelled path.
    pub fn carriage_poses(&self, cars: u32, spacing_m: f32) -> Vec<(Vec2, f32)> {
        // TODO(pr-1): implement
        let _ = (cars, spacing_m);
        todo!("Drive::carriage_poses")
    }
}

/// A wheel's rotation (rad) after rolling `distance_m`.
pub fn wheel_angle(distance_m: f32, radius_m: f32) -> f32 {
    // TODO(pr-1): implement
    let _ = (distance_m, radius_m);
    todo!("wheel_angle")
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

    /// One tick of the tree, then of the drive.
    pub fn tick(&mut self, def: &VehicleDef, world: &World, dt: f32) {
        // TODO(pr-1): implement
        let _ = (def, world, dt);
        todo!("VehicleBody::tick")
    }
}

#[cfg(test)]
mod tests;
