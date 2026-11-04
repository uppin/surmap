//! Moving people at run time (docs/simulation/bevy-simulation.md § *Behaviour trees*). A person
//! with a behaviour tree is ticked at the fixed rate on the simulation clock, faces the way it
//! walks with its yaw eased over `yaw_ease_s`, and bobs while it walks. The scenario's wind tree
//! drives `Wildfire::wind`, so vegetation, fire and particles follow it. Every number lives in
//! `assets/behaviour/person.figure.json`, never here.

use std::f32::consts::{PI, TAU};

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::math::{Quat, Vec2, Vec3};
use bevy::prelude::{Assets, Component, Handle, Query, Res, ResMut, Resource, Transform};
use bevy::reflect::TypePath;
use serde::Deserialize;

use crate::behaviour::{Runner, Tree, World, TICK_HZ};
use crate::building::BuildingClock;
use crate::building_fire::BuildingFires;
use crate::fire::FireSpec;
use crate::scene_manifest::Weather;
use crate::wildfire::{SimClock, Wildfire};
use crate::wind::WindModel;
use crate::world::enu;

/// Seconds of simulation time per tick.
const DT: f32 = 1.0 / TICK_HZ;
/// A tick that moves a body less than this (m) is standing still: no heading, no bob.
const MOVED_M: f32 = 1e-5;
/// Heading changes smaller than this (rad) do not start a new turn.
const TURN_EPS: f32 = 1e-4;
/// Slack on the simulation clock, so the tick at `now` is run despite float rounding (s).
const CLOCK_SLACK_S: f32 = 1e-4;
/// A person's runner carries no wind of its own; the scene's wind is passed to every tick.
const CALM: WindModel = WindModel {
    from_deg: 0.0,
    speed_m_s: 0.0,
    gust_m_s: 0.0,
};

/// The figure's gait and turn (`assets/behaviour/person.figure.json`).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FigureDef {
    /// Seconds a turn takes to ease to the new heading.
    pub yaw_ease_s: f32,
    /// Height of one step's bob, m.
    pub bob_m: f32,
    /// Steps per second at `reference_speed_m_s`; faster walking steps faster in proportion.
    pub steps_per_s: f32,
    /// The walking speed `steps_per_s` is quoted at, m/s.
    pub reference_speed_m_s: f32,
    /// A dark visor on the front of the head, so the heading reads.
    #[serde(default)]
    pub visor: Option<Visor>,
}

/// A box on the figure (`size_m` x, y, z in the figure's frame; `offset_m` from its feet, −z is
/// its front), solid `colour` (sRGB).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Visor {
    pub size_m: [f32; 3],
    pub offset_m: [f32; 3],
    pub colour: [f32; 3],
}

impl FigureDef {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let def: Self = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if def.yaw_ease_s <= 0.0 {
            return Err("yaw_ease_s must be > 0".into());
        }
        if def.bob_m < 0.0 {
            return Err("bob_m must be >= 0".into());
        }
        if def.steps_per_s <= 0.0 {
            return Err("steps_per_s must be > 0".into());
        }
        if def.reference_speed_m_s <= 0.0 {
            return Err("reference_speed_m_s must be > 0".into());
        }
        Ok(def)
    }
}

/// A figure's yaw turning from `from` to `to` (radians, Bevy Y axis), starting at `started_s`.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Turn {
    pub from: f32,
    pub to: f32,
    pub started_s: f32,
}

/// The yaw of a turn at `now_s`: eased over `ease_s`, the short way round.
pub fn yaw_at(turn: Turn, now_s: f32, ease_s: f32) -> f32 {
    let progress = ((now_s - turn.started_s) / ease_s).clamp(0.0, 1.0);
    let eased = progress * progress * (3.0 - 2.0 * progress);
    turn.from + wrap(turn.to - turn.from) * eased
}

/// `angle` folded into [-π, π).
fn wrap(angle: f32) -> f32 {
    (angle + PI).rem_euclid(TAU) - PI
}

/// The Bevy yaw (about +Y) that turns a figure's forward (-Z) to the ENU unit `heading`.
pub fn bevy_yaw(heading: Vec2) -> f32 {
    (-heading.x).atan2(heading.y)
}

