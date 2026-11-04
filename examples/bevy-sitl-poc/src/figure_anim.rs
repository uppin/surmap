//! A person's rigged figure (docs/simulation/bevy-simulation.md § *The figure*): which animation
//! clips play, how strongly and how fast, from the person's speed and pose. Pure, and evaluated
//! on the simulation clock — the app seeks every player to `clip_time`, never lets it free-run —
//! so a still at `--at t` and a recording replay identically. Every number lives in the figure's
//! `rig` block (`assets/behaviour/person.figure.json`), never here.

use serde::Deserialize;

use crate::scene_manifest::is_relative_gltf;

/// How a person holds themself when not walking: the poses a survey finds people in.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Deserialize)]
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
        match self {
            Self::Standing => "standing",
            Self::Lying => "lying",
            Self::Sitting => "sitting",
            Self::Waving => "waving",
        }
    }

    /// The clip a person holds in this pose (a standing person idles).
    pub fn clip(self) -> Clip {
        match self {
            Self::Standing => Clip::Idle,
            Self::Lying => Clip::Lie,
            Self::Sitting => Clip::Sit,
            Self::Waving => Clip::Wave,
        }
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

impl Clip {
    /// Whether the clip repeats. A sit or a fall is held on its last frame instead.
    pub fn looping(self) -> bool {
        !matches!(self, Self::Sit | Self::Lie)
    }
}

/// The rig's clips, by the glTF's animation names. Walk and run and idle every rig carries; a rig
/// names the poses' clips it has, and each pose needs one in the figure's primary rig or in its
/// pose rig (`FigureDef::pose_rigs`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Clips {
    pub idle: String,
    pub walk: String,
    pub run: String,
    #[serde(default)]
    pub wave: Option<String>,
    #[serde(default)]
    pub sit: Option<String>,
    #[serde(default)]
    pub lie: Option<String>,
}

impl Clips {
    /// The glTF animation name `clip` plays under, when the rig names one.
    pub fn name(&self, clip: Clip) -> Option<&str> {
        match clip {
            Clip::Idle => Some(&self.idle),
            Clip::Walk => Some(&self.walk),
            Clip::Run => Some(&self.run),
            Clip::Wave => self.wave.as_deref(),
            Clip::Sit => self.sit.as_deref(),
            Clip::Lie => self.lie.as_deref(),
        }
    }
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
    /// The clip a person in `pose` holds on this rig, when the rig names one.
    pub fn clip_for(&self, pose: Pose) -> Option<&str> {
        self.clips.name(pose.clip())
    }

    /// This rig scaled to a person of `height_m` (the rig's own height when `None`): its ground
    /// speeds and walk-to-run threshold grow with the rig, so the person's feet keep pace with
    /// their clips. Height and blend are unchanged.
    pub fn at_height(&self, height_m: Option<f32>) -> Self {
        let scale = rig_scale(self, height_m);
        let mut scaled = self.clone();
        scaled.walk_ground_m_s *= scale;
        scaled.run_ground_m_s *= scale;
        scaled.run_above_m_s *= scale;
        scaled
    }

    /// Every speed, height and blend > 0, `run_ground_m_s` > `walk_ground_m_s`, the glTF a
    /// relative `.glb`/`.gltf` path; the reason names the field.
    pub fn validate(&self) -> Result<(), String> {
        let positive = [
            ("walk_ground_m_s", self.walk_ground_m_s),
            ("run_ground_m_s", self.run_ground_m_s),
            ("run_above_m_s", self.run_above_m_s),
            ("blend_s", self.blend_s),
            ("standing_height_m", self.standing_height_m),
        ];
        for (field, value) in positive {
            if value.is_nan() || value <= 0.0 {
                return Err(format!("rig {field} must be > 0"));
            }
        }
        if self.run_ground_m_s <= self.walk_ground_m_s {
            return Err("rig run_ground_m_s must be greater than walk_ground_m_s".into());
        }
        if !is_relative_gltf(&self.glb) {
            return Err(format!("rig glb {:?} must be a relative .glb or .gltf path", self.glb));
        }
        Ok(())
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
    if speed_m_s <= 0.0 {
        let clip = match pose {
            Pose::Standing => Clip::Idle,
            Pose::Lying => Clip::Lie,
            Pose::Sitting => Clip::Sit,
            Pose::Waving => Clip::Wave,
        };
        return vec![Weighted { clip, weight: 1.0, rate: 1.0 }];
    }
    // The crossfade spans a quarter of the gap between the two ground speeds either side of the
    // threshold, so a walk never starts to blend before its own speed.
    let half_band = (rig.run_ground_m_s - rig.walk_ground_m_s) / 4.0;
    let run_weight = ((speed_m_s - (rig.run_above_m_s - half_band)) / (2.0 * half_band)).clamp(0.0, 1.0);
    vec![
        Weighted {
            clip: Clip::Walk,
            weight: 1.0 - run_weight,
            rate: speed_m_s / rig.walk_ground_m_s,
        },
        Weighted {
            clip: Clip::Run,
            weight: run_weight,
            rate: speed_m_s / rig.run_ground_m_s,
        },
    ]
}

/// Where in a clip of `duration_s` a person is at `now_s`, playing at `rate` from `phase`
/// (0..1 of a cycle, per person): wrapped when `looping`, held at the end when not.
pub fn clip_time(now_s: f32, phase: f32, rate: f32, duration_s: f32, looping: bool) -> f32 {
    if duration_s <= 0.0 {
        return 0.0;
    }
    let time = now_s * rate + phase * duration_s;
    if looping {
        time.rem_euclid(duration_s)
    } else {
        time.clamp(0.0, duration_s)
    }
}

/// The uniform scale that makes the rig `height_m` tall; 1 when the person names no height. Both
/// heights are heights to the millimetre, so they are read as such before the ratio is taken: a
/// 1.62 m person on a 1.8 m rig scales by exactly 0.9, where the widened f32 values land on the
/// neighbouring float.
pub fn rig_scale(rig: &RigDef, height_m: Option<f32>) -> f32 {
    fn millimetres(metres: f32) -> f64 {
        (f64::from(metres) * 1000.0).round() / 1000.0
    }
    height_m.map_or(1.0, |height| (millimetres(height) / millimetres(rig.standing_height_m)) as f32)
}

#[cfg(test)]
mod tests;
