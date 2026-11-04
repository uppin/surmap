//! The figure's look and gait (`assets/behaviour/person.figure.json`): its definition, the
//! humanoid model it may wear, and the asset loader that reads it.

use std::collections::HashMap;

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::prelude::{Handle, Resource};
use bevy::reflect::TypePath;
use serde::Deserialize;

use crate::figure_anim::Pose;

/// The figure's gait and turn (`assets/behaviour/person.figure.json`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FigureDef {
    /// Seconds a turn takes to ease to the new heading.
    pub yaw_ease_s: f32,
    /// Height of one step's bob, m.
    pub bob_m: f32,
    /// Steps per second at `reference_speed_m_s`; faster walking steps faster in proportion.
    pub steps_per_s: f32,
    /// The walking speed `steps_per_s` is quoted at, m/s.
    pub reference_speed_m_s: f32,
    /// A dark visor on the front of the head, so the heading reads (on the capsule figure only).
    #[serde(default)]
    pub visor: Option<Visor>,
    /// A rigged humanoid glTF the figure wears instead of the capsule.
    #[serde(default)]
    pub model: Option<FigureModel>,
    /// The `person` ground-truth box (east, north, up m) over the feet; it holds the body
    /// whatever way the figure faces.
    #[serde(default = "default_body_m")]
    pub body_m: [f32; 3],
    /// A model for a person who holds a pose the figure's own model carries no clip for (a
    /// sitting person on a sit model). Keys are `lying`, `sitting` or `waving`; each validates
    /// like `model` and must carry a `rig`.
    #[serde(default)]
    pub pose_models: HashMap<Pose, FigureModel>,
}

fn default_body_m() -> [f32; 3] {
    [0.6, 0.6, 1.8]
}

/// A humanoid glTF: scaled and turned so it stands on the figure's feet facing its front (-z).
/// Without a `rig` it is posed from its first animation clip: at `clip_s` standing, played in
/// step while walking. With one, its named clips play by speed and pose (`figure_anim`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FigureModel {
    pub glb: String,
    #[serde(default = "one")]
    pub scale: f32,
    #[serde(default)]
    pub yaw_deg: f32,
    #[serde(default)]
    pub clip_s: f32,
    /// Multiply the model's colours by the person's `coat` (a survivor in a hi-vis coverall).
    #[serde(default)]
    pub coat_tint: bool,
    /// The model's named clips and the speeds they cover; its coat and skin material slots.
    #[serde(default)]
    pub rig: Option<crate::figure_anim::RigDef>,
}

fn one() -> f32 {
    1.0
}

/// A box on the figure (`size_m` x, y, z in the figure's frame; `offset_m` from its feet, −z is
/// its front), solid `colour` (sRGB).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Visor {
    pub size_m: [f32; 3],
    pub offset_m: [f32; 3],
    pub colour: [f32; 3],
}

impl FigureModel {
    /// The clip a person in `pose` holds on this model, when its rig names one.
    pub fn clip_for(&self, pose: Pose) -> Option<&str> {
        self.rig.as_ref().and_then(|rig| rig.clip_for(pose))
    }

    fn validate(&self, what: &str) -> Result<(), String> {
        if !crate::scene_manifest::is_relative_gltf(&self.glb) {
            return Err(format!("{what} glb {:?} must be a .glb/.gltf inside assets/", self.glb));
        }
        if self.scale <= 0.0 {
            return Err(format!("{what} scale must be > 0"));
        }
        if let Some(rig) = &self.rig {
            rig.validate().map_err(|e| format!("{what}: {e}"))?;
        }
        Ok(())
    }
}

impl FigureDef {
    /// The model a person in `pose` is drawn on: the pose's own model, else the figure's; its file
    /// replaced by the person's `rig_glb` when they name one; its speeds scaled to their `height_m`.
    pub fn model_for(&self, pose: Pose, height_m: Option<f32>, rig_glb: Option<&str>) -> Option<FigureModel> {
        let mut model = self.pose_models.get(&pose).or(self.model.as_ref())?.clone();
        if let Some(glb) = rig_glb {
            model.glb = glb.to_owned();
        }
        model.rig = model.rig.map(|rig| rig.at_height(height_m));
        Some(model)
    }

    pub fn from_json(text: &str) -> Result<Self, String> {
        let def: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if def.yaw_ease_s <= 0.0 {
            return Err("yaw_ease_s must be > 0".into());
        }
        if def.bob_m < 0.0 {
            return Err("bob_m must be >= 0".into());
        }
        if def.steps_per_s <= 0.0 {
            return Err("steps_per_s must be > 0".into());
        }
        if def.reference_speed_m_s <= 0.0 {
            return Err("reference_speed_m_s must be > 0".into());
        }
        if let Some(model) = &def.model {
            model.validate("model")?;
        }
        if def.body_m.iter().any(|side| *side <= 0.0) {
            return Err("body_m sides must be > 0".into());
        }
        if def.model.is_none() && !def.pose_models.is_empty() {
            return Err("pose_models needs the figure's own model, which carries standing".into());
        }
        for (pose, model) in &def.pose_models {
            if *pose == Pose::Standing {
                return Err("pose_models must not name standing: the figure's model carries it".into());
            }
            model.validate(&format!("pose_models {}", pose.name()))?;
            if model.rig.is_none() {
                return Err(format!("pose_models {} needs a rig naming its clips", pose.name()));
            }
        }
        if def.model.as_ref().is_some_and(|model| model.rig.is_some()) {
            for pose in [Pose::Standing, Pose::Waving, Pose::Lying, Pose::Sitting] {
                let named = def.pose_models.get(&pose).or(def.model.as_ref()).and_then(|model| model.clip_for(pose));
                if named.is_none() {
                    return Err(format!(
                        "no clip for pose {}: name one in the model's rig clips or in pose_models.{}",
                        pose.name(),
                        pose.name()
                    ));
                }
            }
        }
        Ok(def)
    }
}


/// The figure's gait and turn, loaded from `behaviour/person.figure.json`.
#[derive(Resource)]
pub struct FigureLook(pub Handle<FigureAsset>);

#[derive(Asset, TypePath, Debug)]
pub struct FigureAsset(pub FigureDef);

#[derive(Default, TypePath)]
pub struct FigureLoader;

impl AssetLoader for FigureLoader {
    type Asset = FigureAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _: &(),
        _: &mut LoadContext<'_>,
    ) -> Result<FigureAsset, std::io::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
        FigureDef::from_json(&text)
            .map(FigureAsset)
            .map_err(std::io::Error::other)
    }

    fn extensions(&self) -> &[&str] {
        &["figure.json"]
    }
}

