//! Ground-plane geometry for the tick: the seeded wander stream and distances to burning ground.

use bevy::math::Vec2;

/// A point uniformly spread over the disc of `radius` around `centre`, from the seeded stream.
pub(super) fn point_in_disc(centre: Vec2, radius: f32, stream: &mut u64) -> Vec2 {
    let angle = std::f32::consts::TAU * next_unit(stream);
    let reach = radius * next_unit(stream).sqrt();
    centre + Vec2::from_angle(angle) * reach
}

/// A splitmix64 step, mapped to `[0, 1)`: a fixed sequence per seed, so a run repeats.
fn next_unit(state: &mut u64) -> f32 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^= z >> 31;
    (z >> 40) as f32 / (1u64 << 24) as f32
}

/// The nearest point of any front's edge to `p`, and its distance.
pub(super) fn nearest(fronts: &[Vec<Vec2>], p: Vec2) -> Option<(f32, Vec2)> {
    let mut best: Option<(f32, Vec2)> = None;
    for front in fronts {
        for (a, b) in edges(front) {
            let q = closest_on_segment(p, a, b);
            let d = p.distance(q);
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, q));
            }
        }
    }
    best
}

fn edges(polygon: &[Vec2]) -> impl Iterator<Item = (Vec2, Vec2)> + '_ {
    polygon
        .iter()
        .zip(polygon.iter().cycle().skip(1))
        .map(|(a, b)| (*a, *b))
}

fn closest_on_segment(p: Vec2, a: Vec2, b: Vec2) -> Vec2 {
    let ab = b - a;
    let length_sq = ab.length_squared();
    if length_sq <= f32::EPSILON {
        return a;
    }
    a + ab * ((p - a).dot(ab) / length_sq).clamp(0.0, 1.0)
}

/// Even-odd containment in a polygon.
pub(super) fn contains(polygon: &[Vec2], p: Vec2) -> bool {
    let mut inside = false;
    for (a, b) in edges(polygon) {
        if (a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x {
            inside = !inside;
        }
    }
    inside
}
