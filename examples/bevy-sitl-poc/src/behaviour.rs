//! Behaviour trees for scenario objects and the wind (changeset § *Behaviour-tree JSON*): parsed
//! from the manifest's inline JSON, ticked at a fixed rate in simulation time. Pure, so a run is
//! deterministic and the recorder's tracks come from the same place the renderer moves bodies.

use bevy::math::Vec2;
use serde::de::Error as _;
use serde::{Deserialize, Deserializer};
use serde_json::Value;

use crate::fire::FireSpec;
use crate::wind::WindModel;

mod geometry;
mod tick;
mod validate;

#[cfg(test)]
mod tests;

pub use tick::Runner;

/// Ticks per simulated second.
pub const TICK_HZ: f32 = 10.0;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SucceedOn {
    All,
    One,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "node", rename_all = "snake_case", deny_unknown_fields)]
pub enum Kind {
    Sequence {
        children: Vec<Node>,
    },
    Selector {
        children: Vec<Node>,
    },
    Parallel {
        children: Vec<Node>,
        succeed_on: SucceedOn,
    },
    Repeat {
        child: Box<Node>,
        times: Option<u32>,
    },
    Invert {
        child: Box<Node>,
    },
    TimeAfter {
        s: f32,
    },
    NearFire {
        within_m: f32,
    },
    NearObject {
        object: String,
        within_m: f32,
    },
    WindAbove {
        speed_m_s: f32,
    },
    Idle {
        s: f32,
    },
    MoveTo {
        enu: [f32; 2],
        speed_m_s: f32,
    },
    FollowPath {
        enu: Vec<[f32; 2]>,
        speed_m_s: f32,
    },
    Wander {
        radius_m: f32,
        speed_m_s: f32,
        seed: u64,
    },
    FleeFromFire {
        speed_m_s: f32,
        clearance_m: f32,
    },
    SetWind {
        from_deg: f32,
        speed_m_s: f32,
        gust_m_s: f32,
        over_s: f32,
    },
}

/// One node of a tree: its address (`id`, unique within its tree) and what it does.
#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: Option<String>,
    pub kind: Kind,
}

impl<'de> Deserialize<'de> for Node {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let mut value = Value::deserialize(deserializer)?;
        // The node's `id` addresses it in its tree; the kind's own fields never see it.
        let id = match value.as_object_mut().and_then(|fields| fields.remove("id")) {
            None | Some(Value::Null) => None,
            Some(Value::String(id)) => Some(id),
            Some(other) => {
                return Err(D::Error::custom(format!(
                    "a node's id must be a string, not {other}"
                )))
            }
        };
        let kind = serde_json::from_value(value).map_err(D::Error::custom)?;
        Ok(Self { id, kind })
    }
}

/// What a tree drives: a body on the ground, or the scenario's wind.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Target {
    Object,
    Wind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Running,
    Success,
    Failure,
}

/// A whole tree, as the manifest declares it: its root node (`behaviour` on a `person`, or
/// `weather.wind.behaviour`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(transparent)]
pub struct Tree {
    pub root: Node,
}

/// Everything a tick may read: simulation time, the fires, the current wind, other bodies.
pub struct World<'a> {
    pub t_s: f32,
    pub fires: &'a [FireSpec],
    /// Other burning ground (ENU polygons, e.g. burning buildings' footprints): `near_fire` and
    /// `flee_from_fire` treat them like a wildfire's perimeter.
    pub burning_areas: &'a [Vec<Vec2>],
    pub wind: &'a WindModel,
    pub objects: &'a [(String, Vec2)],
}
