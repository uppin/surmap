//! Behaviour trees for scenario objects and the wind (changeset § *Behaviour-tree JSON*): parsed
//! from the manifest's inline JSON, ticked at a fixed rate in simulation time. Pure, so a run is
//! deterministic and the recorder's tracks come from the same place the renderer moves bodies.

#![allow(dead_code)]

use std::collections::BTreeSet;

use bevy::math::Vec2;
use serde::de::Error as _;
use serde::{Deserialize, Deserializer};
use serde_json::Value;

use crate::fire::FireSpec;
use crate::wind::WindModel;

/// Ticks per simulated second.
pub const TICK_HZ: f32 = 10.0;
/// A body within this distance of its goal has arrived (changeset § *Behaviour-tree JSON*).
const ARRIVED_M: f32 = 0.25;
/// Vertices a fire's front is sampled at for the distance tests.
const FRONT_POINTS: usize = 48;
/// Slack on a timer's end, so a whole number of ticks ends a leaf despite float rounding.
const TIMER_SLACK_S: f32 = 1e-3;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SucceedOn {
    All,
    One,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(tag = "node", rename_all = "snake_case", deny_unknown_fields)]
pub enum Kind {
    Sequence {
        children: Vec<Node>,
    },
    Selector {
        children: Vec<Node>,
    },
    Parallel {
        children: Vec<Node>,
        succeed_on: SucceedOn,
    },
    Repeat {
        child: Box<Node>,
        times: Option<u32>,
    },
    Invert {
        child: Box<Node>,
    },
    TimeAfter {
        s: f32,
    },
    NearFire {
        within_m: f32,
    },
    NearObject {
        id: String,
        within_m: f32,
    },
    WindAbove {
        speed_m_s: f32,
    },
    Idle {
        s: f32,
    },
    MoveTo {
        enu: [f32; 2],
        speed_m_s: f32,
    },
    FollowPath {
        enu: Vec<[f32; 2]>,
        speed_m_s: f32,
    },
    Wander {
        radius_m: f32,
        speed_m_s: f32,
        seed: u64,
    },
    FleeFromFire {
        speed_m_s: f32,
        clearance_m: f32,
    },
    SetWind {
        from_deg: f32,
        speed_m_s: f32,
        gust_m_s: f32,
        over_s: f32,
    },
}

/// One node of a tree: its address (`id`, unique within its tree) and what it does.
#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: Option<String>,
    pub kind: Kind,
}

impl<'de> Deserialize<'de> for Node {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let mut value = Value::deserialize(deserializer)?;
        // A `near_object` names the other body with its `id`; every other node's `id` addresses it.
        let names_body = value.get("node").and_then(Value::as_str) == Some("near_object");
        let id = match value
            .as_object_mut()
            .filter(|_| !names_body)
            .and_then(|fields| fields.remove("id"))
        {
            None | Some(Value::Null) => None,
            Some(Value::String(id)) => Some(id),
            Some(other) => {
                return Err(D::Error::custom(format!(
                    "a node's id must be a string, not {other}"
                )))
            }
        };
        let kind = serde_json::from_value(value).map_err(D::Error::custom)?;
        Ok(Self { id, kind })
    }
}

/// What a tree drives: a body on the ground, or the scenario's wind.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Target {
    Object,
    Wind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Running,
    Success,
    Failure,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Tree {
    pub root: Node,
}

/// Everything a tick may read: simulation time, the fires, the current wind, other bodies.
pub struct World<'a> {
    pub t_s: f32,
    pub fires: &'a [FireSpec],
    /// Other burning ground (ENU polygons, e.g. burning buildings' footprints): `near_fire` and
    /// `flee_from_fire` treat them like a wildfire's perimeter.
    pub burning_areas: &'a [Vec<Vec2>],
    pub wind: &'a WindModel,
    pub objects: &'a [(String, Vec2)],
}

pub struct Runner {
    pub tree: Tree,
    /// ENU metres on the ground plane.
    pub position: Vec2,
    pub wind: WindModel,
    memory: Memory,
    finished: Option<Status>,
    action: Option<&'static str>,
}

