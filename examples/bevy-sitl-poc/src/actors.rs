//! Moving people at run time (docs/simulation/bevy-simulation.md § *Behaviour trees*). A person
//! with a behaviour tree is ticked at the fixed rate on the simulation clock, faces the way it
//! walks with its yaw eased over `yaw_ease_s`, and bobs while it walks. The scenario's wind tree
//! drives `Wildfire::wind`, so vegetation, fire and particles follow it. Every number lives in
//! `assets/behaviour/person.figure.json`, never here.

use std::collections::HashMap;
use std::f32::consts::{PI, TAU};

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::math::{Quat, Vec2, Vec3};
use bevy::prelude::{
    AssetServer, Assets, Children, Color, Commands, Component, Cuboid, Entity, Handle, Has, Mesh, Mesh3d,
    MeshMaterial3d, Name, On, Query, Res, ResMut, Resource, StandardMaterial, Transform, With, Without,
};
use bevy::reflect::TypePath;
use serde::Deserialize;

use crate::behaviour::{Runner, Tree, World, TICK_HZ};
use crate::building::BuildingClock;
use crate::building_fire::BuildingFires;
use crate::figure_anim::Pose;
use crate::fire::FireSpec;
use crate::scene_manifest::Weather;
use crate::vehicle::scene::{VehicleActor, VehicleAsset, VehicleClasses};
use crate::wildfire::{SimClock, Wildfire};
use crate::wind::WindModel;
use crate::wire::GroundTruthObject;
use crate::world::enu;

pub mod rig;

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

mod model;
mod tick;

