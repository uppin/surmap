//! A declarative effect (`fx/<name>.fx.json`, parsed by `fxdef.rs`) turned into a `bevy_hanabi`
//! GPU particle effect. The effect asset carries a `wind` property (Bevy xz, m/s) the owner
//! updates every frame: spawn velocity is `up` plus `wind_coupling × wind`, so flames lean and
//! smoke bends with the one scenario wind.

use bevy::prelude::*;
use bevy_hanabi::prelude::*;

use crate::fxdef::{Blend, FxDef, Shape};

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
    let texture_slot = writer.lit(0u32).expr();
    let roundness = RoundModifier {
        roundness: writer.lit(def.round).expr(),
    };
    let gravity = AccelModifier::new(writer.lit(Vec3::new(0.0, def.motion.gravity, 0.0)).expr());

    let sprite_index = def.flipbook.as_ref().map(|book| {
        // Each particle plays the sheet at `fps`, started at a phase its own lifetime picks.
        let frames = (book.columns * book.rows) as i32;
        let phase = writer.attr(Attribute::LIFETIME) * writer.lit(37.0_f32);
        let frame = (writer.attr(Attribute::AGE) * writer.lit(book.fps) + phase)
            .cast(ScalarType::Int)
            .rem(writer.lit(frames));
        SetAttributeModifier::new(Attribute::SPRITE_INDEX, frame.expr())
    });
    let mut module = writer.finish();
    if def.flipbook.is_some() || def.shape == Shape::SoftDisc {
        module.add_texture_slot("shape");
    }
    let mut asset = EffectAsset::new(
        capacity(def, rate_per_s),
        SpawnerSettings::rate(rate_per_s.into()),
        module,
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
    if let (Some(book), Some(index)) = (&def.flipbook, sprite_index) {
        asset = asset
            .update(index)
            .render(ParticleTextureModifier {
                texture_slot,
                sample_mapping: ImageSampleMapping::Modulate,
            })
            .render(FlipbookModifier {
                sprite_grid_size: UVec2::new(book.columns, book.rows),
            });
    } else if def.shape == Shape::SoftDisc {
        asset = asset.render(ParticleTextureModifier {
            texture_slot,
            sample_mapping: ImageSampleMapping::ModulateOpacityFromR,
        });
    } else if def.round > 0.0 {
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

/// The image an effect's particles sample: its flipbook's sheet, else the generated soft disc.
pub fn sprite(
    def: &FxDef,
    discs: &mut SoftDiscs,
    images: &mut Assets<Image>,
    assets: &AssetServer,
) -> Option<Handle<Image>> {
    match (&def.flipbook, def.shape) {
        (Some(book), _) => Some(assets.load(book.texture.clone())),
        (None, Shape::SoftDisc) => Some(discs.handle(images, def.softness)),
        (None, _) => None,
    }
}

/// The radial alpha texture of a soft disc (red channel): 1 at the centre, 0 at the rim.
/// `softness` 0 keeps a hard edge; 1 fades smoothly all the way from the centre.
pub fn soft_disc_image(softness: f32) -> Image {
    const SIDE: u32 = 64;
    let width = softness.clamp(0.0, 1.0).max(1.0e-3);
    let mut bytes = Vec::with_capacity((SIDE * SIDE * 4) as usize);
    for y in 0..SIDE {
        for x in 0..SIDE {
            let (dx, dy) = (
                (x as f32 + 0.5) / SIDE as f32 * 2.0 - 1.0,
                (y as f32 + 0.5) / SIDE as f32 * 2.0 - 1.0,
            );
            let t = ((1.0 - (dx * dx + dy * dy).sqrt()) / width).clamp(0.0, 1.0);
            let alpha = (t * t * (3.0 - 2.0 * t) * 255.0).round() as u8;
            bytes.extend([alpha, alpha, alpha, 255]);
        }
    }
    Image::new(
        bevy::render::render_resource::Extent3d {
            width: SIDE,
            height: SIDE,
            depth_or_array_layers: 1,
        },
        bevy::render::render_resource::TextureDimension::D2,
        bytes,
        bevy::render::render_resource::TextureFormat::Rgba8UnormSrgb,
        bevy::asset::RenderAssetUsages::default(),
    )
}

/// Generated soft-disc textures, one per distinct softness.
#[derive(Resource, Default)]
pub struct SoftDiscs(Vec<(u32, Handle<Image>)>);

impl SoftDiscs {
    pub fn handle(&mut self, images: &mut Assets<Image>, softness: f32) -> Handle<Image> {
        let key = softness.to_bits();
        if let Some((_, handle)) = self.0.iter().find(|(k, _)| *k == key) {
            return handle.clone();
        }
        let handle = images.add(soft_disc_image(softness));
        self.0.push((key, handle.clone()));
        handle
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn alpha_at(image: &Image, x: u32, y: u32) -> u8 {
        image.data.as_ref().expect("pixels")[((y * 64 + x) * 4) as usize]
    }

    #[test]
    fn a_soft_disc_is_opaque_in_the_middle_and_clear_at_the_corners() {
        let image = soft_disc_image(1.0);

        assert!(alpha_at(&image, 32, 32) > 240);
        assert_eq!(alpha_at(&image, 0, 0), 0);
    }

    #[test]
    fn a_harder_disc_stays_opaque_further_out() {
        let (hard, soft) = (soft_disc_image(0.1), soft_disc_image(1.0));

        assert!(alpha_at(&hard, 32 + 20, 32) > alpha_at(&soft, 32 + 20, 32));
    }
}
