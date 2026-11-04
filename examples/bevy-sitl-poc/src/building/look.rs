//! `building/look.json`: the numbers of a building's shape and fire look that no preset owns —
//! roof geometry, the dark interior, the glow behind broken panes, soot and the fire's light.

use serde::Deserialize;

use crate::building_style::RoofShape;

/// A splitmix64 hash of a building's seed and a window's index.
fn hash(building_seed: u64, window: u32) -> u64 {
    let mut z = building_seed
        .wrapping_add(u64::from(window).wrapping_mul(0x9E37_79B9_7F4A_7C15))
        .wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct FlatRoof {
    pub parapet_m: f32,
    pub parapet_thickness_m: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct PitchedRoof {
    pub pitch_deg: f32,
    pub eave_m: f32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct RoofShapes {
    pub flat: FlatRoof,
    pub gabled: PitchedRoof,
    pub hipped: PitchedRoof,
    pub pyramidal: PitchedRoof,
}

/// The dark volume behind the walls a broken pane shows.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Interior {
    pub inset_m: f32,
    pub colour: [f32; 3],
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Soot {
    pub height_m: f32,
    pub colour: [f32; 3],
    pub alpha: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct BlazeLight {
    pub colour: [f32; 3],
    pub lumens_per_floor: f32,
    pub range_m: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct FireLook {
    /// How far inside the wall the glow plane stands, m.
    pub glow_inset_m: f32,
    pub soot: Soot,
    pub light: BlazeLight,
    /// Each window's glow is scaled within `1 ± glow_variation`, seeded per window.
    #[serde(default)]
    pub glow_variation: f32,
    /// How fast a window's glow flickers, Hz.
    #[serde(default)]
    pub glow_flicker_hz: f32,
}

impl FireLook {
    /// The scale of window `window`'s glow in building `building_seed` at `t_s`: in
    /// `[1 − glow_variation, 1 + glow_variation]`, different per window, flickering in time.
    pub fn window_glow(&self, building_seed: u64, window: u32, t_s: f32) -> f32 {
        let bits = hash(building_seed, window);
        let unit = |shift: u32| ((bits >> shift) & 0xFFFF) as f32 / 65535.0;
        let steady = unit(0) * 2.0 - 1.0;
        let phase = unit(16) * std::f32::consts::TAU;
        let flicker = (std::f32::consts::TAU * self.glow_flicker_hz * t_s + phase).sin();
        1.0 + self.glow_variation * (0.6 * steady + 0.4 * flicker)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Shopfront {
    /// Ground floors drawn with the district's shopfront window ratio.
    pub floors: u32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BuildingLook {
    pub roof_shapes: RoofShapes,
    pub shopfront: Shopfront,
    pub interior: Interior,
    pub fire: FireLook,
}

impl BuildingLook {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let look: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        let shapes = &look.roof_shapes;
        for pitched in [shapes.gabled, shapes.hipped, shapes.pyramidal] {
            if !(pitched.pitch_deg > 0.0 && pitched.pitch_deg < 80.0) || pitched.eave_m < 0.0 {
                return Err("roof pitch must be in (0, 80) degrees and the eave >= 0".into());
            }
        }
        if look.roof_shapes.flat.parapet_m < 0.0 || look.roof_shapes.flat.parapet_thickness_m <= 0.0
        {
            return Err("the parapet must have a height >= 0 and a thickness > 0".into());
        }
        if look.interior.inset_m <= look.fire.glow_inset_m {
            return Err("the interior must stand deeper than the glow plane".into());
        }
        Ok(look)
    }
}

impl RoofShapes {
    /// `(pitch_deg, eave_m)` of a pitched shape.
    pub fn pitched(&self, shape: RoofShape) -> Option<PitchedRoof> {
        match shape {
            RoofShape::Flat => None,
            RoofShape::Gabled => Some(self.gabled),
            RoofShape::Hipped => Some(self.hipped),
            RoofShape::Pyramidal => Some(self.pyramidal),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_shipped_look_is_valid() {
        let text = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/building/look.json"
        ))
        .expect("shipped");

        let look = BuildingLook::from_json(&text).expect("valid");

        assert_eq!(look.roof_shapes.pitched(RoofShape::Flat), None);
        assert_eq!(
            look.roof_shapes
                .pitched(RoofShape::Gabled)
                .map(|p| p.pitch_deg),
            Some(35.0)
        );
    }

    #[test]
    fn an_interior_shallower_than_the_glow_is_refused() {
        let text = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/assets/building/look.json"
        ))
        .expect("shipped");
        let broken = text.replace("\"inset_m\": 0.6", "\"inset_m\": 0.1");

        assert!(BuildingLook::from_json(&broken).is_err());
    }
}
