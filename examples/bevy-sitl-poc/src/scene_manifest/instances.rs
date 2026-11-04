//! Placed model instances and their collider kinds.
//!
//! Split out of `scene_manifest` for the file-length gate; the parent
//! re-exports these names, which is where callers have always reached them.

use bevy::prelude::Transform;
use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ColliderKind {
    None,
    Box,
    Trimesh,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct ModelInstance {
    pub id: String,
    pub glb: String,
    pub position_enu: [f32; 3],
    #[serde(default)]
    pub yaw_deg: f32,
    #[serde(default = "crate::scene_manifest::instances::unit_scale")]
    pub scale: f32,
    pub collider: ColliderKind,
    #[serde(default)]
    pub ground_truth: bool,
    /// Ground-truth kind (`car`, `collapsed_building`, …); `model` when unnamed.
    #[serde(default = "default_kind")]
    pub kind: String,
    /// `false` drops the model's normal maps: Bevy ignores `KHR_texture_transform` on a normal
    /// texture, so a micro-flake map tiled 30× in glTF lands as one coarse speckle over the body.
    #[serde(default = "keeps_normal_maps")]
    pub normal_maps: bool,
}

fn keeps_normal_maps() -> bool {
    true
}

fn default_kind() -> String {
    "model".into()
}

pub fn unit_scale() -> f32 {
    1.0
}

