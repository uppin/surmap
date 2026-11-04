//! The people of a manifest: a survivor's fields and the rules `SceneManifest::from_json` enforces
//! on them (height range, `glb` override path).

use serde::Deserialize;

use super::{is_relative_gltf, Element, ManifestError, SceneManifest};

/// A survivor at an ENU pose (feet at `position_enu`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Person {
    pub id: String,
    pub position_enu: [f32; 3],
    pub coat: String,
    pub skin: String,
    /// What the person does over time; standing still when absent.
    #[serde(default)]
    pub behaviour: Option<crate::behaviour::Tree>,
    /// How the person holds themself when not walking.
    #[serde(default)]
    pub pose: crate::figure_anim::Pose,
    /// The way a posed person faces, counter-clockwise from east.
    #[serde(default)]
    pub yaw_deg: f32,
    /// Body height (0.9–2.2 m); the rig's own height when absent.
    #[serde(default)]
    pub height_m: Option<f32>,
    /// Overrides the figure's rig for this person.
    #[serde(default)]
    pub glb: Option<String>,
}

/// A person's height range, m (the survivors of a survey: a child to a tall adult).
const PERSON_HEIGHT_M: (f32, f32) = (0.9, 2.2);

impl SceneManifest {
    /// Each person: `height_m` in 0.9–2.2, a `glb` override that is a relative glTF path.
    pub(super) fn validate_people(&self) -> Result<(), ManifestError> {
        for element in &self.elements {
            let Element::Person(person) = element else {
                continue;
            };
            if let Some(height) = person.height_m {
                if !(PERSON_HEIGHT_M.0..=PERSON_HEIGHT_M.1).contains(&height) {
                    return Err(ManifestError::Invalid(format!(
                        "person {}: height_m {height} must be {}–{} m",
                        person.id, PERSON_HEIGHT_M.0, PERSON_HEIGHT_M.1
                    )));
                }
            }
            if let Some(glb) = &person.glb {
                if !is_relative_gltf(glb) {
                    return Err(ManifestError::BadAssetPath(glb.clone()));
                }
            }
        }
        Ok(())
    }
}
