//! Rain: one GPU emitter in a box around each viewing camera (chase and review stills), as
//! dense as the scenario's `rain_mm_h` and blown by the same wind as everything else.

use bevy::prelude::*;
use bevy_hanabi::prelude::*;

use super::{bevy_wind, rate_per_emitter, ready_effect, sim_seconds, Wildfire};
use crate::fx::{self, Emission, WIND_PROPERTY};
use crate::fxdef::FxAsset;
use crate::record::SimTime;
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

/// Rain falls in a box around each viewing camera (chase and review stills).
#[allow(clippy::type_complexity)]
pub fn rain_around_cameras(
    mut commands: Commands,
    time: Res<Time>,
    sim: Res<SimTime>,
    scene: Option<ResMut<Wildfire>>,
    fxs: Res<Assets<FxAsset>>,
    mut effects: ResMut<Assets<EffectAsset>>,
    cameras: Query<
        (Entity, &GlobalTransform),
        (
            Or<(With<ChaseCam>, With<crate::shots::OverviewCam>)>,
            Without<RainTagged>,
        ),
    >,
    mut rain: Query<(&RainEmitter, &mut Transform, &mut EffectProperties)>,
    positions: Query<&GlobalTransform, Without<RainEmitter>>,
) {
    let Some(mut scene) = scene else { return };
    let Some(runtime) = scene.rain.as_mut() else {
        return;
    };
    if runtime.effect.is_none() {
        let Some(def) = ready_effect(&fxs, &runtime.fx) else {
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
    let wind = bevy_wind(scene.wind.velocity_enu(sim_seconds(&sim, &time)));
    for (emitter, mut transform, mut properties) in &mut rain {
        if let Ok(at) = positions.get(emitter.camera) {
            transform.translation = at.translation();
        }
        properties.set(WIND_PROPERTY, wind.into());
    }
}
