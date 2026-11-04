//! The kinematic autopilot: where a fleet drone is at a simulation moment, replayed from its home
//! pad and the fleet log at a fixed step, so the answer never depends on the frame rate.
//!
//! No physics, wind, battery or obstacle avoidance: the route is flown as given, within the
//! limits below. It moves the simulation's own drones only; SurMap has no flight control.

use std::collections::VecDeque;

use bevy::math::{Vec2, Vec3};

use super::log::{FleetCommand, FleetLog, OnComplete, Route, Stamped, DEFAULT_SPEED_M_S};

/// The fixed integration step, from `t = 0`. A command takes effect at the first step at or after
/// its `at_s`.
pub const STEP_S: f32 = 0.05;
/// Route speed bounds (a route outside them is refused) and the horizontal speed limit.
pub const MAX_SPEED_M_S: f32 = 8.0;
pub const MIN_SPEED_M_S: f32 = 0.5;
/// Horizontal acceleration limit.
pub const MAX_ACCEL_M_S2: f32 = 2.5;
/// Vertical speed limit while climbing or cruising.
pub const MAX_CLIMB_M_S: f32 = 2.0;
/// Vertical speed limit while landing.
pub const MAX_DESCENT_M_S: f32 = 1.0;
/// Heading turn-rate limit.
pub const MAX_YAW_RATE_DEG_S: f32 = 60.0;
/// A target this close is reached and the next becomes current.
pub const REACH_M: f32 = 1.0;
/// Waypoint `up` bounds (ENU metres); a waypoint outside them is refused. A drone also climbs at
/// least `MIN_UP_M` above its own pad before it cruises.
pub const MIN_UP_M: f32 = 5.0;
pub const MAX_UP_M: f32 = 60.0;

/// A returning drone flies at least this far above its pad, so it never comes home below the deck.
const RETURN_CLEARANCE_M: f32 = 2.0;
/// A climb is over this close to its height.
const CLIMB_DONE_M: f32 = 0.05;
/// A landing drone starts to sink once it is this close to the point above its pad.
const LAND_ALIGN_M: f32 = 0.5;
/// A landing drone docks once it is this close to the pad's centre, m, and turned to within this, degrees.
const DOCK_ALIGN_M: f32 = 0.04;
const DOCK_YAW_DEG: f32 = 1e-3;
/// Slower than this, a drone keeps its heading instead of turning to face its velocity, m/s.
const TURN_FLOOR_M_S: f32 = 0.5;
/// Float slack when a time is turned into a step number.
const STEP_SLACK: f32 = 1e-3;

/// A drone's pad: the deck centre in ENU and the heading it docks facing (degrees, ENU
/// counter-clockwise from east).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Home {
    pub pad_enu: [f32; 3],
    pub yaw_deg: f32,
}

/// What a drone is doing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Docked,
    Climbing,
    Cruising,
    Detouring,
    Hovering,
    Returning,
    Landing,
}

/// A drone's kinematic state at one step.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DroneState {
    pub position_enu: [f32; 3],
    pub velocity_enu: [f32; 3],
    /// Heading in degrees, ENU counter-clockwise from east (as `Home::yaw_deg`).
    pub yaw_deg: f32,
    pub phase: Phase,
    /// The point being flown to, if any.
    pub target: Option<[f32; 3]>,
    /// Route waypoints still to reach after `target`.
    pub legs_left: usize,
}

/// What a drone has been told to fly, as the log's commands leave it.
#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    pub home: Home,
    /// The route's remaining waypoints, the current one first.
    pub route: VecDeque<[f32; 3]>,
    /// Detour waypoints still to visit before the route resumes.
    pub detour: VecDeque<[f32; 3]>,
    pub speed_m_s: f32,
    pub on_complete: OnComplete,
}

impl Plan {
    fn new(home: Home) -> Self {
        Self { home, route: VecDeque::new(), detour: VecDeque::new(), speed_m_s: DEFAULT_SPEED_M_S, on_complete: OnComplete::Return }
    }

