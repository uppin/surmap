//! Moving people at run time (changeset § *Runtime*; visual spec § *People* and *Wind*). A person
//! with a behaviour tree is ticked at the fixed rate on the simulation clock, faces the way it
//! walks with its yaw eased over `yaw_ease_s`, and bobs while it walks. The scenario's wind tree
//! drives `Wildfire::wind`, so vegetation, fire and particles follow it. Every number lives in
//! `assets/behaviour/person.figure.json`, never here.

#![allow(dead_code)]

use std::f32::consts::{PI, TAU};

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::math::{Quat, Vec2, Vec3};
use bevy::prelude::{Assets, Component, Handle, Query, Res, ResMut, Resource, Transform};
use bevy::reflect::TypePath;
use serde::Deserialize;

use crate::behaviour::{Runner, Tree, World, TICK_HZ};
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

/// One `object_tracks.jsonl` line (changeset § *Ground truth*): the frame's time, the wind's
/// velocity (ENU m/s) and each moving body, by id.
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
    let root = weather.wind.behaviour.clone()?;
    Some(Runner::new(
        Tree { root },
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
    mut behaviour: ResMut<Behaviour>,
    mut figures: Query<&mut Figure>,
) {
    let (Some(look), Some(mut scene)) = (look, scene) else {
        return;
    };
    let Some(FigureAsset(gait)) = looks.get(&look.0) else {
        return;
    };
    let now = clock.now();
    while tick_time(behaviour.ticks) <= now + CLOCK_SLACK_S {
        let t_s = tick_time(behaviour.ticks);
        tick_once(
            t_s,
            &mut behaviour,
            &mut scene,
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
    let objects: Vec<(String, Vec2)> = figures
        .iter()
        .map(|figure| (figure.id.clone(), figure.position()))
        .collect();
    let world = World {
        t_s,
        fires: &fires,
        burning_areas: &[],
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
mod tests {
    use std::f32::consts::{FRAC_PI_2, FRAC_PI_4};

    use bevy::math::Vec3;

    use super::*;

    fn gait() -> FigureDef {
        FigureDef {
            yaw_ease_s: 0.3,
            bob_m: 0.03,
            steps_per_s: 2.0,
            reference_speed_m_s: 1.4,
        }
    }

    #[test]
    fn a_turn_eases_to_its_heading_over_its_duration_and_then_holds() {
        let turn = Turn {
            from: 0.0,
            to: FRAC_PI_2,
            started_s: 1.0,
        };

        assert!(yaw_at(turn, 1.0, 0.3).abs() < 1e-6);
        assert!((yaw_at(turn, 1.15, 0.3) - FRAC_PI_4).abs() < 1e-5);
        assert!((yaw_at(turn, 1.3, 0.3) - FRAC_PI_2).abs() < 1e-6);
        assert!((yaw_at(turn, 9.0, 0.3) - FRAC_PI_2).abs() < 1e-6);
    }

    #[test]
    fn a_turn_takes_the_short_way_round_the_circle() {
        let turn = Turn {
            from: 3.0,
            to: -3.0,
            started_s: 0.0,
        };

        let midway = yaw_at(turn, 0.15, 0.3);
        let end = yaw_at(turn, 1.0, 0.3);

        assert!(midway.cos() < -0.9, "through π, not through 0: {midway}");
        assert!((end.cos() - (-3.0f32).cos()).abs() < 1e-5);
        assert!((end.sin() - (-3.0f32).sin()).abs() < 1e-5);
    }

    #[test]
    fn a_figure_faces_its_heading_in_bevy_space() {
        for (heading, forward) in [
            (Vec2::X, Vec3::X),
            (Vec2::Y, Vec3::NEG_Z),
            (Vec2::NEG_X, Vec3::NEG_X),
        ] {
            let facing = Quat::from_rotation_y(bevy_yaw(heading)) * Vec3::NEG_Z;

            assert!(
                facing.abs_diff_eq(forward, 1e-5),
                "{heading:?} faces {facing:?}"
            );
        }
    }

    #[test]
    fn a_walker_bobs_once_per_step_at_its_step_rate() {
        let at = |t| bob(&gait(), 1.4, 0.0, t);

        assert!((at(0.25) - 0.03).abs() < 1e-6, "a step's peak");
        assert!(at(0.5).abs() < 1e-6, "back on the ground between steps");
        assert!((at(0.75) - 0.03).abs() < 1e-6);
    }

    #[test]
    fn a_faster_walker_steps_in_proportion_to_its_speed() {
        let peak_at_double_speed = bob(&gait(), 2.8, 0.0, 0.125);

        assert!((peak_at_double_speed - 0.03).abs() < 1e-6);
    }

    #[test]
    fn a_standing_figure_does_not_bob() {
        assert_eq!(bob(&gait(), 0.0, 0.0, 0.3), 0.0);
    }

    #[test]
    fn each_figure_steps_on_its_own_phase_and_the_same_one_every_time() {
        let phase = phase_of("evacuee-1");

        assert_eq!(phase, phase_of("evacuee-1"));
        assert_ne!(phase, phase_of("evacuee-2"));
        assert!((0.0..TAU).contains(&phase), "{phase}");
    }

    #[test]
    fn the_figure_numbers_come_from_json_and_nonsense_is_refused_by_name() {
        let def = FigureDef::from_json(
            r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4}"#,
        )
        .expect("valid");
        let missing =
            FigureDef::from_json(r#"{"yaw_ease_s": 0.3, "bob_m": 0.03, "steps_per_s": 2}"#)
                .unwrap_err();
        let stuck = FigureDef::from_json(
            r#"{"yaw_ease_s": 0, "bob_m": 0.03, "steps_per_s": 2, "reference_speed_m_s": 1.4}"#,
        )
        .unwrap_err();

        assert_eq!(def, gait());
        assert!(missing.contains("reference_speed_m_s"), "{missing}");
        assert!(stuck.contains("yaw_ease_s"), "{stuck}");
    }

    #[test]
    fn the_track_line_carries_the_frame_time_the_wind_and_each_moving_body_by_id() {
        let line = track_line(
            1_000_000_000,
            Vec2::new(6.0, 0.5),
            &[
                Body {
                    id: "evacuee-2".to_owned(),
                    enu: Vec3::new(12.0, 61.0, 0.0),
                    action: Some("flee_from_fire".to_owned()),
                },
                Body {
                    id: "evacuee-1".to_owned(),
                    enu: Vec3::new(1.0, 2.0, 0.0),
                    action: None,
                },
            ],
        );

        let parsed: serde_json::Value = serde_json::from_str(&line).expect("json");
        assert_eq!(
            parsed,
            serde_json::json!({
                "t_ns": 1_000_000_000u64,
                "wind_enu": [6.0, 0.5],
                "objects": [
                    {"id": "evacuee-1", "enu": [1.0, 2.0, 0.0], "action": null},
                    {"id": "evacuee-2", "enu": [12.0, 61.0, 0.0], "action": "flee_from_fire"}
                ]
            })
        );
    }

    #[test]
    fn a_figure_turns_to_face_the_way_it_walks() {
        let walk = crate::behaviour::Tree::from_json(
            r#"{"node": "move_to", "enu": [10, 0], "speed_m_s": 2}"#,
        )
        .expect("tree");
        let mut figure = Figure::new("evacuee-1", [0.0, 0.0, 0.0], Some(walk));
        let world = World {
            t_s: 0.0,
            fires: &[],
            burning_areas: &[],
            wind: &WindModel {
                from_deg: 0.0,
                speed_m_s: 0.0,
                gust_m_s: 0.0,
            },
            objects: &[],
        };

        figure.step(&world, 0.3);

        assert!(
            (figure.turn.to - bevy_yaw(Vec2::X)).abs() < 1e-5,
            "{:?}",
            figure.turn
        );
    }
}
