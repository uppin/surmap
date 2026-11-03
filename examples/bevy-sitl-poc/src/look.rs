//! The photographic camera stack of visual spec §5, identical on every
//! camera so the chase view, the stills and both eyes expose alike. The
//! sky and its image light come from `sky.rs` once the HDRI has loaded.

use bevy::anti_alias::taa::TemporalAntiAliasing;
use bevy::camera::Exposure;
use bevy::core_pipeline::tonemapping::Tonemapping;
use bevy::light::ShadowFilteringMethod;
use bevy::pbr::{DistanceFog, FogFalloff};
use bevy::post_process::bloom::Bloom;
use bevy::prelude::*;
use bevy::render::view::Msaa;

use crate::world::CameraLook;

/// Which camera a stack is for.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lens {
    /// The on-screen chase view: TAA and bloom.
    Chase,
    /// Eyes and review stills: geometry-stable MSAA, no jitter, no bloom.
    Still,
}

/// Fog before the manifest arrives; `apply_haze` replaces it.
const DEFAULT_VISIBILITY_M: f32 = 600.0;

pub fn haze(visibility_m: f32) -> DistanceFog {
    DistanceFog {
        color: Color::srgba(0.74, 0.70, 0.62, 1.0),
        directional_light_color: Color::srgba(1.0, 0.90, 0.75, 0.4),
        directional_light_exponent: 24.0,
        falloff: FogFalloff::from_visibility_colors(
            visibility_m,
            Color::srgb(0.45, 0.42, 0.38),
            Color::srgb(0.78, 0.74, 0.66),
        ),
    }
}

/// Until the manifest says otherwise (spec §5).
const DEFAULT_EV100: f32 = 14.0;

pub fn photographic(commands: &mut EntityCommands, lens: Lens) {
    commands.insert((
        Camera3d::default(),
        bevy::render::view::Hdr,
        Exposure { ev100: DEFAULT_EV100 },
        Tonemapping::AgX,
        haze(DEFAULT_VISIBILITY_M),
        // Feronia's GPU-instanced grass is culled per camera.
        bevy_eidolon::prepass::CullComputeCamera,
    ));
    match lens {
        Lens::Chase => {
            commands.insert((
                Msaa::Off,
                TemporalAntiAliasing::default(),
                ShadowFilteringMethod::Temporal,
                Bloom { intensity: 0.05, ..Bloom::NATURAL },
            ));
        }
        Lens::Still => {
            commands.insert((Msaa::Sample4, ShadowFilteringMethod::Gaussian));
        }
    }
}

/// The manifest's haze and exposure onto every camera.
pub fn apply_look(look: Option<Res<CameraLook>>, mut cameras: Query<(&mut DistanceFog, &mut Exposure)>) {
    let Some(look) = look else { return };
    if !look.is_changed() {
        return;
    }
    for (mut fog, mut exposure) in &mut cameras {
        *fog = haze(look.fog_visibility_m);
        exposure.ev100 = look.exposure_ev100;
    }
}