    /// The point being flown to, and whether it is a detour's: a detour first, else the route's.
    fn current(&self) -> Option<([f32; 3], bool)> {
        self.detour.front().map(|w| (*w, true)).or_else(|| self.route.front().map(|w| (*w, false)))
    }

    /// True when the current point is the last one the drone has to reach.
    fn on_last_leg(&self) -> bool {
        match self.current() {
            Some((_, true)) => self.detour.len() == 1 && self.route.is_empty(),
            Some((_, false)) => self.route.len() == 1,
            None => true,
        }
    }

    /// The targets to reach after the current one.
    fn legs_after_current(&self) -> usize {
        match self.current() {
            Some((_, true)) => self.detour.len() - 1 + self.route.len(),
            Some((_, false)) => self.route.len() - 1,
            None => 0,
        }
    }

    /// The point above the pad a returning drone flies to, from where it is.
    fn return_point(&self, position_enu: [f32; 3]) -> [f32; 3] {
        let [x, y, z] = self.home.pad_enu;
        [x, y, position_enu[2].max(z + RETURN_CLEARANCE_M)]
    }

    fn take(&mut self, route: &Route) {
        self.route = route.waypoints.iter().copied().collect();
        self.detour.clear();
        self.speed_m_s = route.speed_m_s;
        self.on_complete = route.on_complete;
    }
}

fn distance(a: [f32; 3], b: [f32; 3]) -> f32 {
    Vec3::from(a).distance(Vec3::from(b))
}

/// `angle` brought into `-180..180` degrees.
fn wrapped_deg(angle: f32) -> f32 {
    (angle + 180.0).rem_euclid(360.0) - 180.0
}

/// `yaw_deg` turned toward `target_deg` the short way, by at most the turn-rate limit.
fn turn_toward(yaw_deg: f32, target_deg: f32, dt: f32) -> f32 {
    let turn = wrapped_deg(target_deg - yaw_deg);
    yaw_deg + turn.clamp(-MAX_YAW_RATE_DEG_S * dt, MAX_YAW_RATE_DEG_S * dt)
}

/// The fastest a drone may still be going `distance` from a point it has to stop at.
fn approach_speed(distance: f32, top_m_s: f32, dt: f32) -> f32 {
    top_m_s.min((2.0 * MAX_ACCEL_M_S2 * distance).sqrt()).min(distance / dt)
}

/// `velocity` after a step toward `wanted`, changing by at most the acceleration limit.
fn accelerate(velocity: Vec2, wanted: Vec2, dt: f32) -> Vec2 {
    velocity + (wanted - velocity).clamp_length_max(MAX_ACCEL_M_S2 * dt)
}

/// A vertical speed after a step toward the point `remaining` metres away (signed), stopping on it.
fn accelerate_along(speed: f32, remaining: f32, top_m_s: f32, dt: f32) -> f32 {
    let wanted = remaining.signum() * approach_speed(remaining.abs(), top_m_s, dt);
    speed + (wanted - speed).clamp(-MAX_ACCEL_M_S2 * dt, MAX_ACCEL_M_S2 * dt)
}

/// Moves `state` by its velocity over `dt`.
fn drift(state: &mut DroneState, velocity: Vec3, dt: f32) {
    state.velocity_enu = velocity.to_array();
    state.position_enu = (Vec3::from(state.position_enu) + velocity * dt).to_array();
}

fn horizontal(velocity: [f32; 3]) -> Vec2 {
    Vec2::new(velocity[0], velocity[1])
}

