//! Standard materials for preset material definitions, loaded once per distinct definition.

use std::collections::BTreeMap;

use bevy::prelude::*;

use crate::scene_manifest::PbrTextureSet;
use crate::textures::{load_texture_set, tiled_material, RoughnessPacking};

pub struct Surfaces<'a> {
    pub assets: &'a AssetServer,
    packing: &'a RoughnessPacking,
    pub materials: &'a mut Assets<StandardMaterial>,
    /// Every texture a material waits on, so the scene is not ready before it arrives.
    pub pending: &'a mut Vec<UntypedHandle>,
    cache: BTreeMap<(String, [u32; 3], bool), Handle<StandardMaterial>>,
}

impl<'a> Surfaces<'a> {
    pub fn new(
        assets: &'a AssetServer,
        packing: &'a RoughnessPacking,
        materials: &'a mut Assets<StandardMaterial>,
        pending: &'a mut Vec<UntypedHandle>,
    ) -> Self {
        Self {
            assets,
            packing,
            materials,
            pending,
            cache: BTreeMap::new(),
        }
    }

    /// `def` as a material, UVs in metres, multiplied by `tint`. `key` names the definition
    /// (its preset path and part) so two buildings of one preset share one material.
    pub fn material(
        &mut self,
        key: &str,
        def: &PbrTextureSet,
        tint: Option<[f32; 3]>,
        double_sided: bool,
    ) -> Handle<StandardMaterial> {
        let tint_bits = tint.unwrap_or([1.0; 3]).map(f32::to_bits);
        let cache_key = (key.to_owned(), tint_bits, double_sided);
        if let Some(handle) = self.cache.get(&cache_key) {
            return handle.clone();
        }
        let maps = def
            .base_color
            .as_ref()
            .map(|_| load_texture_set(self.assets, def, self.packing));
        if let Some(maps) = &maps {
            self.pending.extend(
                maps.base_color
                    .iter()
                    .chain(&maps.normal)
                    .chain(&maps.arm)
                    .chain(&maps.roughness)
                    .map(|h| h.clone().untyped()),
            );
        }
        let tint = tint.map_or(Color::WHITE, |[r, g, b]| Color::srgb(r, g, b));
        let mut material = tiled_material(def, maps.as_ref(), Vec2::ONE, tint, None);
        if double_sided {
            material.cull_mode = None;
            material.double_sided = true;
        }
        let handle = self.materials.add(material);
        self.cache.insert(cache_key, handle.clone());
        handle
    }

    /// A plain colour, with no maps.
    pub fn flat(&mut self, material: StandardMaterial) -> Handle<StandardMaterial> {
        self.materials.add(material)
    }
}