/// The vertical bob of a figure at `now_s`: one bob per step, `bob_m` high at the top of each.
/// Steps per second scale with speed against the reference speed; standing still never bobs.
pub fn bob(def: &FigureDef, speed_m_s: f32, phase: f32, now_s: f32) -> f32 {
    if speed_m_s <= 0.0 {
        return 0.0;
    }
    let steps_per_s = def.steps_per_s * speed_m_s / def.reference_speed_m_s;
    def.bob_m * (PI * steps_per_s * now_s + phase).sin().abs()
}

/// A figure's step phase, a fixed fraction of a cycle per id, so the crowd does not step in unison.
pub fn phase_of(id: &str) -> f32 {
    let hash = id.bytes().fold(0x811c_9dc5u32, |h, b| {
        (h ^ u32::from(b)).wrapping_mul(0x0100_0193)
    });
    TAU * ((hash >> 8) as f32 / (1u32 << 24) as f32)
}

/// One moving body in a track frame: its id, ENU place and the action it is running.
#[derive(Debug, Clone, PartialEq)]
pub struct Body {
    pub id: String,
    pub enu: Vec3,
    pub action: Option<String>,
}

/// One `object_tracks.jsonl` line (bevy-simulation.md § *Presets, ground truth and stills*): the
/// frame's time, the wind's velocity (ENU m/s) and each moving body, by id.
pub fn track_line(t_ns: u64, wind: Vec2, bodies: &[Body]) -> String {
    let mut sorted: Vec<&Body> = bodies.iter().collect();
    sorted.sort_by(|a, b| a.id.cmp(&b.id));
    let objects: Vec<serde_json::Value> = sorted
        .iter()
        .map(|body| {
            serde_json::json!({
                "id": body.id,
                "enu": [body.enu.x, body.enu.y, body.enu.z],
                "action": body.action,
            })
        })
        .collect();
    serde_json::json!({"t_ns": t_ns, "wind_enu": [wind.x, wind.y], "objects": objects}).to_string()
}

/// A person's motion state on the root entity of its figure.
#[derive(Component)]
pub struct Figure {
    pub id: String,
    ground_z: f32,
    base: Vec2,
    runner: Option<Runner>,
    speed_m_s: f32,
    turn: Turn,
    phase: f32,
}

impl Figure {
    pub fn new(id: &str, position_enu: [f32; 3], tree: Option<Tree>) -> Self {
        let [x, y, z] = position_enu;
        let base = Vec2::new(x, y);
        Self {
            id: id.to_owned(),
            ground_z: z,
            base,
            runner: tree.map(|tree| Runner::new(tree, base, CALM)),
            speed_m_s: 0.0,
            turn: Turn::default(),
            phase: phase_of(id),
        }
    }

    /// Advance the figure's tree by one tick, and start a turn when its heading changes.
    pub fn step(&mut self, world: &World, yaw_ease_s: f32) {
        let Some(runner) = self.runner.as_mut() else {
            return;
        };
        let before = runner.position;
        runner.tick(world, DT);
        let moved = runner.position - before;
        self.speed_m_s = moved.length() / DT;
        if moved.length() > MOVED_M {
            let heading = bevy_yaw(moved.normalize());
            if wrap(heading - self.turn.to).abs() > TURN_EPS {
                self.turn = Turn {
                    from: yaw_at(self.turn, world.t_s, yaw_ease_s),
                    to: heading,
                    started_s: world.t_s,
                };
            }
        }
    }

    /// Where the figure stands, ENU, before its bob.
    pub fn position(&self) -> Vec2 {
        self.runner
            .as_ref()
            .map_or(self.base, |runner| runner.position)
    }

    /// The figure's place on the ground in Bevy space, before its bob.
    fn bevy_base(&self) -> Vec3 {
        let at = self.position();
        enu(at.x, at.y, self.ground_z)
    }

    /// The figure as a moving body in a track frame; `None` for a person standing still.
    pub fn body(&self) -> Option<Body> {
        let runner = self.runner.as_ref()?;
        Some(Body {
            id: self.id.clone(),
            enu: Vec3::new(runner.position.x, runner.position.y, self.ground_z),
            action: runner.action().map(str::to_owned),
        })
    }
}

/// The scenario's wind tree and the tick count: tick `n` runs at `n / TICK_HZ` seconds.
#[derive(Resource, Default)]
pub struct Behaviour {
    wind: Option<Runner>,
    ticks: u64,
}

impl Behaviour {
    pub fn new(wind: Option<Runner>) -> Self {
        Self { wind, ticks: 0 }
    }
}

