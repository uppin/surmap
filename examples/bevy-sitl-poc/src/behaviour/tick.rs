//! The deterministic tick: each node kind's semantics over a `World`, and the runner that holds a
//! tree's state between ticks.

use bevy::math::Vec2;

use super::geometry::{contains, nearest, point_in_disc};
use super::{Kind, Node, Status, SucceedOn, Tree, World};
use crate::wind::WindModel;

/// A body within this distance of its goal has arrived (`move_to`).
const ARRIVED_M: f32 = 0.25;
/// Vertices a fire's front is sampled at for the distance tests.
const FRONT_POINTS: usize = 48;
/// Slack on a timer's end, so a whole number of ticks ends a leaf despite float rounding.
const TIMER_SLACK_S: f32 = 1e-3;

pub struct Runner {
    pub tree: Tree,
    /// ENU metres on the ground plane.
    pub position: Vec2,
    pub wind: WindModel,
    memory: Memory,
    finished: Option<Status>,
    action: Option<&'static str>,
    goal: Option<super::Goal>,
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
    goal: &'a mut Option<super::Goal>,
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
            || self
                .world
                .burning_areas
                .iter()
                .any(|area| contains(area, p))
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
            goal: None,
        }
    }

    /// Advance one tick of `dt` seconds; a root that finished keeps returning its status.
    pub fn tick(&mut self, world: &World, dt: f32) -> Status {
        if let Some(status) = self.finished {
            return status;
        }
        self.action = None;
        self.goal = None;
        let mut env = Env {
            world,
            dt,
            position: &mut self.position,
            wind: &mut self.wind,
            action: &mut self.action,
            goal: &mut self.goal,
            fronts: fronts(world),
        };
        let status = tick_node(&self.tree.root, &mut self.memory, &mut env);
        if status != Status::Running {
            self.finished = Some(status);
            self.action = None;
            self.goal = None;
        }
        status
    }

    /// The running leaf's kind (`"flee_from_fire"`, …), for the recorder; `None` when finished.
    pub fn action(&self) -> Option<&str> {
        self.action
    }

    /// The running leaf's goal at the last tick; `None` when it is not heading anywhere (`idle`,
    /// a condition, a finished tree).
    pub fn goal(&self) -> Option<super::Goal> {
        self.goal
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
        Kind::NearObject { object, within_m } => {
            let p = *env.position;
            let near = env
                .world
                .objects
                .iter()
                .find(|(other, _)| other == object)
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
                walk_towards(env, goal, *speed_m_s, true);
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
                let stop = memory.index + 1 == enu.len();
                walk_towards(env, Vec2::from_array(enu[memory.index]), *speed_m_s, stop);
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
    walk_towards(env, goal, speed_m_s, false);
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

/// Walks toward `goal` at `speed_m_s`, and records it as the running leaf's goal: `stop` when
/// the body must end on it (a path's end, a `move_to`), not merely drive through it.
fn walk_towards(env: &mut Env, goal: Vec2, speed_m_s: f32, stop: bool) {
    *env.goal = Some(super::Goal {
        point: goal,
        speed_m_s,
        stop,
    });
    let to_goal = goal - *env.position;
    let stride = (speed_m_s * env.dt).min(to_goal.length());
    *env.position += to_goal.normalize_or_zero() * stride;
}
