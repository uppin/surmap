//! The building preset files as Bevy assets, so they are fetched like every other runtime file
//! (natively from disk, in the browser over HTTP) and never compiled in.

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::reflect::TypePath;

use super::look::BuildingLook;
use crate::building_fire::BuildingFireTuning;
use crate::building_style::{DistrictPreset, FacadePreset, RoofPreset};

macro_rules! json_asset {
    ($asset:ident, $loader:ident, $def:ty, $extension:literal) => {
        #[derive(Asset, TypePath, Debug)]
        pub struct $asset(pub $def);

        #[derive(Default, TypePath)]
        pub struct $loader;

        impl AssetLoader for $loader {
            type Asset = $asset;
            type Settings = ();
            type Error = std::io::Error;

            async fn load(
                &self,
                reader: &mut dyn Reader,
                _settings: &(),
                _context: &mut LoadContext<'_>,
            ) -> Result<$asset, std::io::Error> {
                let mut bytes = Vec::new();
                reader.read_to_end(&mut bytes).await?;
                let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
                <$def>::from_json(&text)
                    .map($asset)
                    .map_err(std::io::Error::other)
            }

            fn extensions(&self) -> &[&str] {
                &[$extension]
            }
        }
    };
}

json_asset!(FacadeAsset, FacadeLoader, FacadePreset, "facade.json");
json_asset!(RoofAsset, RoofLoader, RoofPreset, "roof.json");
json_asset!(
    DistrictAsset,
    DistrictLoader,
    DistrictPreset,
    "district.json"
);
json_asset!(TuningAsset, TuningLoader, BuildingFireTuning, "fire.json");
json_asset!(LookAsset, LookLoader, BuildingLook, "look.json");
