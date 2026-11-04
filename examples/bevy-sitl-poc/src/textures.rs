//! Tiled PBR materials from the manifest's texture sets, and the mip
//! chains Bevy does not build for loaded JPGs.
//!
//! Without mips a 2K texture tiled across a 140 m block aliases into
//! shimmer at distance, which is wrong on screen and worse for stereo
//! matching. Every image the asset server loads (manifest textures and
//! glTF textures alike) gets a box-filtered chain once it arrives.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use bevy::asset::AssetEvent;
use bevy::image::{
    ImageAddressMode, ImageFilterMode, ImageLoaderSettings, ImageSampler, ImageSamplerDescriptor,
};
use bevy::math::Affine2;
use bevy::prelude::*;
use bevy::render::render_resource::TextureFormat;

use crate::scene_manifest::PbrTextureSet;

/// The maps of one texture set, loaded with the right colour space.
#[derive(Clone)]
pub struct TextureSetHandles {
    pub base_color: Option<Handle<Image>>,
    pub normal: Option<Handle<Image>>,
    pub arm: Option<Handle<Image>>,
    pub roughness: Option<Handle<Image>>,
}

/// The roughness-only maps in flight and the `metallic` of the set each belongs to: once loaded,
/// each is repacked so its blue channel carries that metalness (a shared file takes the last
/// set's value).
#[derive(Resource, Clone, Default)]
pub struct RoughnessPacking(Arc<Mutex<HashMap<AssetId<Image>, f32>>>);

impl RoughnessPacking {
    fn register(&self, id: AssetId<Image>, metallic: f32) {
        self.0.lock().expect("packing registry").insert(id, metallic);
    }

    fn metallic_of(&self, id: AssetId<Image>) -> Option<f32> {
        self.0.lock().expect("packing registry").get(&id).copied()
    }
}

fn tiled_sampler() -> ImageSampler {
    ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: ImageAddressMode::Repeat,
        address_mode_v: ImageAddressMode::Repeat,
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        anisotropy_clamp: 8,
        ..default()
    })
}

fn load_map(assets: &AssetServer, path: &str, srgb: bool) -> Handle<Image> {
    assets.load_with_settings(path.to_owned(), move |settings: &mut ImageLoaderSettings| {
        settings.is_srgb = srgb;
        settings.sampler = tiled_sampler();
    })
}

pub fn load_texture_set(
    assets: &AssetServer,
    set: &PbrTextureSet,
    packing: &RoughnessPacking,
) -> TextureSetHandles {
    let handles = TextureSetHandles {
        base_color: set.base_color.as_deref().map(|p| load_map(assets, p, true)),
        normal: set.normal.as_deref().map(|p| load_map(assets, p, false)),
        arm: set.arm.as_deref().map(|p| load_map(assets, p, false)),
        roughness: set.roughness.as_deref().map(|p| load_map(assets, p, false)),
    };
    if let (None, Some(roughness)) = (&handles.arm, &handles.roughness) {
        packing.register(roughness.id(), set.metallic);
    }
    handles
}

/// A manifest material as a `StandardMaterial`, tiled by world size:
/// `size_m` metres of surface carry `size_m * uv_scale` repeats (spec §3).
/// Solid definitions (no maps) use their scalar values only.
pub fn tiled_material(
    def: &PbrTextureSet,
    maps: Option<&TextureSetHandles>,
    size_m: Vec2,
    tint: Color,
    uv_scale: Option<f32>,
) -> StandardMaterial {
    let [r, g, b] = def.color;
    let (base, tint) = (Color::srgb(r, g, b).to_linear(), tint.to_linear());
    let colour = LinearRgba::rgb(base.red * tint.red, base.green * tint.green, base.blue * tint.blue);
    let mut material = StandardMaterial {
        base_color: Color::LinearRgba(colour),
        perceptual_roughness: def.perceptual_roughness,
        metallic: def.metallic,
        reflectance: def.reflectance,
        clearcoat: def.clearcoat,
        ..default()
    };
    let Some(maps) = maps else { return material };
    material.base_color_texture = maps.base_color.clone();
    material.normal_map_texture = maps.normal.clone();
    material.uv_transform = Affine2::from_scale(size_m * uv_scale.unwrap_or(def.uv_scale));
    match (&maps.arm, &maps.roughness) {
        (Some(arm), _) => {
            // ARM: R occlusion, G roughness, B metalness — B is real here.
            material.metallic_roughness_texture = Some(arm.clone());
            material.occlusion_texture = Some(arm.clone());
            material.metallic = 1.0;
            material.perceptual_roughness = 1.0;
        }
        (None, Some(roughness)) => {
            // The map is repacked on load (`pack_metallic_roughness`): G roughness, B this set's
            // metalness, so both factors pass the texture through.
            material.metallic_roughness_texture = Some(roughness.clone());
            material.metallic = 1.0;
            material.perceptual_roughness = 1.0;
        }
        (None, None) => {}
    }
    material
}

