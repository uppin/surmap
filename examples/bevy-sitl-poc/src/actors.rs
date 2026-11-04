//! Moving people at run time (docs/simulation/bevy-simulation.md § *Behaviour trees*). A person
//! with a behaviour tree is ticked at the fixed rate on the simulation clock, faces the way it
//! walks with its yaw eased over `yaw_ease_s`, and bobs while it walks. The scenario's wind tree
//! drives `Wildfire::wind`, so vegetation, fire and particles follow it. Every number lives in
//! `assets/behaviour/person.figure.json`, never here.

use std::f32::consts::{PI, TAU};

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::math::{Quat, Vec2, Vec3};
use bevy::animation::graph::{AnimationGraph, AnimationGraphHandle, AnimationNodeIndex};
use bevy::animation::{AnimationClip, AnimationPlayer};
use bevy::gltf::GltfAssetLabel;
use bevy::prelude::{
    AssetServer, Assets, Children, Color, Commands, Component, Cuboid, Entity, Handle, Mesh, Mesh3d, MeshMaterial3d,
    Name, On, Query, Res, ResMut, Resource, StandardMaterial, Transform, With, Without,
};
use bevy::scene::{SceneInstanceReady, SceneRoot};
use bevy::reflect::TypePath;
use serde::Deserialize;

use crate::behaviour::{Runner, Tree, World, TICK_HZ};
use crate::building::BuildingClock;
use crate::building_fire::BuildingFires;
use crate::fire::FireSpec;
use crate::scene_manifest::Weather;
use crate::wildfire::{SimClock, Wildfire};
use crate::wind::WindModel;
use crate::wire::GroundTruthObject;
use crate::world::{enu, GroundTruth};

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
#[derive(Debug, Clone, PartialEq, Deserialize)]
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
    /// A dark visor on the front of the head, so the heading reads (on the capsule figure only).
    #[serde(default)]
    pub visor: Option<Visor>,
    /// A rigged humanoid glTF the figure wears instead of the capsule.
    #[serde(default)]
    pub model: Option<FigureModel>,
    /// The `person` ground-truth box (east, north, up m) over the feet; it holds the body
    /// whatever way the figure faces.
    #[serde(default = "default_body_m")]
    pub body_m: [f32; 3],
}

fn default_body_m() -> [f32; 3] {
    [0.6, 0.6, 1.8]
}

