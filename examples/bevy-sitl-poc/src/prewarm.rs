//! Screenshot mode only: before a still is taken, run the particle clock ahead so each plume is as
//! old as the scene it is shot in. Hanabi has no pre-warm, so the effect clock (not the
//! simulation's) is sped up in steps of at most `MAX_STEP_S` until the longest `prewarm_s` among
//! the scene's effects has passed. Effects with no pre-warm (short-lived flames) are in their
//! steady state either way, so one clock advance serves every effect.

use bevy::ecs::system::SystemParam;
use bevy::prelude::*;
use bevy_hanabi::{EffectSimulation, EffectSimulationTime};

use crate::fxdef::FxAsset;
use crate::shots::{RunMode, Shots};
use crate::wildfire::FireEmitter;
use crate::world::{scene_ready, PendingModel, SceneState};

/// Effect seconds one rendered frame may advance: small enough that emitted particles stay a
/// continuous plume rather than clumps.
const MAX_STEP_S: f32 = 0.2;
/// Frames to wait for the scene's emitters to appear before giving up on pre-warming.
const MAX_WAIT_FRAMES: u32 = 300;
/// The frame length assumed when the virtual clock has not advanced yet.
const FALLBACK_DT_S: f32 = 1.0 / 60.0;

#[derive(Resource, Default)]
pub struct Prewarm {
    advanced_s: f32,
    waited_frames: u32,
    started: bool,
    done: bool,
}

/// The clock speed that advances the effects `remaining_s` more, at most `MAX_STEP_S` per frame of
/// `frame_dt_s` real seconds.
pub fn prewarm_speed(remaining_s: f32, frame_dt_s: f32) -> f32 {
    (remaining_s.min(MAX_STEP_S) / frame_dt_s.max(1.0e-4)).max(1.0)
}

/// What the pre-warm reads.
#[derive(SystemParam)]
pub struct PrewarmInputs<'w, 's> {
    mode: Res<'w, RunMode>,
    scene: Option<Res<'w, SceneState>>,
    assets: Res<'w, AssetServer>,
    pending: Query<'w, 's, (), With<PendingModel>>,
    fxs: Res<'w, Assets<FxAsset>>,
    emitters: Query<'w, 's, (), With<FireEmitter>>,
    frame: Res<'w, Time<Virtual>>,
}

pub fn prewarm_effects(
    inputs: PrewarmInputs,
    mut clock: ResMut<Time<EffectSimulation>>,
    mut state: ResMut<Prewarm>,
    shots: Option<ResMut<Shots>>,
) {
    if inputs.mode.screenshot.is_none() || state.done {
        return;
    }
    let ready = inputs
        .scene
        .as_ref()
        .is_some_and(|scene| scene_ready(scene, &inputs.assets, inputs.pending.iter().count()));
    if !ready {
        return;
    }
    let target_s = inputs.fxs.iter().map(|(_, fx)| fx.0.prewarm_s).fold(0.0, f32::max);
    let waiting = inputs.emitters.is_empty() && state.waited_frames < MAX_WAIT_FRAMES;
    if waiting {
        state.waited_frames += 1;
    }
    // The settle wait for the still starts only once the plumes are as old as the scene.
    if let Some(mut shots) = shots {
        shots.settled_frames = 0;
    }
    if state.started {
        state.advanced_s += clock.delta_secs();
    }
    let remaining_s = target_s - state.advanced_s;
    if waiting || remaining_s <= 0.0 {
        if !waiting {
            clock.set_relative_speed(1.0);
            state.done = true;
        }
        return;
    }
    state.started = true;
    let dt = inputs.frame.delta_secs();
    let dt = if dt > 0.0 { dt } else { FALLBACK_DT_S };
    clock.set_relative_speed(prewarm_speed(remaining_s, dt));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_long_pre_warm_runs_the_effects_in_bounded_steps() {
        let speed = prewarm_speed(20.0, 1.0 / 60.0);

        assert!((speed * (1.0 / 60.0) - MAX_STEP_S).abs() < 1e-4);
    }

    #[test]
    fn the_last_step_stops_on_the_target() {
        let speed = prewarm_speed(0.05, 1.0 / 60.0);

        assert!((speed * (1.0 / 60.0) - 0.05).abs() < 1e-4);
    }

    #[test]
    fn the_effects_never_run_slower_than_real_time() {
        assert_eq!(prewarm_speed(0.0001, 1.0), 1.0);
    }
}
