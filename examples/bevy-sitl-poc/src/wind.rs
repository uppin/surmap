//! The scenario's one wind: from the manifest's `weather.wind`, it drives Feronia's
//! vegetation, the fire's spread and the particles' drift.


use bevy::math::Vec2;

/// Meteorological wind: `from_deg` is where it blows *from*, clockwise from north.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WindModel {
    pub from_deg: f32,
    pub speed_m_s: f32,
    pub gust_m_s: f32,
}

/// Gust period (s): a slow swell the vegetation and smoke follow.
pub const GUST_PERIOD_S: f32 = 7.0;

impl WindModel {
    /// The air's velocity at `t_s`, ENU metres per second, pointing where it blows *to*.
    pub fn velocity_enu(&self, t_s: f32) -> Vec2 {
        let swell = (std::f32::consts::TAU * t_s / GUST_PERIOD_S).sin();
        let speed = (self.speed_m_s + self.gust_m_s * swell).max(0.0);
        self.toward() * speed
    }

    /// Unit vector (ENU) the wind blows toward: opposite of the compass bearing it comes from.
    fn toward(&self) -> Vec2 {
        let from = self.from_deg.to_radians();
        Vec2::new(-from.sin(), -from.cos())
    }

    /// Feronia's wind at `t_s`: Bevy xz direction (east +x, north −z), strength speed/15 in 0..1.
    pub fn feronia(&self, t_s: f32) -> bevy_feronia::prelude::Wind {
        let velocity = self.velocity_enu(t_s);
        let direction = self.toward();
        bevy_feronia::prelude::Wind {
            direction: Vec2::new(direction.x, -direction.y),
            strength: (velocity.length() / 15.0).clamp(0.0, 1.0),
            ..bevy_feronia::prelude::Wind::from(bevy_feronia::prelude::WindPreset::Mild)
        }
    }
}

impl From<&crate::scene_manifest::WindDef> for WindModel {
    fn from(wind: &crate::scene_manifest::WindDef) -> Self {
        Self {
            from_deg: wind.from_deg,
            speed_m_s: wind.speed_m_s,
            gust_m_s: wind.gust_m_s,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn westerly(speed: f32, gust: f32) -> WindModel {
        WindModel {
            from_deg: 270.0,
            speed_m_s: speed,
            gust_m_s: gust,
        }
    }

    #[test]
    fn a_westerly_blows_towards_the_east() {
        let v = westerly(6.0, 0.0).velocity_enu(0.0);

        assert!(v.abs_diff_eq(Vec2::new(6.0, 0.0), 1e-4), "{v:?}");
    }

    #[test]
    fn a_northerly_blows_towards_the_south() {
        let v = WindModel {
            from_deg: 0.0,
            speed_m_s: 3.0,
            gust_m_s: 0.0,
        }
        .velocity_enu(0.0);

        assert!(v.abs_diff_eq(Vec2::new(0.0, -3.0), 1e-4), "{v:?}");
    }

    #[test]
    fn gusts_swell_the_speed_within_the_gust_amplitude() {
        let wind = westerly(6.0, 2.0);

        let speeds: Vec<f32> = (0..70)
            .map(|i| wind.velocity_enu(i as f32 * 0.1).length())
            .collect();

        assert!(speeds.iter().all(|s| (4.0 - 1e-3..=8.0 + 1e-3).contains(s)));
        assert!(speeds.iter().cloned().fold(0.0, f32::max) > 7.9);
    }

    #[test]
    fn feronia_points_east_as_bevy_plus_x_and_scales_strength_by_fifteen() {
        let wind = westerly(6.0, 0.0).feronia(0.0);

        assert!(
            wind.direction.abs_diff_eq(Vec2::new(1.0, 0.0), 1e-4),
            "{:?}",
            wind.direction
        );
        assert!((wind.strength - 0.4).abs() < 1e-4);
    }

    #[test]
    fn feronia_strength_saturates_at_one() {
        assert_eq!(westerly(40.0, 0.0).feronia(0.0).strength, 1.0);
    }
}
