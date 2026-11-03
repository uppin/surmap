//! Rain: one GPU emitter in a box around each viewing camera (chase and review stills), as
//! dense as the scenario's `rain_mm_h` and blown by the same wind as everything else.

use bevy::prelude::*;
use bevy_hanabi::prelude::*;

use super::{bevy_wind, rate_per_emitter, ready_effect, EffectAssets, SimClock, Wildfire};
use crate::fx::{self, Emission, WIND_PROPERTY};
use crate::fxdef::FxAsset;
use crate::shots::OverviewCam;
use crate::ChaseCam;

#[derive(Component)]
pub struct RainEmitter {
    camera: Entity,
}

#[derive(Component)]
pub struct RainTagged;

/// The rain effect of a scenario that rains, once its file has loaded.
pub(super) struct RainRuntime {
    pub(super) rain_mm_h: f32,
    pub(super) fx: Handle<FxAsset>,
    pub(super) effect: Option<Handle<EffectAsset>>,
}

/// A viewing camera (chase or review still) that has no rain box yet.
type UnrainedCamera = (Or<(With<ChaseCam>, With<OverviewCam>)>, Without<RainTagged>);

/// Rain falls in a box around each viewing camera (chase and review stills).
pub fn rain_around_cameras(
    mut commands: Commands,
    clock: SimClock,
    scene: Option<ResMut<Wildfire>>,
    mut fx_assets: EffectAssets,
    cameras: Query<(Entity, &GlobalTransform), UnrainedCamera>,
    mut rain: Query<(&RainEmitter, &mut Transform, &mut EffectProperties)>,
    positions: Query<&GlobalTransform, Without<RainEmitter>>,
) {
    let Some(mut scene) = scene else { return };
    let EffectAssets { fxs, effects } = &mut fx_assets;
    let Some(runtime) = scene.rain.as_mut() else {
        return;
    };
    if runtime.effect.is_none() {
        let Some(def) = ready_effect(fxs, &runtime.fx) else {
            return;
        };
        let side = def.box_m.unwrap_or(60.0);
        let rate = runtime.rain_mm_h * rate_per_emitter(&def, 1.0);
        runtime.effect = Some(effects.add(fx::effect(
            &def,
            "rain",
            rate,
            Emission::Box(Vec3::new(side, side / 2.0, side)),
        )));
    }
    let Some(effect) = runtime.effect.clone() else {
        return;
    };
    for (camera, at) in &cameras {
        commands.entity(camera).insert(RainTagged);
        commands.spawn((
            Name::new("Rain"),
            RainEmitter { camera },
            ParticleEffect::new(effect.clone()),
            EffectProperties::default(),
            Transform::from_translation(at.translation()),
        ));
    }
    let wind = bevy_wind(scene.wind.velocity_enu(clock.now()));
    for (emitter, mut transform, mut properties) in &mut rain {
        if let Ok(at) = positions.get(emitter.camera) {
            transform.translation = at.translation();
        }
        properties.set(WIND_PROPERTY, wind.into());
    }
}
