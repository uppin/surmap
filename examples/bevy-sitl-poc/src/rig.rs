//! The stereo rig, built from the runtime camera profile: once the
//! manifest has named it and it has loaded, both eyes are spawned with
//! the profile's exact projection, offsets and mount.

use bevy::asset::io::Reader;
use bevy::asset::{AssetLoader, LoadContext};
use bevy::camera::RenderTarget;
use bevy::prelude::*;

use crate::calibration::{CalibratedProjection, CameraModel, CameraProfile};
use crate::look::{photographic, Lens};
use crate::shots::shot_target;
use crate::world::SceneState;
use crate::{LeftEye, RightEye, StereoFeeds};

#[derive(Asset, TypePath, Debug)]
pub struct ProfileAsset(pub CameraProfile);

#[derive(Default, TypePath)]
pub struct ProfileLoader;

impl AssetLoader for ProfileLoader {
    type Asset = ProfileAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(&self, reader: &mut dyn Reader, _settings: &(), _context: &mut LoadContext<'_>) -> Result<ProfileAsset, std::io::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
        CameraProfile::from_json(&text).map(ProfileAsset).map_err(|e| std::io::Error::other(format!("{e:?}")))
    }

    fn extensions(&self) -> &[&str] {
        &["camera.json"]
    }
}

/// The profile handle the world asked for.
#[derive(Resource)]
pub struct RigSource(pub Handle<ProfileAsset>);

/// Eye render range (m).
const NEAR_M: f32 = 0.1;
const FAR_M: f32 = 600.0;

impl CameraProfile {
    /// The rig's rotation in the drone body frame: pitched down about body x.
    pub fn mount_rotation(&self) -> Quat {
        Quat::from_rotation_x(-self.mount.pitch_deg.to_radians())
    }
}

/// Spawn both eyes once the profile is in; publishes `CameraProfile` and `StereoFeeds`.
pub fn spawn_rig(
    mut commands: Commands,
    source: Option<Res<RigSource>>,
    profiles: Res<Assets<ProfileAsset>>,
    existing: Option<Res<CameraProfile>>,
    mut images: ResMut<Assets<Image>>,
    mut scene: Option<ResMut<SceneState>>,
) {
    let (Some(source), None) = (source, existing) else { return };
    let Some(ProfileAsset(profile)) = profiles.get(&source.0) else { return };
    if profile.model != CameraModel::Pinhole {
        // Rendering a fisheye needs the remap pass (next step); refuse rather than lie.
        error!("camera profile {}: {:?} rendering is not available yet", profile.id, profile.model);
        commands.remove_resource::<RigSource>();
        if let Some(scene) = scene.as_mut() {
            scene.failed = Some(format!("unsupported camera model {:?}", profile.model));
        }
        return;
    }
    let left = shot_target(&mut images, profile.width, profile.height);
    let right = shot_target(&mut images, profile.width, profile.height);
    for (target, right_eye) in [(left.clone(), false), (right.clone(), true)] {
        let mut eye = commands.spawn((
            Camera { order: 1, ..default() },
            RenderTarget::Image(target.into()),
            Projection::custom(CalibratedProjection::of(profile, NEAR_M, FAR_M)),
            Transform::from_translation(profile.eye_translation_m(right_eye)),
        ));
        if right_eye {
            eye.insert(RightEye);
        } else {
            eye.insert(LeftEye);
        }
        photographic(&mut eye, Lens::Still);
    }
    commands.insert_resource(StereoFeeds { left, right });
    commands.insert_resource(profile.clone());
}