pub use model::{attach_bodies, pose_figures, FallbackBody, FigureCoat};
pub use tick::{tick_behaviours, wind_runner, Behaviour};

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
    /// The rigged glTF and its clips; without one the figure is the capsule and the visor.
    #[serde(default)]
    pub rig: Option<crate::figure_anim::RigDef>,
    /// A rig for a person who holds a pose the primary rig carries no clip for (a sitting person
    /// on a sit model). Keys are `lying`, `sitting` or `waving`; each validates like `rig`.
    #[serde(default)]
    pub pose_rigs: HashMap<Pose, crate::figure_anim::RigDef>,
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
    /// The rig a person in `pose` is drawn on: the pose's own rig, else the primary rig; its file
    /// replaced by the person's `rig_glb` when they name one; scaled to their `height_m`.
    pub fn rig_for(
        &self,
        pose: Pose,
        height_m: Option<f32>,
        rig_glb: Option<&str>,
    ) -> Option<crate::figure_anim::RigDef> {
        let mut rig = self.pose_rigs.get(&pose).or(self.rig.as_ref())?.clone();
        if let Some(glb) = rig_glb {
            rig.glb = glb.to_owned();
        }
        Some(rig.at_height(height_m))
    }

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
        if let Some(rig) = &def.rig {
            rig.validate()?;
        }
        if def.rig.is_none() && !def.pose_rigs.is_empty() {
            return Err("pose_rigs needs the figure's own rig, which carries standing".into());
        }
        for (pose, rig) in &def.pose_rigs {
            if *pose == Pose::Standing {
                return Err("pose_rigs must not name standing: the figure's rig carries it".into());
            }
            rig.validate().map_err(|e| format!("pose_rigs {}: {e}", pose.name()))?;
        }
        if def.rig.is_some() {
            for pose in [Pose::Standing, Pose::Lying, Pose::Sitting, Pose::Waving] {
                let named = def.pose_rigs.get(&pose).or(def.rig.as_ref()).and_then(|rig| rig.clip_for(pose));
                if named.is_none() {
                    return Err(format!(
                        "no clip for pose {}: name one in rig clips or in pose_rigs.{}",
                        pose.name(),
                        pose.name()
                    ));
                }
            }
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

/// The ENU heading (degrees counter-clockwise from east) of a Bevy yaw about +Y: the inverse of
/// `bevy_yaw`.
pub fn enu_yaw_deg(bevy: f32) -> f32 {
    bevy.cos().atan2(-bevy.sin()).to_degrees()
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
    /// A person's pose (`lying`, …); `None` for a vehicle.
    pub pose: Option<String>,
}

/// One `object_tracks.jsonl` line (bevy-simulation.md § *Presets, ground truth and stills*): the
/// frame's time, the wind's velocity (ENU m/s) and each moving body, by id.
pub fn track_line(t_ns: u64, wind: Vec2, bodies: &[Body]) -> String {
    let mut sorted: Vec<&Body> = bodies.iter().collect();
    sorted.sort_by(|a, b| a.id.cmp(&b.id));
    let objects: Vec<serde_json::Value> = sorted
        .iter()
        .map(|body| {
            let mut object = serde_json::json!({
                "id": body.id,
                "enu": [body.enu.x, body.enu.y, body.enu.z],
                "action": body.action,
                "kind": body.kind,
                "yaw_deg": body.yaw_deg,
            });
            if let Some(pose) = &body.pose {
                object["pose"] = serde_json::json!(pose);
            }
            object
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
    /// How the person holds themself when not walking.
    pose: Pose,
    /// The way a posed person faces, ENU degrees counter-clockwise from east.
    yaw_deg: f32,
    /// Body height, m; the rig's own height when absent.
    pub height_m: Option<f32>,
    /// A rig for this person instead of the figure's own.
    pub rig_glb: Option<String>,
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
            pose: Pose::Standing,
            yaw_deg: 0.0,
            height_m: None,
            rig_glb: None,
        }
    }

    /// The figure in `pose`, facing `yaw_deg` (ENU, counter-clockwise from east) while it stands;
    /// a posed person is tracked even without a tree.
    pub fn posed(mut self, pose: Pose, yaw_deg: f32) -> Self {
        let facing = bevy_yaw(Vec2::from_angle(yaw_deg.to_radians()));
        self.pose = pose;
        self.yaw_deg = yaw_deg;
        self.turn = Turn {
            from: facing,
            to: facing,
            started_s: 0.0,
        };
        self
    }

    /// How the person holds themself when not walking.
    pub fn pose(&self) -> Pose {
        self.pose
    }

    /// The person's speed over the last tick, m/s.
    pub fn speed_m_s(&self) -> f32 {
        self.speed_m_s
    }

    /// The person's step phase (a fixed fraction of a cycle per id).
    pub fn phase(&self) -> f32 {
        self.phase
    }

    /// The person's height (scales the rig) and a rig override (`glb`) for this person alone.
    pub fn with_stature(mut self, height_m: Option<f32>, rig_glb: Option<String>) -> Self {
        self.height_m = height_m;
        self.rig_glb = rig_glb;
        self
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
        if self.runner.is_none() && self.pose == Pose::Standing {
            return None;
        }
        let at = self.position();
        Some(Body {
            id: self.id.clone(),
            enu: Vec3::new(at.x, at.y, self.ground_z),
            action: self
                .runner
                .as_ref()
                .and_then(|runner| runner.action().map(str::to_owned)),
            kind: "person".to_owned(),
            yaw_deg: if self.runner.is_some() { enu_yaw_deg(self.turn.to) } else { self.yaw_deg },
            pose: Some(self.pose.name().to_owned()),
        })
    }
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

/// A figure whose visor (if its look declares one) has been put on.
#[derive(Component)]
pub struct Visored;

/// The capsule, head and visor a figure shows until its rig is ready (then they are hidden).
#[derive(Component)]
pub struct StandIn;

/// A person's coat and skin materials: the rig's coat and skin slots take them.
#[derive(Component, Clone)]
pub struct PersonLook {
    pub coat: Handle<StandardMaterial>,
    pub skin: Handle<StandardMaterial>,
}

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
                StandIn,
            ));
        });
    }
}

/// Each figure's pose at the simulation's moment: its turn eased, and its step bob. A figure whose
/// rig is shown carries its gait in the clips, so it does not bob.
pub fn animate_figures(
    clock: SimClock,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    mut figures: Query<(&Figure, &mut Transform, Has<rig::RigShown>)>,
) {
    let Some(FigureAsset(gait)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    let now = clock.now();
    for (figure, mut transform, rig_shown) in &mut figures {
        let bob_m = if rig_shown {
            0.0
        } else {
            bob(gait, figure.speed_m_s, figure.phase, now)
        };
        transform.translation = figure.bevy_base() + Vec3::Y * bob_m;
        transform.rotation = Quat::from_rotation_y(yaw_at(figure.turn, now, gait.yaw_ease_s));
    }
}

#[cfg(test)]
mod tests;