/// A humanoid glTF: scaled and turned so it stands on the figure's feet facing its front (-z),
/// posed from its first animation clip: at `clip_s` standing, played in step while walking.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FigureModel {
    pub glb: String,
    pub scale: f32,
    #[serde(default)]
    pub yaw_deg: f32,
    #[serde(default)]
    pub clip_s: f32,
    /// Multiply the model's colours by the person's `coat` (a survivor in a hi-vis coverall).
    #[serde(default)]
    pub coat_tint: bool,
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
        if let Some(model) = &def.model {
            let inside = !model.glb.starts_with('/') && model.glb.split('/').all(|part| !part.is_empty() && part != "..");
            if !inside || !(model.glb.ends_with(".glb") || model.glb.ends_with(".gltf")) {
                return Err(format!("model glb {:?} must be a .glb/.gltf inside assets/", model.glb));
            }
            if model.scale <= 0.0 {
                return Err("model scale must be > 0".into());
            }
        }
        if def.body_m.iter().any(|side| *side <= 0.0) {
            return Err("body_m sides must be > 0".into());
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

/// The moment of a figure model's clip (of `duration_s`) to show at `now_s`: the model's rest
/// moment standing still; walking, the clip plays at `speed / reference_speed` from the figure's
/// own phase, so a crowd does not stride in unison.
pub fn clip_time(model: &FigureModel, speed_m_s: f32, reference_speed_m_s: f32, phase: f32, now_s: f32, duration_s: f32) -> f32 {
    if speed_m_s <= 0.0 || duration_s <= 0.0 {
        return model.clip_s;
    }
    (now_s * speed_m_s / reference_speed_m_s + phase / TAU * duration_s).rem_euclid(duration_s)
}

/// A survivor's `person` ground-truth box: `body_m` (east, north, up) centred over the feet.
pub fn person_truth(id: &str, position_enu: [f32; 3], body_m: [f32; 3]) -> GroundTruthObject {
    let [x, y, z] = position_enu;
    let [east, north, up] = body_m;
    GroundTruthObject {
        id: id.to_owned(),
        kind: "person".into(),
        min_enu: [x - east / 2.0, y - north / 2.0, z],
        max_enu: [x + east / 2.0, y + north / 2.0, z + up],
    }
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
    /// What the body is: `person`, or a vehicle's class (`car`, `bus`, …).
    pub kind: String,
    /// The way it faces, ENU degrees counter-clockwise from east.
    pub yaw_deg: f32,
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

    /// The figure's ground place in Bevy space (public form of `bevy_base`).
    pub fn bevy_position(&self) -> Vec3 {
        self.bevy_base()
    }

    /// The yaw (Bevy, about +Y) the figure is turning to; its front is −Z rotated by it.
    pub fn facing_yaw(&self) -> f32 {
        self.turn.to
    }

    /// Where the figure was placed (ENU, feet), before any walking.
    pub fn feet_enu(&self) -> [f32; 3] {
        [self.base.x, self.base.y, self.ground_z]
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
            // TODO(pr-1): implement — the figure's facing.
            kind: "person".to_owned(),
            yaw_deg: 0.0,
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

/// The capsule body and head a figure is built with; dropped once it wears a model.
#[derive(Component)]
pub struct FallbackBody;

/// The person's coat material, for a model that wears it (`coat_tint`).
#[derive(Component)]
pub struct FigureCoat(pub Handle<StandardMaterial>);

/// A figure whose body (model or capsule) and ground-truth box are settled.
#[derive(Component)]
pub struct Bodied;

/// A figure's model child: the figure it belongs to and the glTF it came from.
#[derive(Component)]
pub struct FigureBody {
    figure: Entity,
    glb: String,
    coat_tint: bool,
}

/// A figure whose model has spawned: the player posing it, its clip node and the clip.
#[derive(Component)]
pub struct FigureRig {
    player: Entity,
    node: AnimationNodeIndex,
    clip: Handle<AnimationClip>,
}

/// Once the figure look has loaded: every survivor's `person` ground-truth box, and the
/// humanoid model (if the look declares one) in place of the capsule.
pub fn attach_bodies(
    mut commands: Commands,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    assets: Res<AssetServer>,
    mut truth: ResMut<GroundTruth>,
    figures: Query<(Entity, &Figure, &Children), Without<Bodied>>,
    fallback: Query<(), With<FallbackBody>>,
) {
    let Some(FigureAsset(def)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    for (entity, figure, children) in &figures {
        commands.entity(entity).insert(Bodied);
        truth.0.push(person_truth(&figure.id, figure.feet_enu(), def.body_m));
        let Some(model) = &def.model else {
            continue;
        };
        for child in children.iter().copied().filter(|child| fallback.contains(*child)) {
            commands.entity(child).despawn();
        }
        let scene = assets.load(GltfAssetLabel::Scene(0).from_asset(model.glb.clone()));
        let turned = Transform::from_rotation(Quat::from_rotation_y(model.yaw_deg.to_radians()))
            .with_scale(Vec3::splat(model.scale));
        let body = commands
            .spawn((Name::new("Body"), SceneRoot(scene), turned, FigureBody { figure: entity, glb: model.glb.clone(), coat_tint: model.coat_tint }))
            .observe(on_figure_model_ready)
            .id();
        commands.entity(entity).add_child(body);
    }
}

/// A figure model's scene has spawned: give its animation player the model's first clip.
fn on_figure_model_ready(
    ready: On<SceneInstanceReady>,
    mut commands: Commands,
    bodies: Query<&FigureBody>,
    children: Query<&Children>,
    players: Query<(), With<AnimationPlayer>>,
    coats: Query<&FigureCoat>,
    mut looks: Query<&mut MeshMaterial3d<StandardMaterial>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    assets: Res<AssetServer>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    let Ok(body) = bodies.get(ready.entity) else {
        return;
    };
    let coat = coats.get(body.figure).ok().and_then(|coat| materials.get(&coat.0)).map(|coat| coat.base_color);
    if let (true, Some(coat)) = (body.coat_tint, coat) {
        for part in children.iter_descendants(ready.entity) {
            let Ok(mut look) = looks.get_mut(part) else { continue };
            let Some(mut worn) = materials.get(&look.0).cloned() else { continue };
            let (have, tint) = (worn.base_color.to_linear(), coat.to_linear());
            worn.base_color = Color::linear_rgba(have.red * tint.red, have.green * tint.green, have.blue * tint.blue, have.alpha);
            look.0 = materials.add(worn);
        }
    }
    let Some(player) = children.iter_descendants(ready.entity).find(|e| players.contains(*e)) else {
        return;
    };
    let clip: Handle<AnimationClip> = assets.load(GltfAssetLabel::Animation(0).from_asset(body.glb.clone()));
    let (graph, node) = AnimationGraph::from_clip(clip.clone());
    commands.entity(player).insert(AnimationGraphHandle(graphs.add(graph)));
    commands.entity(body.figure).insert(FigureRig { player, node, clip });
}

/// Each model's pose at the simulation's moment: its clip held at the rest moment standing,
/// played in step walking. Seeking on the sim clock keeps a recording repeatable.
pub fn pose_figures(
    clock: SimClock,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    clips: Res<Assets<AnimationClip>>,
    figures: Query<(&Figure, &FigureRig)>,
    mut players: Query<&mut AnimationPlayer>,
) {
    let Some(FigureAsset(def)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    let Some(model) = &def.model else {
        return;
    };
    let now = clock.now();
    for (figure, rig) in &figures {
        let Ok(mut player) = players.get_mut(rig.player) else {
            continue;
        };
        let duration = clips.get(&rig.clip).map_or(0.0, AnimationClip::duration);
        let at = clip_time(model, figure.speed_m_s, def.reference_speed_m_s, figure.phase, now, duration);
        if player.animation(rig.node).is_none() {
            player.play(rig.node).pause();
        }
        if let Some(active) = player.animation_mut(rig.node) {
            active.seek_to(at);
        }
    }
}

/// A figure whose visor (if its look declares one) has been put on.
#[derive(Component)]
pub struct Visored;

/// Once the figure look has loaded, put its visor on the front of each figure's head.
pub fn attach_visors(
    mut commands: Commands,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    figures: Query<Entity, (With<Figure>, Without<Visored>)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Some(FigureAsset(def)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    // A humanoid model has a face: the visor is the capsule's heading cue only.
    let (Some(visor), None) = (def.visor, &def.model) else {
        return;
    };
    for figure in &figures {
        let [x, y, z] = visor.size_m;
        let [r, g, b] = visor.colour;
        commands.entity(figure).insert(Visored).with_children(|parent| {
            parent.spawn((
                Name::new("Visor"),
                Mesh3d(meshes.add(Cuboid::new(x, y, z))),
                MeshMaterial3d(materials.add(StandardMaterial {
                    base_color: Color::srgb(r, g, b),
                    perceptual_roughness: 0.3,
                    ..StandardMaterial::default()
                })),
                Transform::from_translation(Vec3::from(visor.offset_m)),
            ));
        });
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
