//! A declarative effect (`fx/<name>.fx.json`, parsed by `fxdef.rs`) turned into a `bevy_hanabi`
//! GPU particle effect. The effect asset carries a `wind` property (Bevy xz, m/s) the owner
//! updates every frame: spawn velocity is `up` plus `wind_coupling × wind`, so flames lean and
//! smoke bends with the one scenario wind.

use bevy::prelude::*;
use bevy_hanabi::prelude::*;

use crate::fxdef::{Blend, FxDef};

/// The name of the wind property every effect built here declares.
pub const WIND_PROPERTY: &str = "wind";

/// Where particles appear.
pub enum Emission {
    /// A sphere of this radius (m) around the emitter.
    Around(f32),
    /// A box of this size (m) centred on the emitter (weather around a camera).
    Box(Vec3),
}

fn linear(colour: [f32; 3], intensity: f32, alpha: f32) -> Vec4 {
    let c = Color::srgb(colour[0], colour[1], colour[2]).to_linear();
    Vec4::new(
        c.red * intensity,
        c.green * intensity,
        c.blue * intensity,
        alpha,
    )
}

/// Particles alive at once at `rate_per_s`: the capacity one emitter needs (with headroom).
pub fn capacity(def: &FxDef, rate_per_s: f32) -> u32 {
    let live = (rate_per_s * def.lifetime_s[1] * 1.5).ceil() as u32 + 8;
    live.min(def.max_particles).max(8)
}

pub fn effect(def: &FxDef, name: &str, rate_per_s: f32, emission: Emission) -> EffectAsset {
    let writer = ExprWriter::new();
    let wind = writer.add_property(WIND_PROPERTY, Vec3::ZERO.into());

    let velocity = writer.lit(Vec3::new(0.0, def.motion.up, 0.0))
        + writer.prop(wind) * writer.lit(def.motion.wind_coupling);
    let init_velocity = SetAttributeModifier::new(Attribute::VELOCITY, velocity.expr());
    let init_age = SetAttributeModifier::new(Attribute::AGE, writer.lit(0.0_f32).expr());
    let init_lifetime = SetAttributeModifier::new(
        Attribute::LIFETIME,
        writer
            .lit(def.lifetime_s[0])
            .uniform(writer.lit(def.lifetime_s[1]))
            .expr(),
    );

    let mut colours = bevy_hanabi::Gradient::<Vec4>::new();
    for stop in &def.colour_gradient {
        colours.add_key(stop.0, linear(stop.1, stop.2, stop.3));
    }
    let mut sizes = bevy_hanabi::Gradient::<Vec3>::new();
    let ends = [def.size_m[0], def.size_m[1]];
    sizes.add_key(0.0, Vec3::new(ends[0] * def.stretch, ends[0], 1.0));
    sizes.add_key(1.0, Vec3::new(ends[1] * def.stretch, ends[1], 1.0));

    let position = match emission {
        Emission::Around(radius) => Position::Sphere(SetPositionSphereModifier {
            center: writer.lit(Vec3::ZERO).expr(),
            radius: writer.lit(radius).expr(),
            dimension: ShapeDimension::Volume,
        }),
        Emission::Box(size) => Position::Box(SetAttributeModifier::new(
            Attribute::POSITION,
            ((writer.rand(VectorType::VEC3F) - writer.lit(Vec3::splat(0.5))) * writer.lit(size))
                .expr(),
        )),
    };
    let roundness = RoundModifier {
        roundness: writer.lit(def.round).expr(),
    };
    let gravity = AccelModifier::new(writer.lit(Vec3::new(0.0, def.motion.gravity, 0.0)).expr());

    let mut asset = EffectAsset::new(
        capacity(def, rate_per_s),
        SpawnerSettings::rate(rate_per_s.into()),
        writer.finish(),
    )
    .with_name(name)
    .with_alpha_mode(match def.blend {
        Blend::Additive => bevy_hanabi::AlphaMode::Add,
        Blend::Alpha => bevy_hanabi::AlphaMode::Blend,
    });
    asset = match position {
        Position::Sphere(modifier) => asset.init(modifier),
        Position::Box(modifier) => asset.init(modifier),
    };
    asset = asset.init(init_velocity).init(init_age).init(init_lifetime);
    if def.motion.gravity != 0.0 {
        asset = asset.update(gravity);
    }
    asset = asset
        .render(ColorOverLifetimeModifier {
            gradient: colours,
            blend: ColorBlendMode::Overwrite,
            mask: ColorBlendMask::RGBA,
        })
        .render(SizeOverLifetimeModifier {
            gradient: sizes,
            screen_space_size: false,
        });
    if def.round > 0.0 {
        asset = asset.render(roundness);
    }
    if def.stretch != 1.0 {
        asset = asset.render(OrientModifier::new(OrientMode::AlongVelocity));
    }
    asset
}

enum Position {
    Sphere(SetPositionSphereModifier),
    Box(SetAttributeModifier),
}