/// The scenario's wind tree, when its weather has one; it starts from the weather's wind.
pub fn wind_runner(weather: Option<&Weather>) -> Option<Runner> {
    let weather = weather?;
    let tree = weather.wind.behaviour.clone()?;
    Some(Runner::new(
        tree,
        Vec2::ZERO,
        WindModel::from(&weather.wind),
    ))
}

/// The figure's gait and turn, loaded from `behaviour/person.figure.json`.
#[derive(Resource)]
pub struct FigureLook(pub Handle<FigureAsset>);

#[derive(Asset, TypePath, Debug)]
pub struct FigureAsset(pub FigureDef);

#[derive(Default, TypePath)]
pub struct FigureLoader;

impl AssetLoader for FigureLoader {
    type Asset = FigureAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(
        &self,
        reader: &mut dyn Reader,
        _: &(),
        _: &mut LoadContext<'_>,
    ) -> Result<FigureAsset, std::io::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
        FigureDef::from_json(&text)
            .map(FigureAsset)
            .map_err(std::io::Error::other)
    }

    fn extensions(&self) -> &[&str] {
        &["figure.json"]
    }
}

fn tick_time(ticks: u64) -> f32 {
    ticks as f32 * DT
}

/// Ticks every tree up to the simulation's moment, in order, then moves the figures. It runs
/// before the wind is read, so the vegetation, the fire and the particles see this tick's wind.
pub fn tick_behaviours(
    clock: SimClock,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    scene: Option<ResMut<Wildfire>>,
    buildings: BuildingClock,
    mut behaviour: ResMut<Behaviour>,
    mut figures: Query<&mut Figure>,
) {
    let (Some(look), Some(mut scene)) = (look, scene) else {
        return;
    };
    // The ticks of buildings still being raised would run without their fire: wait for them.
    if buildings.raising.is_some() {
        return;
    }
    let Some(FigureAsset(gait)) = looks.get(&look.0) else {
        return;
    };
    let now = clock.now();
    let mut fires = buildings.blaze.map(|blaze| blaze.map_unchanged(|b| &mut b.fires));
    while tick_time(behaviour.ticks) <= now + CLOCK_SLACK_S {
        let t_s = tick_time(behaviour.ticks);
        tick_once(
            t_s,
            &mut behaviour,
            &mut scene,
            fires.as_deref_mut(),
            &mut figures,
            gait.yaw_ease_s,
        );
        behaviour.ticks += 1;
    }
}

fn tick_once(
    t_s: f32,
    behaviour: &mut Behaviour,
    scene: &mut Wildfire,
    buildings: Option<&mut BuildingFires>,
    figures: &mut Query<&mut Figure>,
    yaw_ease_s: f32,
) {
    let fires: Vec<FireSpec> = scene.fire_specs();
    if let Some(wind) = behaviour.wind.as_mut() {
        let current = wind.wind;
        wind.tick(
            &World {
                t_s,
                fires: &fires,
                burning_areas: &[],
                wind: &current,
                objects: &[],
            },
            DT,
        );
        scene.wind = wind.wind;
    }
    let wind = scene.wind;
    // Buildings alight at this tick, for people to flee from.
    let burning_areas: Vec<Vec<Vec2>> = buildings.map_or_else(Vec::new, |buildings| {
        buildings.step(t_s, DT, wind.velocity_enu(t_s), &fires);
        buildings.burning_footprints()
    });
    let objects: Vec<(String, Vec2)> = figures
        .iter()
        .map(|figure| (figure.id.clone(), figure.position()))
        .collect();
    let world = World {
        t_s,
        fires: &fires,
        burning_areas: &burning_areas,
        wind: &wind,
        objects: &objects,
    };
    for mut figure in figures.iter_mut() {
        figure.step(&world, yaw_ease_s);
    }
}

/// Each figure's pose at the simulation's moment: its turn eased, and its step bob.
pub fn animate_figures(
    clock: SimClock,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    mut figures: Query<(&Figure, &mut Transform)>,
) {
    let Some(FigureAsset(gait)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    let now = clock.now();
    for (figure, mut transform) in &mut figures {
        transform.translation =
            figure.bevy_base() + Vec3::Y * bob(gait, figure.speed_m_s, figure.phase, now);
        transform.rotation = Quat::from_rotation_y(yaw_at(figure.turn, now, gait.yaw_ease_s));
    }
}

#[cfg(test)]
mod tests;