#[cfg(test)]
thread_local! {
    /// The steps this test's thread has taken, for the step-count measurements.
    static STEPS_TAKEN: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

/// How many autopilot steps `work` takes on this thread, with its result. Test-only: production
/// carries no counter.
#[cfg(test)]
pub fn counting_steps<R>(work: impl FnOnce() -> R) -> (R, usize) {
    let before = STEPS_TAKEN.with(std::cell::Cell::get);
    let result = work();
    (result, STEPS_TAKEN.with(std::cell::Cell::get) - before)
}

/// Advances `state` by `dt` toward what `plan` says, within the limits; pops each target it
/// reaches.
pub fn step(state: &mut DroneState, plan: &mut Plan, dt: f32) {
    #[cfg(test)]
    STEPS_TAKEN.with(|taken| taken.set(taken.get() + 1));
    match state.phase {
        Phase::Docked => {}
        Phase::Climbing => climb(state, plan, dt),
        Phase::Landing => land(state, plan, dt),
        Phase::Cruising | Phase::Detouring | Phase::Hovering | Phase::Returning => navigate(state, plan, dt),
    }
    refresh_target(state, plan);
}

/// Straight up to the route's first height, or at least `MIN_UP_M` over the pad, then on to cruise.
fn climb(state: &mut DroneState, plan: &mut Plan, dt: f32) {
    let first_up = plan.current().map_or(f32::MIN, |(point, _)| point[2]);
    let remaining = first_up.max(plan.home.pad_enu[2] + MIN_UP_M) - state.position_enu[2];
    if remaining <= CLIMB_DONE_M {
        state.phase = Phase::Cruising;
        return navigate(state, plan, dt);
    }
    let level = accelerate(horizontal(state.velocity_enu), Vec2::ZERO, dt);
    let rising = accelerate_along(state.velocity_enu[2], remaining, MAX_CLIMB_M_S, dt);
    drift(state, level.extend(rising), dt);
}

/// One step of everything that flies on its own: legs, detours, hovering and the way home.
fn navigate(state: &mut DroneState, plan: &mut Plan, dt: f32) {
    if let Some((point, from_detour)) = plan.current() {
        if distance(state.position_enu, point) <= REACH_M {
            if from_detour { plan.detour.pop_front() } else { plan.route.pop_front() };
        }
    }
    state.phase = match (plan.current(), state.phase) {
        (Some((_, true)), _) => Phase::Detouring,
        (Some((_, false)), _) => Phase::Cruising,
        (None, Phase::Hovering | Phase::Returning) => state.phase,
        (None, _) => match plan.on_complete {
            OnComplete::Hover => Phase::Hovering,
            OnComplete::Return => Phase::Returning,
        },
    };
    match (state.phase, plan.current()) {
        (Phase::Hovering, _) => hover(state, dt),
        (Phase::Returning, _) => {
            let point = plan.return_point(state.position_enu);
            if distance(state.position_enu, point) <= REACH_M {
                state.phase = Phase::Landing;
                land(state, plan, dt);
            } else {
                fly_to(state, point, plan.speed_m_s, true, dt);
            }
        }
        (_, Some((point, _))) => fly_to(state, point, plan.speed_m_s, plan.on_last_leg(), dt),
        (_, None) => {}
    }
}

/// One step toward `point` at up to `speed_m_s`, braking to a stop on it when `stop`; the
/// horizontal speed is held to what the climb can match, so the drone arrives level with it.
fn fly_to(state: &mut DroneState, point: [f32; 3], speed_m_s: f32, stop: bool, dt: f32) {
    let to = Vec2::new(point[0] - state.position_enu[0], point[1] - state.position_enu[1]);
    let (along, up) = (to.length(), point[2] - state.position_enu[2]);
    let mut speed = speed_m_s.min(MAX_SPEED_M_S);
    if up.abs() > REACH_M {
        speed = speed.min(along * MAX_CLIMB_M_S / up.abs());
    }
    if stop {
        speed = approach_speed(along, speed, dt);
    }
    let wanted = if along > f32::EPSILON { to / along * speed } else { Vec2::ZERO };
    let level = accelerate(horizontal(state.velocity_enu), wanted, dt);
    let rising = accelerate_along(state.velocity_enu[2], up, MAX_CLIMB_M_S, dt);
    if level.length() > TURN_FLOOR_M_S {
        state.yaw_deg = turn_toward(state.yaw_deg, level.y.atan2(level.x).to_degrees(), dt);
    }
    drift(state, level.extend(rising), dt);
}

/// Slows to a stop where it is, within the acceleration limit.
fn hover(state: &mut DroneState, dt: f32) {
    let velocity = Vec3::from(state.velocity_enu);
    let slower = (velocity.length() - MAX_ACCEL_M_S2 * dt).max(0.0);
    drift(state, velocity.normalize_or_zero() * slower, dt);
}

/// Over the pad, turns to its heading and sinks to it at up to `MAX_DESCENT_M_S`, then docks.
fn land(state: &mut DroneState, plan: &mut Plan, dt: f32) {
    let home = plan.home;
    let to = Vec2::new(home.pad_enu[0] - state.position_enu[0], home.pad_enu[1] - state.position_enu[1]);
    let (along, drop) = (to.length(), state.position_enu[2] - home.pad_enu[2]);
    let settled = drop.abs() <= MAX_DESCENT_M_S * dt
        && along <= DOCK_ALIGN_M
        && horizontal(state.velocity_enu).length() <= MAX_ACCEL_M_S2 * dt
        && wrapped_deg(home.yaw_deg - state.yaw_deg).abs() <= DOCK_YAW_DEG;
    if settled {
        *state = docked(home);
        return;
    }
    let wanted = if along > f32::EPSILON { to / along * approach_speed(along, MAX_DESCENT_M_S, dt) } else { Vec2::ZERO };
    let level = accelerate(horizontal(state.velocity_enu), wanted, dt);
    let remaining = if along <= LAND_ALIGN_M { -drop } else { 0.0 };
    let sinking = accelerate_along(state.velocity_enu[2], remaining, MAX_DESCENT_M_S, dt);
    state.yaw_deg = turn_toward(state.yaw_deg, home.yaw_deg, dt);
    drift(state, level.extend(sinking), dt);
}

/// What a drone on `home` reports: on the pad, facing its heading, still.
fn docked(home: Home) -> DroneState {
    DroneState { position_enu: home.pad_enu, velocity_enu: [0.0; 3], yaw_deg: home.yaw_deg, phase: Phase::Docked, target: None, legs_left: 0 }
}

/// Brings `target` and `legs_left` up to date with what `plan` says about `state`'s phase.
fn refresh_target(state: &mut DroneState, plan: &Plan) {
    (state.target, state.legs_left) = match state.phase {
        Phase::Docked | Phase::Hovering => (None, 0),
        Phase::Climbing | Phase::Cruising | Phase::Detouring => (plan.current().map(|(point, _)| point), plan.legs_after_current()),
        Phase::Returning => (Some(plan.return_point(state.position_enu)), 0),
        Phase::Landing => (Some(plan.home.pad_enu), 0),
    };
}

/// What a command does to a drone that is allowed to take it; the log has already refused the
/// rest, and a replay that meets one anyway ignores it.
fn apply(state: &mut DroneState, plan: &mut Plan, command: &FleetCommand) {
    let flying = !matches!(state.phase, Phase::Docked | Phase::Landing);
    match command {
        FleetCommand::Launch { route, .. } if state.phase == Phase::Docked => {
            plan.take(route);
            state.phase = Phase::Climbing;
        }
        FleetCommand::SetRoute { route, .. } if flying => {
            plan.take(route);
            if state.phase != Phase::Climbing {
                state.phase = Phase::Cruising;
            }
        }
        FleetCommand::Detour { waypoints, .. } if flying => plan.detour = waypoints.iter().copied().collect(),
        FleetCommand::Recall { .. } if flying => {
            plan.route.clear();
            plan.detour.clear();
            plan.on_complete = OnComplete::Return;
            state.phase = Phase::Returning;
        }
        _ => {}
    }
    refresh_target(state, plan);
}

/// The step a command stamped `at_s` takes effect before: the first at or after its moment.
fn due_step(at_s: f32) -> usize {
    (at_s / STEP_S - STEP_SLACK).ceil().max(0.0) as usize
}

/// How many whole steps lie in `0..=t_s`.
fn steps_until(t_s: f32) -> usize {
    (t_s / STEP_S + STEP_SLACK).floor().max(0.0) as usize
}

/// The state of drone `id`, docked on `home` at `t = 0`, after replaying `log` to `t_s`. The
/// definition the incremental `Autopilot` must equal; production advances one instead.
#[cfg(test)]
pub fn state_at(home: Home, id: &str, log: &FleetLog, t_s: f32) -> DroneState {
    Autopilot::new(id, home).advance(log, t_s)
}

/// The phase drone `id` is in when a command stamped `at_s` reaches it: every logged command up to
/// that moment applied, none after. The definition `Autopilot::phase_when` must equal; the log
/// asks its own checker instead.
#[cfg(test)]
pub(super) fn phase_when(home: Home, id: &str, log: &FleetLog, at_s: f32) -> Phase {
    let mut pilot = Autopilot::new(id, home);
    let due = due_step(at_s);
    pilot.run_to(log.entries(), due);
    pilot.apply_due(log.entries(), due);
    pilot.state.phase
}

/// The live app's autopilot for one drone: it advances from where it last was instead of
/// replaying from `t = 0`, and equals `state_at` at every moment. A command added to the log must
/// be stamped no earlier than the last moment advanced to, as the live station stamps its own.
#[derive(Debug, Clone, PartialEq)]
pub struct Autopilot {
    id: String,
    state: DroneState,
    plan: Plan,
    /// Steps taken so far.
    steps: usize,
    /// Log entries looked at so far (the other drones' included).
    applied: usize,
}

impl Autopilot {
    /// Drone `id`, docked on `home` at `t = 0`.
    pub fn new(id: &str, home: Home) -> Self {
        Self { id: id.to_owned(), state: docked(home), plan: Plan::new(home), steps: 0, applied: 0 }
    }

    /// The drone's id.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// Where the drone was at the last moment advanced to.
    pub fn state(&self) -> DroneState {
        self.state
    }

    /// Advances to `t_s`, applying `log`'s new entries. An earlier moment than the last call
    /// replays from the pad, as `state_at` does.
    pub fn advance(&mut self, log: &FleetLog, t_s: f32) -> DroneState {
        let steps = steps_until(t_s);
        if steps < self.steps {
            *self = Self::new(&self.id, self.plan.home);
        }
        self.run_to(log.entries(), steps);
        self.state
    }

    /// The phase this drone is in when a command stamped `at_s` reaches it: every entry of
    /// `entries` up to that moment applied, none after. It continues from where it last was, so
    /// the moments asked must not decrease; an earlier one replays from the pad.
    pub(super) fn phase_when(&mut self, entries: &[Stamped], at_s: f32) -> Phase {
        let due = due_step(at_s);
        if due < self.steps {
            *self = Self::new(&self.id, self.plan.home);
        }
        self.run_to(entries, due);
        self.apply_due(entries, due);
        self.state.phase
    }

    fn run_to(&mut self, entries: &[Stamped], steps: usize) {
        while self.steps < steps {
            self.apply_due(entries, self.steps);
            step(&mut self.state, &mut self.plan, STEP_S);
            self.steps += 1;
        }
    }

    /// Applies the log's entries that take effect before step `k`.
    fn apply_due(&mut self, entries: &[Stamped], k: usize) {
        while let Some(entry) = entries.get(self.applied).filter(|e| due_step(e.at_s) <= k) {
            if entry.command.drone() == self.id {
                apply(&mut self.state, &mut self.plan, &entry.command);
            }
            self.applied += 1;
        }
    }
}

#[cfg(test)]
mod tests;
