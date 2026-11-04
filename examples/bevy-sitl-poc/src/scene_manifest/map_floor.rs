//! The map floor's manifest shape and its ENU geometry.
//!
//! Split out of `scene_manifest` for the file-length gate; the parent
//! re-exports `MapFloor`, which is where callers have always reached it.

use serde::Deserialize;

use super::{validate_asset_path, ManifestError};

/// A GPS-bounded map floor. `sw`/`ne` are [lat, lon] WGS84 degrees; the floor's
/// ENU origin is the bbox centre and its plane is sized from the bbox, so every
/// element keeps its ENU pose and sits on the map it was placed over.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct MapFloor {
    pub sw: [f64; 2],
    pub ne: [f64; 2],
    pub texture: String,
    pub zoom: u32,
}

impl MapFloor {
    /// Centre [lat, lon] and size [east, north] in metres (the snapshot's ENU rule:
    /// 111 320 m per degree of latitude, longitude scaled by cos(latitude)).
    pub fn centre_and_size_enu(&self) -> ([f64; 2], [f64; 2]) {
        let centre = [(self.sw[0] + self.ne[0]) / 2.0, (self.sw[1] + self.ne[1]) / 2.0];
        let north = (self.ne[0] - self.sw[0]) * 111_320.0;
        let east = (self.ne[1] - self.sw[1]) * 111_320.0 * centre[0].to_radians().cos();
        (centre, [east, north])
    }

    pub(crate) fn validate(&self) -> Result<(), ManifestError> {
        let invalid = |reason: &str| ManifestError::Invalid(format!("map_floor: {reason}"));
        for (name, point) in [("sw", self.sw), ("ne", self.ne)] {
            if !(-85.0..=85.0).contains(&point[0]) || !(-180.0..=180.0).contains(&point[1]) {
                return Err(invalid(&format!("{name} is outside the map's range")));
            }
        }
        if !(self.sw[0] < self.ne[0] && self.sw[1] < self.ne[1]) {
            return Err(invalid("sw must be south and west of ne"));
        }
        if !self.texture.ends_with(".png") {
            return Err(invalid("texture must be a .png"));
        }
        if self.zoom > 18 {
            return Err(invalid("zoom must be in 0..=18"));
        }
        let (_, [east, north]) = self.centre_and_size_enu();
        if east > 1000.0 || north > 1000.0 {
            return Err(invalid("a floor is at most 1000 m a side"));
        }
        Ok(())
    }
}

