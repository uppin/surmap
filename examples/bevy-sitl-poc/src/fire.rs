//! Wildfire spread: a Huygens ellipse with its rear focus at the ignition point, stretched
//! downwind (`docs/simulation/bevy-simulation.md` § *Weather, wind and fire*). Pure, so the
//! front, the burnt area and the ground truth the recorder writes all come from one place.


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

/// The front's ellipse at one instant: centre, unit head direction and its two semi-axes.
struct Ellipse {
    centre: Vec2,
    head: Vec2,
    a: f32,
    b: f32,
}

impl Ellipse {
    fn point(&self, theta: f32) -> Vec2 {
        let side = self.head.perp();
        self.centre + self.head * (self.a * theta.cos()) + side * (self.b * theta.sin())
    }

    fn contains(&self, p: Vec2) -> bool {
        let rel = p - self.centre;
        let u = rel.dot(self.head);
        let v = rel.dot(self.head.perp());
        u * u * self.b * self.b + v * v * self.a * self.a <= self.a * self.a * self.b * self.b
    }
}

impl FireSpec {
    /// The ellipse at `t_s`, or none before the fire starts. The burning time stops growing
    /// once the head reaches `max_radius_m`, so no point is ever farther than that.
    fn ellipse(&self, t_s: f32, wind: Vec2) -> Option<Ellipse> {
        let burning = t_s - self.start_s;
        if burning < 0.0 {
            return None;
        }
        let speed = wind.length();
        let head = if speed > 1e-4 { wind / speed } else { Vec2::X };
        let head_rate = self.spread_m_s * (1.0 + self.head_wind_gain * speed);
        let length_to_breadth = 1.0 + self.lb_wind_gain * speed;
        let root = (length_to_breadth * length_to_breadth - 1.0).sqrt();
        let back_rate = head_rate * (length_to_breadth - root) / (length_to_breadth + root);
        let burning = burning.min(self.max_radius_m / head_rate);
        let a = (head_rate + back_rate) * burning / 2.0;
        Some(Ellipse {
            centre: self.ignition + head * (a - back_rate * burning),
            head,
            a,
            b: a / length_to_breadth,
        })
    }

    /// The front at `t_s` under `wind` (ENU m/s toward), `points` vertices counter-clockwise;
    /// empty before `start_s`.
    pub fn perimeter(&self, t_s: f32, wind: Vec2, points: usize) -> Vec<Vec2> {
        let Some(ellipse) = self.ellipse(t_s, wind) else {
            return Vec::new();
        };
        (0..points)
            .map(|i| ellipse.point(std::f32::consts::TAU * i as f32 / points as f32))
            .collect()
    }

    /// Whether `p` (ENU) is inside the burnt area at `t_s`.
    pub fn burnt(&self, p: Vec2, t_s: f32, wind: Vec2) -> bool {
        self.ellipse(t_s, wind)
            .is_some_and(|ellipse| ellipse.a > 0.0 && ellipse.contains(p))
    }
}

/// One `fire_perimeter.jsonl` line: the frame's time and every fire's ENU front (an empty
/// polygon before it ignites).
pub fn perimeter_line(t_ns: u64, fronts: &[(String, Vec<Vec2>)]) -> String {
    let fires: Vec<serde_json::Value> = fronts
        .iter()
        .map(|(id, polygon)| {
            let points: Vec<[f32; 2]> = polygon.iter().map(|p| [p.x, p.y]).collect();
            serde_json::json!({"id": id, "polygon_enu": points})
        })
        .collect();
    serde_json::json!({"t_ns": t_ns, "fires": fires}).to_string()
}

impl From<&crate::scene_manifest::FireDef> for FireSpec {
    fn from(fire: &crate::scene_manifest::FireDef) -> Self {
        Self {
            ignition: Vec2::new(fire.ignition_enu[0], fire.ignition_enu[1]),
            start_s: fire.start_s,
            spread_m_s: fire.spread_m_s,
            max_radius_m: fire.max_radius_m,
            head_wind_gain: fire.head_wind_gain,
            lb_wind_gain: fire.lb_wind_gain,
        }
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
    fn a_perimeter_line_carries_the_frame_time_and_each_fires_polygon() {
        let line = perimeter_line(
            1_000_000_000,
            &[("front-1".to_owned(), vec![Vec2::new(-19.0, 60.0), Vec2::new(-20.0, 61.0)])],
        );

        let parsed: serde_json::Value = serde_json::from_str(&line).expect("json");
        assert_eq!(
            parsed,
            serde_json::json!({"t_ns": 1_000_000_000u64, "fires": [{"id": "front-1", "polygon_enu": [[-19.0, 60.0], [-20.0, 61.0]]}]})
        );
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
