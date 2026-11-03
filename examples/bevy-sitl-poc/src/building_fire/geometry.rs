//! Footprint geometry for the building fire model: how close two footprints are, which way one
//! lies from the other, and points along a footprint's wall.

use bevy::math::Vec2;

/// The closest point to `p` on the segment `a`–`b`.
fn closest_on_segment(p: Vec2, a: Vec2, b: Vec2) -> Vec2 {
    let edge = b - a;
    let length_sq = edge.length_squared();
    if length_sq <= f32::EPSILON {
        return a;
    }
    a + edge * ((p - a).dot(edge) / length_sq).clamp(0.0, 1.0)
}

fn edges(polygon: &[Vec2]) -> impl Iterator<Item = (Vec2, Vec2)> + '_ {
    polygon
        .iter()
        .copied()
        .zip(polygon.iter().copied().cycle().skip(1))
}

/// The closest pair of points between two polygons' walls: `(on a, on b)`.
pub fn closest_points(a: &[Vec2], b: &[Vec2]) -> (Vec2, Vec2) {
    let mut best = (a[0], b[0]);
    let mut best_d = f32::MAX;
    for &p in a {
        for (s, e) in edges(b) {
            let q = closest_on_segment(p, s, e);
            if p.distance_squared(q) < best_d {
                best_d = p.distance_squared(q);
                best = (p, q);
            }
        }
    }
    for &p in b {
        for (s, e) in edges(a) {
            let q = closest_on_segment(p, s, e);
            if p.distance_squared(q) < best_d {
                best_d = p.distance_squared(q);
                best = (q, p);
            }
        }
    }
    best
}

/// Points along every wall of `polygon`, at most `step_m` apart (the vertices included).
pub fn wall_points(polygon: &[Vec2], step_m: f32) -> Vec<Vec2> {
    let mut points = Vec::new();
    for (s, e) in edges(polygon) {
        let pieces = ((s.distance(e) / step_m).ceil() as usize).max(1);
        points.extend((0..pieces).map(|i| s.lerp(e, i as f32 / pieces as f32)));
    }
    points
}

/// The centre of a polygon's vertices.
pub fn centroid(polygon: &[Vec2]) -> Vec2 {
    polygon.iter().copied().sum::<Vec2>() / polygon.len() as f32
}