impl Tree {
    /// Parse one tree; an unknown node kind or field is an error naming it.
    pub fn from_json(text: &str) -> Result<Self, String> {
        let root: Node = serde_json::from_str(text).map_err(|e| e.to_string())?;
        Ok(Self { root })
    }

    /// Node ids unique, numbers in range (speeds, times, radii > 0; `parallel` and composites
    /// non-empty), and only the leaves the target may use: no `set_wind` on an object, only
    /// composites, decorators, `time_after`, `idle` and `set_wind` on the wind.
    pub fn validate(&self, target: Target) -> Result<(), String> {
        validate_node(&self.root, target)
    }
}

/// Validates `root` and its subtree for `target` (see `Tree::validate`).
pub fn validate_node(root: &Node, target: Target) -> Result<(), String> {
    check(root, target, &mut BTreeSet::new())
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
    fn name(&self) -> &'static str {
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

    fn children(&self) -> Vec<&Node> {
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
            Kind::Sequence { children } | Kind::Selector { children } | Kind::Parallel { children, .. } => {
                require(!children.is_empty(), "children", "a non-empty list")?
            }
            Kind::Repeat { times, .. } => require(times.is_none_or(|n| n >= 1), "times", ">= 1")?,
            Kind::Invert { .. } => {}
            Kind::TimeAfter { s } => require(non_negative(*s), "s", ">= 0")?,
            Kind::NearFire { within_m } | Kind::NearObject { within_m, .. } => {
                require(positive(*within_m), "within_m", "> 0")?
            }
            Kind::WindAbove { speed_m_s } => require(non_negative(*speed_m_s), "speed_m_s", ">= 0")?,
            Kind::Idle { s } => require(positive(*s), "s", "> 0")?,
            Kind::MoveTo { enu, speed_m_s } => {
                require(finite(std::slice::from_ref(enu)), "enu", "finite")?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::FollowPath { enu, speed_m_s } => {
                require(!enu.is_empty() && finite(enu), "enu", "a non-empty list of finite points")?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::Wander { radius_m, speed_m_s, .. } => {
                require(positive(*radius_m), "radius_m", "> 0")?;
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
            }
            Kind::FleeFromFire { speed_m_s, clearance_m } => {
                require(positive(*speed_m_s), "speed_m_s", "> 0")?;
                require(non_negative(*clearance_m), "clearance_m", ">= 0")?;
            }
            Kind::SetWind { from_deg, speed_m_s, gust_m_s, over_s } => {
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

/// What one node remembers between ticks: a composite's cursor, a leaf's timer and goal, and
/// the memory of each child.
#[derive(Debug, Clone, Default, PartialEq)]
struct Memory {
    /// Sequence and follow_path cursor; repeat's completed laps.
    index: usize,
    /// Seconds a leaf has run (idle, set_wind).
    elapsed_s: f32,
    /// Where a wander began (its disc's centre), and the point it is heading for.
    anchor: Option<Vec2>,
    goal: Option<Vec2>,
    /// A wander's random stream.
    stream: u64,
    /// The wind when a set_wind began.
    wind_at_start: Option<WindModel>,
    /// Parallel: each child's verdict once it has finished.
    verdicts: Vec<Option<Status>>,
    /// One memory per child.
    children: Vec<Memory>,
}

/// One tick's view: the world, the runner's own state, and the fronts it can flee.
struct Env<'a, 'w> {
    world: &'a World<'w>,
    dt: f32,
    position: &'a mut Vec2,
    wind: &'a mut WindModel,
    action: &'a mut Option<&'static str>,
    /// Wildfire fronts and other burning ground, as polygons, at `world.t_s`.
    fronts: Vec<Vec<Vec2>>,
}

impl Env<'_, '_> {
    /// Whether `p` is inside burning ground at this tick.
    fn burning(&self, p: Vec2) -> bool {
        let wind = self.world.wind.velocity_enu(self.world.t_s);
        self.world
            .fires
            .iter()
            .any(|fire| fire.burnt(p, self.world.t_s, wind))
            || self.world.burning_areas.iter().any(|area| contains(area, p))
    }

    /// Within `within` metres of a front or inside burning ground.
    fn near_fire(&self, p: Vec2, within: f32) -> bool {
        self.burning(p) || nearest(&self.fronts, p).is_some_and(|(d, _)| d <= within)
    }
}

impl Runner {
    pub fn new(tree: Tree, position: Vec2, wind: WindModel) -> Self {
        Self {
            tree,
            position,
            wind,
            memory: Memory::default(),
            finished: None,
            action: None,
        }
    }

    /// Advance one tick of `dt` seconds; a root that finished keeps returning its status.
    pub fn tick(&mut self, world: &World, dt: f32) -> Status {
        if let Some(status) = self.finished {
            return status;
        }
        self.action = None;
        let mut env = Env {
            world,
            dt,
            position: &mut self.position,
            wind: &mut self.wind,
            action: &mut self.action,
            fronts: fronts(world),
        };
        let status = tick_node(&self.tree.root, &mut self.memory, &mut env);
        if status != Status::Running {
            self.finished = Some(status);
            self.action = None;
        }
        status
    }

    /// The running leaf's kind (`"flee_from_fire"`, …), for the recorder; `None` when finished.
    pub fn action(&self) -> Option<&str> {
        self.action
    }
}

/// The wildfire fronts at `world.t_s` and the other burning ground, as polygons.
fn fronts(world: &World) -> Vec<Vec<Vec2>> {
    let wind = world.wind.velocity_enu(world.t_s);
    world
        .fires
        .iter()
        .map(|fire| fire.perimeter(world.t_s, wind, FRONT_POINTS))
        .chain(world.burning_areas.iter().cloned())
        .filter(|front| !front.is_empty())
        .collect()
}

fn tick_node(node: &Node, memory: &mut Memory, env: &mut Env) -> Status {
    ensure_children(memory, node.kind.children().len());
    match &node.kind {
        Kind::Sequence { children } => sequence(children, memory, env),
        Kind::Selector { children } => selector(children, memory, env),
        Kind::Parallel {
            children,
            succeed_on,
        } => parallel(children, *succeed_on, memory, env),
        Kind::Repeat { child, times } => repeat(child, *times, memory, env),
        Kind::Invert { child } => invert(child, memory, env),
        Kind::TimeAfter { s } => decide(env.world.t_s >= *s),
        Kind::NearFire { within_m } => {
            let p = *env.position;
            decide(env.near_fire(p, *within_m))
        }
        Kind::NearObject { id, within_m } => {
            let p = *env.position;
            let near = env
                .world
                .objects
                .iter()
                .find(|(other, _)| other == id)
                .is_some_and(|(_, at)| p.distance(*at) <= *within_m);
            decide(near)
        }
        Kind::WindAbove { speed_m_s } => {
            let speed = env.world.wind.velocity_enu(env.world.t_s).length();
            decide(speed > *speed_m_s)
        }
        Kind::Idle { s } => {
            memory.elapsed_s += env.dt;
            if memory.elapsed_s + TIMER_SLACK_S >= *s {
                *memory = Memory::default();
                Status::Success
            } else {
                running(env, "idle")
            }
        }
        Kind::MoveTo { enu, speed_m_s } => {
            let goal = Vec2::from_array(*enu);
            if arrived(env, goal) {
                *memory = Memory::default();
                Status::Success
            } else {
                walk_towards(env, goal, *speed_m_s);
                running(env, "move_to")
            }
        }
        Kind::FollowPath { enu, speed_m_s } => {
            while memory.index < enu.len() && arrived(env, Vec2::from_array(enu[memory.index])) {
                memory.index += 1;
            }
            if memory.index == enu.len() {
                *memory = Memory::default();
                Status::Success
            } else {
                walk_towards(env, Vec2::from_array(enu[memory.index]), *speed_m_s);
                running(env, "follow_path")
            }
        }
        Kind::Wander {
            radius_m,
            speed_m_s,
            seed,
        } => wander(*radius_m, *speed_m_s, *seed, memory, env),
        Kind::FleeFromFire {
            speed_m_s,
            clearance_m,
        } => flee_from_fire(*speed_m_s, *clearance_m, memory, env),
        Kind::SetWind {
            from_deg,
            speed_m_s,
            gust_m_s,
            over_s,
        } => {
            let target = WindModel {
                from_deg: *from_deg,
                speed_m_s: *speed_m_s,
                gust_m_s: *gust_m_s,
            };
            set_wind(target, *over_s, memory, env)
        }
    }
}

/// The first child that does not fail decides; children after it start afresh next time, so a
/// higher choice that becomes possible again takes over from a lower one.
fn selector(children: &[Node], memory: &mut Memory, env: &mut Env) -> Status {
    for index in 0..children.len() {
        match tick_child(children, index, memory, env) {
            Status::Failure => {}
            decided => {
                for later in &mut memory.children[index + 1..] {
                    *later = Memory::default();
                }
                return decided;
            }
        }
    }
    *memory = Memory::default();
    Status::Failure
}

/// Children in order; a child that is still running holds the sequence on it until it ends.
fn sequence(children: &[Node], memory: &mut Memory, env: &mut Env) -> Status {
    for index in memory.index..children.len() {
        match tick_child(children, index, memory, env) {
            Status::Success => {}
            Status::Running => {
                memory.index = index;
                return Status::Running;
            }
            Status::Failure => {
                *memory = Memory::default();
                return Status::Failure;
            }
        }
    }
    *memory = Memory::default();
    Status::Success
}

/// Every unfinished child is ticked each tick; the policy decides when the whole is done.
fn parallel(
    children: &[Node],
    succeed_on: SucceedOn,
    memory: &mut Memory,
    env: &mut Env,
) -> Status {
    if memory.verdicts.len() != children.len() {
        memory.verdicts = vec![None; children.len()];
    }
    for index in 0..children.len() {
        if memory.verdicts[index].is_none() {
            let verdict = tick_child(children, index, memory, env);
            if verdict != Status::Running {
                memory.verdicts[index] = Some(verdict);
            }
        }
    }
    let wins = memory
        .verdicts
        .iter()
        .filter(|v| **v == Some(Status::Success))
        .count();
    let losses = memory
        .verdicts
        .iter()
        .filter(|v| **v == Some(Status::Failure))
        .count();
    let decided = match succeed_on {
        SucceedOn::All if losses > 0 => Some(Status::Failure),
        SucceedOn::All if wins == children.len() => Some(Status::Success),
        SucceedOn::One if wins > 0 => Some(Status::Success),
        SucceedOn::One if losses == children.len() => Some(Status::Failure),
        _ => None,
    };
    match decided {
        Some(status) => {
            *memory = Memory::default();
            status
        }
        None => Status::Running,
    }
}

fn repeat(child: &Node, times: Option<u32>, memory: &mut Memory, env: &mut Env) -> Status {
    match tick_node(child, &mut memory.children[0], env) {
        Status::Running => Status::Running,
        Status::Failure => {
            *memory = Memory::default();
            Status::Failure
        }
        Status::Success => {
            memory.index += 1;
            if times.is_some_and(|n| memory.index >= n as usize) {
                *memory = Memory::default();
                Status::Success
            } else {
                Status::Running
            }
        }
    }
}

fn invert(child: &Node, memory: &mut Memory, env: &mut Env) -> Status {
    match tick_node(child, &mut memory.children[0], env) {
        Status::Success => Status::Failure,
        Status::Failure => Status::Success,
        Status::Running => Status::Running,
    }
}

fn wander(radius_m: f32, speed_m_s: f32, seed: u64, memory: &mut Memory, env: &mut Env) -> Status {
    let anchor = match memory.anchor {
        Some(anchor) => anchor,
        None => {
            memory.anchor = Some(*env.position);
            memory.stream = seed;
            *env.position
        }
    };
    let goal = match memory.goal {
        Some(goal) if !arrived(env, goal) => goal,
        _ => {
            let goal = point_in_disc(anchor, radius_m, &mut memory.stream);
            memory.goal = Some(goal);
            goal
        }
    };
    walk_towards(env, goal, speed_m_s);
    running(env, "wander")
}

/// Flees from the nearest front, outward from burning ground, until `clearance_m` clear of it.
fn flee_from_fire(speed_m_s: f32, clearance_m: f32, memory: &mut Memory, env: &mut Env) -> Status {
    let p = *env.position;
    let Some((distance, edge)) = nearest(&env.fronts, p) else {
        *memory = Memory::default();
        return Status::Success;
    };
    let inside = env.burning(p);
    if !inside && distance >= clearance_m {
        *memory = Memory::default();
        return Status::Success;
    }
    let away = if inside { edge - p } else { p - edge };
    *env.position += away.normalize_or(Vec2::X) * (speed_m_s * env.dt);
    running(env, "flee_from_fire")
}

/// Ramps the wind linearly to `target` over `over_s`, the short way round the compass.
fn set_wind(target: WindModel, over_s: f32, memory: &mut Memory, env: &mut Env) -> Status {
    let start = *memory.wind_at_start.get_or_insert(*env.wind);
    let progress = memory.elapsed_s / over_s;
    memory.elapsed_s += env.dt;
    if progress >= 1.0 {
        *env.wind = target;
        *memory = Memory::default();
        return Status::Success;
    }
    let turn = shortest_turn(start.from_deg, target.from_deg);
    *env.wind = WindModel {
        from_deg: start.from_deg + turn * progress,
        speed_m_s: start.speed_m_s + (target.speed_m_s - start.speed_m_s) * progress,
        gust_m_s: start.gust_m_s + (target.gust_m_s - start.gust_m_s) * progress,
    };
    running(env, "set_wind")
}

fn shortest_turn(from_deg: f32, to_deg: f32) -> f32 {
    (to_deg - from_deg + 540.0).rem_euclid(360.0) - 180.0
}

fn tick_child(children: &[Node], index: usize, memory: &mut Memory, env: &mut Env) -> Status {
    tick_node(&children[index], &mut memory.children[index], env)
}

fn ensure_children(memory: &mut Memory, count: usize) {
    if memory.children.len() < count {
        memory.children.resize_with(count, Memory::default);
    }
}

fn decide(holds: bool) -> Status {
    if holds {
        Status::Success
    } else {
        Status::Failure
    }
}

fn running(env: &mut Env, action: &'static str) -> Status {
    *env.action = Some(action);
    Status::Running
}

fn arrived(env: &Env, goal: Vec2) -> bool {
    (*env.position).distance(goal) <= ARRIVED_M
}

fn walk_towards(env: &mut Env, goal: Vec2, speed_m_s: f32) {
    let to_goal = goal - *env.position;
    let stride = (speed_m_s * env.dt).min(to_goal.length());
    *env.position += to_goal.normalize_or_zero() * stride;
}

/// A point uniformly spread over the disc of `radius` around `centre`, from the seeded stream.
fn point_in_disc(centre: Vec2, radius: f32, stream: &mut u64) -> Vec2 {
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
fn nearest(fronts: &[Vec<Vec2>], p: Vec2) -> Option<(f32, Vec2)> {
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
fn contains(polygon: &[Vec2], p: Vec2) -> bool {
    let mut inside = false;
    for (a, b) in edges(polygon) {
        if (a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x {
            inside = !inside;
        }
    }
    inside
}

#[cfg(test)]
mod tests {
    use super::*;

    const DT: f32 = 1.0 / TICK_HZ;

    fn calm() -> WindModel {
        WindModel {
            from_deg: 270.0,
            speed_m_s: 0.0,
            gust_m_s: 0.0,
        }
    }

    fn tree(json: &str) -> Tree {
        Tree::from_json(json).unwrap_or_else(|e| panic!("{e}"))
    }

    /// Ticks `runner` from `t0` for `seconds`, with `fires` and the runner's own wind as the world.
    fn run(runner: &mut Runner, fires: &[FireSpec], t0: f32, seconds: f32) -> Status {
        let mut status = Status::Running;
        for i in 0..(seconds * TICK_HZ).round() as usize {
            let wind = runner.wind;
            let world = World {
                t_s: t0 + i as f32 * DT,
                fires,
                burning_areas: &[],
                wind: &wind,
                objects: &[],
            };
            status = runner.tick(&world, DT);
        }
        status
    }

    fn a_fire_west_of_the_origin() -> FireSpec {
        FireSpec {
            ignition: Vec2::new(-10.0, 0.0),
            start_s: 0.0,
            spread_m_s: 0.3,
            max_radius_m: 40.0,
            head_wind_gain: 0.5,
            lb_wind_gain: 0.25,
        }
    }

    #[test]
    fn a_body_walks_to_its_goal_at_its_speed_then_succeeds() {
        let mut runner = Runner::new(
            tree(r#"{"node": "move_to", "enu": [10, 0], "speed_m_s": 2}"#),
            Vec2::ZERO,
            calm(),
        );

        let halfway = run(&mut runner, &[], 0.0, 2.5);
        let at_two_and_a_half = runner.position;
        let done = run(&mut runner, &[], 2.5, 3.0);

        assert_eq!(halfway, Status::Running);
        assert!(
            (at_two_and_a_half.x - 5.0).abs() < 0.11,
            "{at_two_and_a_half:?}"
        );
        assert_eq!(done, Status::Success);
        assert!(runner.position.distance(Vec2::new(10.0, 0.0)) <= 0.25);
    }

    #[test]
    fn a_sequence_walks_its_path_then_idles() {
        let mut runner = Runner::new(
            tree(
                r#"{"node": "sequence", "children": [
                    {"node": "follow_path", "enu": [[4, 0], [4, 3]], "speed_m_s": 1},
                    {"node": "idle", "s": 2}]}"#,
            ),
            Vec2::ZERO,
            calm(),
        );

        run(&mut runner, &[], 0.0, 7.5);
        let idling = runner.action().map(str::to_owned);
        let done = run(&mut runner, &[], 7.5, 2.0);

        assert!(runner.position.distance(Vec2::new(4.0, 3.0)) <= 0.25);
        assert_eq!(idling.as_deref(), Some("idle"));
        assert_eq!(done, Status::Success);
    }

    #[test]
    fn time_after_fails_before_its_time_and_succeeds_after() {
        let gate = tree(r#"{"node": "time_after", "s": 30}"#);
        let wind = calm();
        let before = World {
            t_s: 29.0,
            fires: &[],
            burning_areas: &[],
            wind: &wind,
            objects: &[],
        };
        let after = World {
            t_s: 31.0,
            fires: &[],
            burning_areas: &[],
            wind: &wind,
            objects: &[],
        };

        assert_eq!(
            Runner::new(gate.clone(), Vec2::ZERO, wind).tick(&before, DT),
            Status::Failure
        );
        assert_eq!(
            Runner::new(gate, Vec2::ZERO, wind).tick(&after, DT),
            Status::Success
        );
    }

    #[test]
    fn a_selector_flees_a_near_fire_and_otherwise_wanders() {
        let evacuee = r#"{"node": "selector", "children": [
            {"node": "sequence", "children": [
                {"node": "near_fire", "within_m": 20},
                {"id": "flee", "node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 30}]},
            {"node": "wander", "radius_m": 6, "speed_m_s": 0.8, "seed": 7}]}"#;
        let fire = [a_fire_west_of_the_origin()];
        let mut far = Runner::new(tree(evacuee), Vec2::new(200.0, 0.0), calm());
        let mut near = Runner::new(tree(evacuee), Vec2::ZERO, calm());

        run(&mut far, &fire, 0.0, 3.0);
        run(&mut near, &fire, 0.0, 3.0);

        assert_eq!(far.action(), Some("wander"));
        assert_eq!(near.action(), Some("flee_from_fire"));
        assert!(
            near.position.x > 0.0,
            "flees east, away from the fire: {:?}",
            near.position
        );
    }

    #[test]
    fn a_fleeing_person_never_stands_in_the_burnt_area() {
        let mut runner = Runner::new(
            tree(r#"{"node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 30}"#),
            Vec2::new(-4.0, 1.0),
            WindModel {
                from_deg: 270.0,
                speed_m_s: 6.0,
                gust_m_s: 0.0,
            },
        );
        let fire = a_fire_west_of_the_origin();

        for i in 0..(120.0 * TICK_HZ) as usize {
            let t_s = i as f32 * DT;
            let wind = runner.wind;
            runner.tick(
                &World {
                    t_s,
                    fires: std::slice::from_ref(&fire),
                    burning_areas: &[],
                    wind: &wind,
                    objects: &[],
                },
                DT,
            );
            assert!(
                !fire.burnt(runner.position, t_s, wind.velocity_enu(t_s)),
                "burnt at t={t_s}: {:?}",
                runner.position
            );
        }
    }

    #[test]
    fn repeat_runs_its_child_the_given_number_of_times() {
        let mut runner = Runner::new(
            tree(
                r#"{"node": "repeat", "times": 2, "child":
                    {"node": "follow_path", "enu": [[2, 0], [0, 0]], "speed_m_s": 1}}"#,
            ),
            Vec2::ZERO,
            calm(),
        );

        let after_one_lap = run(&mut runner, &[], 0.0, 4.5);
        let after_two = run(&mut runner, &[], 4.5, 4.5);

        assert_eq!(after_one_lap, Status::Running);
        assert_eq!(after_two, Status::Success);
    }

    #[test]
    fn invert_swaps_success_and_failure() {
        let wind = calm();
        let early = World {
            t_s: 0.0,
            fires: &[],
            burning_areas: &[],
            wind: &wind,
            objects: &[],
        };

        let status = Runner::new(
            tree(r#"{"node": "invert", "child": {"node": "time_after", "s": 5}}"#),
            Vec2::ZERO,
            wind,
        )
        .tick(&early, DT);

        assert_eq!(status, Status::Success);
    }

    #[test]
    fn near_object_reads_the_other_bodies() {
        let wind = calm();
        let others = [("car-1".to_owned(), Vec2::new(3.0, 4.0))];
        let world = World {
            t_s: 0.0,
            fires: &[],
            burning_areas: &[],
            wind: &wind,
            objects: &others,
        };

        let near = Runner::new(
            tree(r#"{"node": "near_object", "id": "car-1", "within_m": 6}"#),
            Vec2::ZERO,
            wind,
        )
        .tick(&world, DT);
        let far = Runner::new(
            tree(r#"{"node": "near_object", "id": "car-1", "within_m": 4}"#),
            Vec2::ZERO,
            wind,
        )
        .tick(&world, DT);

        assert_eq!((near, far), (Status::Success, Status::Failure));
    }

    #[test]
    fn a_burning_building_is_a_fire_to_flee_from() {
        let wind = calm();
        let block = [vec![
            Vec2::new(-12.0, -5.0),
            Vec2::new(-2.0, -5.0),
            Vec2::new(-2.0, 5.0),
            Vec2::new(-12.0, 5.0),
        ]];
        let mut runner = Runner::new(
            tree(
                r#"{"node": "sequence", "children": [
                {"node": "near_fire", "within_m": 5},
                {"node": "flee_from_fire", "speed_m_s": 3, "clearance_m": 20}]}"#,
            ),
            Vec2::ZERO,
            wind,
        );

        for i in 0..100 {
            runner.tick(
                &World {
                    t_s: i as f32 * DT,
                    fires: &[],
                    burning_areas: &block,
                    wind: &wind,
                    objects: &[],
                },
                DT,
            );
        }

        assert!(
            runner.position.x >= 18.0 - 0.1,
            "18 m east of the block's east wall: {:?}",
            runner.position
        );
    }

    #[test]
    fn wandering_is_deterministic_for_a_seed_and_stays_in_its_radius() {
        let wanderer = r#"{"node": "wander", "radius_m": 6, "speed_m_s": 0.8, "seed": 3}"#;
        let mut a = Runner::new(tree(wanderer), Vec2::new(5.0, 5.0), calm());
        let mut b = Runner::new(tree(wanderer), Vec2::new(5.0, 5.0), calm());

        let mut farthest: f32 = 0.0;
        for i in 0..600 {
            let wind = calm();
            let world = World {
                t_s: i as f32 * DT,
                fires: &[],
                burning_areas: &[],
                wind: &wind,
                objects: &[],
            };
            a.tick(&world, DT);
            b.tick(&world, DT);
            farthest = farthest.max(a.position.distance(Vec2::new(5.0, 5.0)));
        }

        assert_eq!(a.position, b.position);
        assert!(farthest > 1.0 && farthest <= 6.0 + 1e-3, "{farthest}");
    }

    #[test]
    fn the_wind_tree_veers_and_strengthens_the_wind_over_its_ramp() {
        let mut wind = Runner::new(
            tree(
                r#"{"node": "sequence", "children": [
                    {"node": "idle", "s": 20},
                    {"node": "set_wind", "from_deg": 300, "speed_m_s": 10, "gust_m_s": 3, "over_s": 30}]}"#,
            ),
            Vec2::ZERO,
            WindModel {
                from_deg: 270.0,
                speed_m_s: 6.0,
                gust_m_s: 1.0,
            },
        );

        run(&mut wind, &[], 0.0, 20.0);
        let before_ramp = wind.wind;
        run(&mut wind, &[], 20.0, 15.0);
        let halfway = wind.wind;
        let done = run(&mut wind, &[], 35.0, 16.0);

        assert_eq!(
            before_ramp,
            WindModel {
                from_deg: 270.0,
                speed_m_s: 6.0,
                gust_m_s: 1.0
            }
        );
        assert!(
            (halfway.from_deg - 285.0).abs() < 0.5 && (halfway.speed_m_s - 8.0).abs() < 0.15,
            "{halfway:?}"
        );
        assert_eq!(done, Status::Success);
        assert_eq!(
            wind.wind,
            WindModel {
                from_deg: 300.0,
                speed_m_s: 10.0,
                gust_m_s: 3.0
            }
        );
    }

    #[test]
    fn the_wind_turns_the_short_way_round_the_compass() {
        let mut wind = Runner::new(
            tree(
                r#"{"node": "set_wind", "from_deg": 10, "speed_m_s": 5, "gust_m_s": 0, "over_s": 10}"#,
            ),
            Vec2::ZERO,
            WindModel {
                from_deg: 350.0,
                speed_m_s: 5.0,
                gust_m_s: 0.0,
            },
        );

        run(&mut wind, &[], 0.0, 5.0);

        let d = wind.wind.from_deg.rem_euclid(360.0);
        assert!(d < 1.0 || d > 359.0, "through north, not south: {d}");
    }

    #[test]
    fn an_unknown_node_kind_is_refused_by_name() {
        let err =
            Tree::from_json(r#"{"node": "teleport", "enu": [0, 0]}"#).expect_err("unknown kind");

        assert!(err.contains("teleport"), "{err}");
    }

    #[test]
    fn an_object_may_not_set_the_wind_and_the_wind_may_not_walk() {
        let gusty = tree(
            r#"{"node": "set_wind", "from_deg": 0, "speed_m_s": 5, "gust_m_s": 0, "over_s": 1}"#,
        );
        let walker = tree(r#"{"node": "move_to", "enu": [1, 1], "speed_m_s": 1}"#);

        assert!(gusty.validate(Target::Object).is_err());
        assert!(walker.validate(Target::Wind).is_err());
        assert!(gusty.validate(Target::Wind).is_ok() && walker.validate(Target::Object).is_ok());
    }

    #[test]
    fn duplicate_node_ids_and_empty_composites_are_refused() {
        let twins = tree(
            r#"{"node": "sequence", "children": [
                {"id": "a", "node": "idle", "s": 1}, {"id": "a", "node": "idle", "s": 2}]}"#,
        );
        let empty = tree(r#"{"node": "selector", "children": []}"#);
        let still = tree(r#"{"node": "move_to", "enu": [1, 1], "speed_m_s": 0}"#);

        assert!(twins.validate(Target::Object).unwrap_err().contains('a'));
        assert!(empty.validate(Target::Object).is_err());
        assert!(still.validate(Target::Object).is_err());
    }
}