/// A glTF metallic-roughness map from a greyscale roughness map (R used) and a preset's scalar
/// `metallic`: R 255, G the roughness, B `metallic`·255, A 255 — so roughness-only sets keep metal.
pub fn pack_metallic_roughness(roughness_rgba: &[u8], metallic: f32) -> Vec<u8> {
    let metal = (metallic.clamp(0.0, 1.0) * 255.0).round() as u8;
    roughness_rgba
        .chunks_exact(4)
        .flat_map(|pixel| [255, pixel[0], metal, 255])
        .collect()
}

/// Box-filtered mip chain for a tightly packed RGBA8 image.
pub fn build_mip_chain(data: &[u8], width: u32, height: u32) -> (Vec<u8>, u32) {
    let mut out = data.to_vec();
    let (mut w, mut h) = (width as usize, height as usize);
    let mut level_start = 0;
    let mut levels = 1;
    while w > 1 || h > 1 {
        let (nw, nh) = ((w / 2).max(1), (h / 2).max(1));
        let mut next = vec![0u8; nw * nh * 4];
        for y in 0..nh {
            for x in 0..nw {
                for c in 0..4 {
                    let mut sum = 0u32;
                    for (dx, dy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
                        let sx = (x * 2 + dx).min(w - 1);
                        let sy = (y * 2 + dy).min(h - 1);
                        sum += u32::from(out[level_start + (sy * w + sx) * 4 + c]);
                    }
                    next[(y * nw + x) * 4 + c] = ((sum + 2) / 4) as u8;
                }
            }
        }
        level_start = out.len();
        out.extend_from_slice(&next);
        (w, h) = (nw, nh);
        levels += 1;
    }
    (out, levels)
}

/// Give every asset-server image without mips its chain.
pub fn generate_mips(
    mut events: MessageReader<AssetEvent<Image>>,
    mut images: ResMut<Assets<Image>>,
    packing: Res<RoughnessPacking>,
) {
    for event in events.read() {
        let AssetEvent::LoadedWithDependencies { id } = event else { continue };
        let Some(image) = images.get_mut(*id) else { continue };
        let format = image.texture_descriptor.format;
        let rgba8 = matches!(format, TextureFormat::Rgba8Unorm | TextureFormat::Rgba8UnormSrgb);
        if !rgba8 || image.texture_descriptor.mip_level_count > 1 {
            continue;
        }
        let size = image.texture_descriptor.size;
        let Some(data) = image.data.as_ref() else { continue };
        if data.len() != (size.width * size.height * 4) as usize {
            continue;
        }
        let packed = packing.metallic_of(*id).map(|metallic| pack_metallic_roughness(data, metallic));
        let (chain, levels) = build_mip_chain(packed.as_deref().unwrap_or(data), size.width, size.height);
        image.data = Some(chain);
        image.texture_descriptor.mip_level_count = levels;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_four_by_four_image_gets_three_levels_averaged_by_two_by_two() {
        let mut data = vec![0u8; 4 * 4 * 4];
        data[..16].copy_from_slice(&[100; 16]);

        let (chain, levels) = build_mip_chain(&data, 4, 4);

        assert_eq!(levels, 3);
        assert_eq!(chain.len(), (16 + 4 + 1) * 4);
        assert_eq!(&chain[64..68], &[50, 50, 50, 50]);
        assert_eq!(chain[64 + 16..].len(), 4);
    }

    #[test]
    fn a_non_square_image_halves_each_side_down_to_one() {
        let (_, levels) = build_mip_chain(&[0; 8 * 2 * 4], 8, 2);

        assert_eq!(levels, 4);
    }
}
