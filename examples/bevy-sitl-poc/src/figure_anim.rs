//! A person's rigged figure (docs/simulation/bevy-simulation.md § *The figure*): which animation
//! clips play, how strongly and how fast, from the person's speed and pose. Pure, and evaluated
//! on the simulation clock — the app seeks every player to `clip_time`, never lets it free-run —
//! so a still at `--at t` and a recording replay identically. Every number lives in the figure's
//! `rig` block (`assets/behaviour/person.figure.json`), never here.

#![allow(dead_code)]

use serde::Deserialize;

/// How a person holds themself when not walking: the poses a survey finds people in.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Pose {
    #[default]
    Standing,
    /// An injured survivor on the ground.
    Lying,
    Sitting,
    /// Signalling for help.
    Waving,
}

impl Pose {
    /// The pose's name in tracks and manifests (`lying`, …).
    pub fn name(self) -> &'static str {
        // TODO(pr-2): implement
        todo!("Pose::name")
    }
}

/// One of the rig's animation clips.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Clip {
    Idle,
    Walk,
    Run,
    Wave,
    Sit,
    Lie,
}

/// The rig's clips, by the glTF's animation names.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Clips {
    pub idle: String,
    pub walk: String,
    pub run: String,
    pub wave: String,
    pub sit: String,
    pub lie: String,
}

/// The figure's rigged glTF and how its clips map to motion (`person.figure.json` → `rig`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RigDef {
    pub glb: String,
    pub clips: Clips,
    /// Ground covered per second by the walk and run clips at rate 1 (no foot slide).
    pub walk_ground_m_s: f32,
    pub run_ground_m_s: f32,
    /// Where locomotion crosses from walking to running.
    pub run_above_m_s: f32,
    /// Seconds a crossfade takes, between locomotion clips and into or out of a pose.
    pub blend_s: f32,
    /// The rig's height at scale 1.
    pub standing_height_m: f32,
    /// glTF material names that take the person's coat and skin materials.
    #[serde(default)]
    pub coat_slots: Vec<String>,
    #[serde(default)]
    pub skin_slots: Vec<String>,
}

impl RigDef {
    /// Every speed, height and blend > 0, `run_ground_m_s` > `walk_ground_m_s`, the glTF a
    /// relative `.glb`/`.gltf` path; the reason names the field.
    pub fn validate(&self) -> Result<(), String> {
        // TODO(pr-2): implement
        todo!("RigDef::validate")
    }
}

/// One clip at a weight (the weights of a frame sum to 1) and a playback rate.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Weighted {
    pub clip: Clip,
    pub weight: f32,
    pub rate: f32,
}

/// The clips a person shows at `speed_m_s` in `pose`: idle when standing still, walk at
/// `speed / walk_ground_m_s`, run at `speed / run_ground_m_s` above `run_above_m_s`, crossfaded
/// around the threshold; a posed person who is not moving shows the pose's clip (`lie` and `sit`
/// held, `wave` looped). Moving always shows locomotion, whatever the pose.
pub fn locomotion(rig: &RigDef, speed_m_s: f32, pose: Pose) -> Vec<Weighted> {
    // TODO(pr-2): implement
    let _ = (rig, speed_m_s, pose);
    todo!("locomotion")
}

/// Where in a clip of `duration_s` a person is at `now_s`, playing at `rate` from `phase`
/// (0..1 of a cycle, per person): wrapped when `looping`, held at the end when not.
pub fn clip_time(now_s: f32, phase: f32, rate: f32, duration_s: f32, looping: bool) -> f32 {
    // TODO(pr-2): implement
    let _ = (now_s, phase, rate, duration_s, looping);
    todo!("clip_time")
}

/// The uniform scale that makes the rig `height_m` tall; 1 when the person names no height.
pub fn rig_scale(rig: &RigDef, height_m: Option<f32>) -> f32 {
    // TODO(pr-2): implement
    let _ = (rig, height_m);
    todo!("rig_scale")
}

#[cfg(test)]
mod tests;
