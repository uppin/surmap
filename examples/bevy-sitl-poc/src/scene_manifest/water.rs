//! Water surfaces (`box` elements with `water: true`) and the rules that keep a vessel on them
//! (docs/simulation/bevy-simulation.md § *Vehicles* → vessels). A vessel floats on the top of the
//! surface it starts on; every point it is driven to must lie on some surface.

use bevy::math::Vec2;

use super::{BoxElement, Element};
use crate::behaviour::{Kind, Node, Tree};

/// A water box's footprint (its centre and half-extents, ENU, yawed about its centre) and its top.
#[derive(Debug, Clone, PartialEq)]
pub struct Surface {
    centre: Vec2,
    half: Vec2,
    yaw_rad: f32,
    /// The water's top, m above the ground.
    pub top_z_m: f32,
}

impl Surface {
    fn of(element: &BoxElement) -> Self {
        let [east, north, up] = element.size_m;
        let [x, y, z] = element.position_enu;
        Self {
            centre: Vec2::new(x, y),
            half: Vec2::new(east, north) / 2.0,
            yaw_rad: element.yaw_deg.to_radians(),
            top_z_m: z + up,
        }
    }

    /// Whether the ENU point `p` lies on this surface.
    pub fn contains(&self, p: Vec2) -> bool {
        let offset = p - self.centre;
        let (sin, cos) = self.yaw_rad.sin_cos();
        let local = Vec2::new(offset.x * cos + offset.y * sin, -offset.x * sin + offset.y * cos);
        local.x.abs() <= self.half.x && local.y.abs() <= self.half.y
    }
}

/// Every `water: true` box in the scene, as surfaces.
pub fn surfaces(elements: &[Element]) -> Vec<Surface> {
    elements
        .iter()
        .filter_map(|element| match element {
            Element::Box(water) if water.water => Some(Surface::of(water)),
            _ => None,
        })
        .collect()
}

/// The surface a point lies on, the highest one when several overlap.
pub fn surface_at(surfaces: &[Surface], p: Vec2) -> Option<&Surface> {
    surfaces.iter().filter(|s| s.contains(p)).max_by(|a, b| a.top_z_m.total_cmp(&b.top_z_m))
}

/// Every point a tree steers a body to (`move_to`, `follow_path`), in its tree order.
pub fn steered_points(tree: &Tree) -> Vec<Vec2> {
    let mut points = Vec::new();
    collect(&tree.root, &mut points);
    points
}

fn collect(node: &Node, points: &mut Vec<Vec2>) {
    match &node.kind {
        Kind::MoveTo { enu, .. } => points.push(Vec2::from_array(*enu)),
        Kind::FollowPath { enu, .. } => points.extend(enu.iter().map(|p| Vec2::from_array(*p))),
        Kind::Sequence { children } | Kind::Selector { children } | Kind::Parallel { children, .. } => {
            children.iter().for_each(|child| collect(child, points));
        }
        Kind::Repeat { child, .. } | Kind::Invert { child } => collect(child, points),
        _ => {}
    }
}

/// The names of the nodes a vessel's tree may not use, found in it, in tree order: a vessel's
/// `wander` and `flee_from_fire` aim at points that are not known to be on water at load.
pub fn forbidden_nodes(tree: &Tree) -> Vec<&'static str> {
    let mut found = Vec::new();
    forbidden(&tree.root, &mut found);
    found
}

fn forbidden(node: &Node, found: &mut Vec<&'static str>) {
    match &node.kind {
        Kind::Wander { .. } => found.push("wander"),
        Kind::FleeFromFire { .. } => found.push("flee_from_fire"),
        Kind::Sequence { children } | Kind::Selector { children } | Kind::Parallel { children, .. } => {
            children.iter().for_each(|child| forbidden(child, found));
        }
        Kind::Repeat { child, .. } | Kind::Invert { child } => forbidden(child, found),
        _ => {}
    }
}
