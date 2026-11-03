//! Wildfire spread: a Huygens ellipse with its rear focus at the ignition point, stretched
//! downwind (changeset § *Fire model*). Pure, so the front, the burnt area and the ground truth
//! the recorder writes all come from one place.

#![allow(dead_code)]

use bevy::math::Vec2;

#[derive(Debug, Clone, PartialEq)]
pub struct FireSpec {
    pub ignition: Vec2,
    pub start_s: f32,
    pub spread_m_s: f32,
    pub max_radius_m: f32,
    pub head_wind_gain: f32,
    pub lb_wind_gain: f32,
}

impl FireSpec {
    /// The front at `t_s` under `wind` (ENU m/s toward), `points` vertices counter-clockwise;
    /// empty before `start_s`.
    pub fn perimeter(&self, t_s: f32, wind: Vec2, points: usize) -> Vec<Vec2> {
        let _ = (t_s, wind, points);
        todo!("fire perimeter")
    }

    /// Whether `p` (ENU) is inside the burnt area at `t_s`.
    pub fn burnt(&self, p: Vec2, t_s: f32, wind: Vec2) -> bool {
        let _ = (p, t_s, wind);
        todo!("burnt area")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn a_fire() -> FireSpec {
        FireSpec {
            ignition: Vec2::new(-20.0, 60.0),
            start_s: 2.0,
            spread_m_s: 0.15,
            max_radius_m: 35.0,
            head_wind_gain: 0.5,
            lb_wind_gain: 0.25,
        }
    }

    fn reach(perimeter: &[Vec2], origin: Vec2, direction: Vec2) -> f32 {
        perimeter
            .iter()
            .map(|p| (*p - origin).dot(direction))
            .fold(f32::MIN, f32::max)
    }

    #[test]
    fn nothing_burns_before_the_fire_starts() {
        let fire = a_fire();

        assert!(fire.perimeter(1.0, Vec2::ZERO, 48).is_empty());
        assert!(!fire.burnt(fire.ignition, 1.0, Vec2::ZERO));
    }

    #[test]
    fn without_wind_the_front_is_a_circle_growing_at_the_spread_rate() {
        let fire = a_fire();

        let front = fire.perimeter(42.0, Vec2::ZERO, 48);

        assert_eq!(front.len(), 48);
        assert!(
            front
                .iter()
                .all(|p| (p.distance(fire.ignition) - 6.0).abs() < 0.05),
            "radius 0.15 · 40 s"
        );
    }

    #[test]
    fn wind_pushes_the_head_downwind_and_holds_the_back() {
        let fire = a_fire();
        let east = Vec2::X;

        let front = fire.perimeter(42.0, east * 6.0, 96);

        let downwind = reach(&front, fire.ignition, east);
        let upwind = reach(&front, fire.ignition, -east);
        assert!(
            (downwind - 0.15 * 4.0 * 40.0).abs() < 0.2,
            "head rate (1 + 0.5 · 6) · 0.15, got {downwind}"
        );
        assert!(upwind < downwind / 4.0, "back {upwind} vs head {downwind}");
    }

    #[test]
    fn the_front_never_passes_the_maximum_radius() {
        let fire = a_fire();

        let front = fire.perimeter(10_000.0, Vec2::X * 6.0, 96);

        assert!(front
            .iter()
            .all(|p| p.distance(fire.ignition) <= fire.max_radius_m + 1e-3));
    }

    #[test]
    fn the_perimeter_winds_counter_clockwise() {
        let front = a_fire().perimeter(42.0, Vec2::X * 6.0, 48);

        let twice_area: f32 = front
            .iter()
            .zip(front.iter().cycle().skip(1))
            .map(|(a, b)| a.perp_dot(*b))
            .sum();

        assert!(twice_area > 0.0);
    }

    #[test]
    fn the_ignition_point_is_burnt_once_the_fire_runs_and_far_ground_is_not() {
        let fire = a_fire();

        assert!(fire.burnt(fire.ignition, 30.0, Vec2::X * 6.0));
        assert!(!fire.burnt(fire.ignition + Vec2::new(0.0, 30.0), 30.0, Vec2::X * 6.0));
    }
}
