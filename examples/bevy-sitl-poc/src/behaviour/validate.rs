//! Validation of a tree for what it drives: unique node ids, numbers in range, and only the
//! leaves its target may use.

use std::collections::BTreeSet;

use super::{Kind, Node, Target, Tree};

impl Tree {
    /// Node ids unique, numbers in range (speeds, times, radii > 0; `parallel` and composites
    /// non-empty), and only the leaves the target may use: no `set_wind` on an object, only
    /// composites, decorators, `time_after`, `idle` and `set_wind` on the wind.
    pub fn validate(&self, target: Target) -> Result<(), String> {
        check(&self.root, target, &mut BTreeSet::new())
    }
}

fn check(node: &Node, target: Target, ids: &mut BTreeSet<String>) -> Result<(), String> {
    if let Some(id) = &node.id {
        if !ids.insert(id.clone()) {
            return Err(format!("duplicate node id {id:?}"));
        }
    }
    let name = node.kind.name();
    match (target, &node.kind) {
        (Target::Object, Kind::SetWind { .. }) => {
            return Err(format!(
                "{name}: set_wind drives the wind, so only the wind's own tree may use it"
            ))
        }
        (Target::Wind, kind) if !kind.is_wind_node() => {
            return Err(format!(
                "{name}: the wind's tree may only use composites, decorators, time_after, idle and set_wind"
            ))
        }
        _ => {}
    }
    node.kind.check_ranges()?;
    for child in node.kind.children() {
        check(child, target, ids)?;
    }
    Ok(())
}

impl Kind {
    pub(super) fn name(&self) -> &'static str {
        match self {
            Kind::Sequence { .. } => "sequence",
            Kind::Selector { .. } => "selector",
            Kind::Parallel { .. } => "parallel",
            Kind::Repeat { .. } => "repeat",
            Kind::Invert { .. } => "invert",
            Kind::TimeAfter { .. } => "time_after",
            Kind::NearFire { .. } => "near_fire",
            Kind::NearObject { .. } => "near_object",
            Kind::WindAbove { .. } => "wind_above",
            Kind::Idle { .. } => "idle",
            Kind::MoveTo { .. } => "move_to",
            Kind::FollowPath { .. } => "follow_path",
            Kind::Wander { .. } => "wander",
            Kind::FleeFromFire { .. } => "flee_from_fire",
            Kind::SetWind { .. } => "set_wind",
        }
    }

    pub(super) fn children(&self) -> Vec<&Node> {
        match self {
            Kind::Sequence { children }
            | Kind::Selector { children }
            | Kind::Parallel { children, .. } => children.iter().collect(),
            Kind::Repeat { child, .. } | Kind::Invert { child } => vec![child.as_ref()],
            _ => Vec::new(),
        }
    }

    /// The kinds the wind's own tree may use: composites, decorators, `time_after`, `idle`, `set_wind`.
    fn is_wind_node(&self) -> bool {
        matches!(
            self,
            Kind::Sequence { .. }
                | Kind::Selector { .. }
                | Kind::Parallel { .. }
                | Kind::Repeat { .. }
                | Kind::Invert { .. }
                | Kind::TimeAfter { .. }
                | Kind::Idle { .. }
                | Kind::SetWind { .. }
        )
    }

    fn check_ranges(&self) -> Result<(), String> {
        let name = self.name();
        let require = |holds: bool, field: &str, rule: &str| -> Result<(), String> {
            if holds {
                Ok(())
            } else {
                Err(format!("{name}: {field} must be {rule}"))
            }
        };
        match self {
            Kind::Sequence { children }
            | Kind::Selector { children }
            | Kind::Parallel { children, .. } => {
                require(!children.is_empty(), "children", "a non-empty list")?
            }
            Kind::Repeat { times, .. } => require(times.is_none_or(|n| n >= 1), "times", ">= 1")?,
            Kind::Invert { .. } => {}
            Kind::TimeAfter { s } => require(non_negative(*s), "s", ">= 0")?,
            Kind::NearFire { within_m } | Kind::NearObject { within_m, .. } => {
                require(positive(*within_m), "within_m", "> 0")?
            }
            Kind::WindAbove { speed_m_s } => {
                require(non_negative(*speed_m_s), "speed_m_s", ">= 0")?
            }
            Kind::Idle { s } => require(positive(*s), "s", "> 0")?,
            Kind::MoveTo { enu, speed_m_s } => {
                require(finite(std::slice::from_ref(enu)), "enu", "finite")?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::FollowPath { enu, speed_m_s } => {
                require(
                    !enu.is_empty() && finite(enu),
                    "enu",
                    "a non-empty list of finite points",
                )?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::Wander {
                radius_m,
                speed_m_s,
                ..
            } => {
                require(positive(*radius_m), "radius_m", "> 0")?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::FleeFromFire {
                speed_m_s,
                clearance_m,
            } => {
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
                require(non_negative(*clearance_m), "clearance_m", ">= 0")?;
            }
            Kind::SetWind {
                from_deg,
                speed_m_s,
                gust_m_s,
                over_s,
            } => {
                require(from_deg.is_finite(), "from_deg", "finite")?;
                require(non_negative(*speed_m_s), "speed_m_s", ">= 0")?;
                require(non_negative(*gust_m_s), "gust_m_s", ">= 0")?;
                require(positive(*over_s), "over_s", "> 0")?;
            }
        }
        Ok(())
    }
}

fn positive(value: f32) -> bool {
    value.is_finite() && value > 0.0
}

fn non_negative(value: f32) -> bool {
    value.is_finite() && value >= 0.0
}

fn finite(points: &[[f32; 2]]) -> bool {
    points.iter().all(|p| p.iter().all(|v| v.is_finite()))
}
