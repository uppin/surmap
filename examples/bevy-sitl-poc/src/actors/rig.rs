//! The rigged person at run time (docs/simulation/bevy-simulation.md § *The figure*). The rig's
//! glTF spawns under each figure, scaled to the person's height, with one animation graph per rig
//! asset. Every frame each player's clips take the weights `locomotion` gives them, crossfaded over
//! `blend_s`, and each is seeked to its `clip_time` on the simulation clock, so nothing free-runs.
//! Until the rig's scene is ready — and for a figure with no rig — the capsule and visor stand in.

use std::collections::HashMap;

use bevy::asset::{AssetServer, Assets, Handle};
use bevy::gltf::{Gltf, GltfMaterialName};
use bevy::prelude::*;
use bevy::scene::{SceneInstanceReady, SceneRoot};

use super::{Figure, FigureAsset, FigureLook, PersonLook, StandIn};
use crate::figure_anim::{clip_time, locomotion, rig_scale, Clip, RigDef};
use crate::wildfire::SimClock;
use crate::world::SceneState;

/// The clips every rig plays, in a fixed order (an index into the per-clip arrays below).
const CLIPS: [Clip; 6] = [Clip::Idle, Clip::Walk, Clip::Run, Clip::Wave, Clip::Sit, Clip::Lie];

fn index_of(clip: Clip) -> usize {
    CLIPS.iter().position(|c| *c == clip).unwrap_or(0)
}

/// A clip of a built graph: its node, and the animation clip it plays (for its duration).
#[derive(Clone)]
struct Playing {
    clip: Clip,
    node: AnimationNodeIndex,
    animation: Handle<AnimationClip>,
}

/// One rig asset, built once its glTF has loaded: the scene, and the graph of its six clips.
struct BuiltRig {
    scene: Handle<Scene>,
    graph: Handle<AnimationGraph>,
    clips: Vec<Playing>,
}

/// A rig glTF in use, by path. `failed` names a clip the file does not have, so it is said once.
struct RigAsset {
    gltf: Handle<Gltf>,
    built: Option<BuiltRig>,
    failed: bool,
}

/// The rigs in use: the figure's own, and any a person names instead (`glb`).
#[derive(Resource, Default)]
pub struct Rigs {
    assets: HashMap<String, RigAsset>,
}

/// On a figure whose rig scene has been spawned under it.
#[derive(Component)]
pub struct Rigged;

/// On a figure whose rig scene is ready: its bob is the clips' own, and its stand-ins are hidden.
#[derive(Component)]
pub struct RigShown;

/// The rig's scene under a figure: its clip weights, eased toward what the person is doing.
#[derive(Component)]
pub struct RigRoot {
    figure: Entity,
    def: RigDef,
    clips: Vec<Playing>,
    graph: Handle<AnimationGraph>,
    weights: [f32; 6],
    at_s: f32,
    ready: bool,
}

/// Loads each rig glTF in use, and builds its graph once the file has its named clips.
pub fn prepare_rigs(
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    figures: Query<&Figure>,
    assets: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
    mut rigs: ResMut<Rigs>,
    mut scene: ResMut<SceneState>,
) {
    let Some(FigureAsset(def)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    let Some(rig) = def.rig.as_ref() else {
        return;
    };
    let mut wanted: Vec<String> = vec![rig.glb.clone()];
    wanted.extend(figures.iter().filter_map(|figure| figure.rig_glb.clone()));
    for glb in wanted {
        if rigs.assets.contains_key(&glb) {
            continue;
        }
        let gltf: Handle<Gltf> = assets.load(glb.clone());
        scene.pending.push(gltf.clone().untyped());
        rigs.assets.insert(glb, RigAsset { gltf, built: None, failed: false });
    }
    for (glb, asset) in rigs.assets.iter_mut() {
        if asset.built.is_some() || asset.failed {
            continue;
        }
        let Some(gltf) = gltfs.get(&asset.gltf) else {
            continue;
        };
        let mut graph = AnimationGraph::new();
        let root = graph.root;
        let mut clips = Vec::with_capacity(CLIPS.len());
        for clip in CLIPS {
            let Some(name) = rig.clips.name(clip) else {
                continue;
            };
            let Some(animation) = gltf.named_animations.get(name) else {
                warn!("rig {glb} has no animation named {name:?}; the figure stays a capsule");
                asset.failed = true;
                break;
            };
            let node = graph.add_clip(animation.clone(), 0.0, root);
            clips.push(Playing { clip, node, animation: animation.clone() });
        }
        if asset.failed {
            continue;
        }
        let Some(scene_handle) = gltf.scenes.first().cloned() else {
            asset.failed = true;
            continue;
        };
        asset.built = Some(BuiltRig { scene: scene_handle, graph: graphs.add(graph), clips });
    }
}

/// Spawns the rig under each figure that has one and whose rig is built, scaled to its height.
pub fn spawn_rigs(
    mut commands: Commands,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    rigs: Res<Rigs>,
    figures: Query<(Entity, &Figure), Without<Rigged>>,
) {
    let Some(FigureAsset(def)) = look.and_then(|look| looks.get(&look.0)) else {
        return;
    };
    let Some(rig) = def.rig.as_ref() else {
        return;
    };
    for (figure_entity, figure) in &figures {
        let glb = figure.rig_glb.clone().unwrap_or_else(|| rig.glb.clone());
        let Some(built) = rigs.assets.get(&glb).and_then(|asset| asset.built.as_ref()) else {
            continue;
        };
        let mut figure_rig = rig.clone();
        figure_rig.glb = glb;
        let scale = rig_scale(rig, figure.height_m);
        let root = RigRoot {
            figure: figure_entity,
            def: figure_rig,
            clips: built.clips.clone(),
            graph: built.graph.clone(),
            weights: [0.0; 6],
            at_s: 0.0,
            ready: false,
        };
        commands.entity(figure_entity).insert(Rigged).with_children(|parent| {
            parent
                .spawn((
                    SceneRoot(built.scene.clone()),
                    Transform::from_scale(Vec3::splat(scale)),
                    root,
                ))
                .observe(on_rig_ready);
        });
    }
}

/// The rig's scene has spawned: each of its players plays its clips under the figure's graph, the
/// coat and skin slots take the person's materials, and the figure's capsule and visor step aside.
fn on_rig_ready(
    ready: On<SceneInstanceReady>,
    mut commands: Commands,
    mut roots: Query<&mut RigRoot>,
    children: Query<&Children>,
    mut players: Query<&mut AnimationPlayer>,
    names: Query<&GltfMaterialName>,
    mut materials: Query<&mut MeshMaterial3d<StandardMaterial>>,
    looks: Query<&PersonLook>,
    stand_ins: Query<(), With<StandIn>>,
    mut visibility: Query<&mut Visibility>,
) {
    let Ok(mut root) = roots.get_mut(ready.entity) else {
        return;
    };
    root.ready = true;
    for entity in children.iter_descendants(ready.entity) {
        if let Ok(mut player) = players.get_mut(entity) {
            commands.entity(entity).insert(AnimationGraphHandle(root.graph.clone()));
            for playing in &root.clips {
                player.play(playing.node).repeat();
            }
        }
        let Ok(name) = names.get(entity) else {
            continue;
        };
        let Ok(mut material) = materials.get_mut(entity) else {
            continue;
        };
        let figure_look = looks.get(root.figure).ok();
        if root.def.coat_slots.contains(&name.0) {
            if let Some(look) = figure_look {
                material.0 = look.coat.clone();
            }
        } else if root.def.skin_slots.contains(&name.0) {
            if let Some(look) = figure_look {
                material.0 = look.skin.clone();
            }
        }
    }
    let figure = root.figure;
    commands.entity(figure).insert(RigShown);
    for entity in children.iter_descendants(figure) {
        if stand_ins.contains(entity) {
            if let Ok(mut shown) = visibility.get_mut(entity) {
                *shown = Visibility::Hidden;
            }
        }
    }
}

/// Every frame, each ready rig's clips take the weights `locomotion` gives the person (eased over
/// `blend_s` of simulation time), and each is seeked to its clip time on the simulation clock.
pub fn drive_rigs(
    clock: SimClock,
    figures: Query<&Figure>,
    mut roots: Query<(Entity, &mut RigRoot)>,
    children: Query<&Children>,
    mut players: Query<&mut AnimationPlayer>,
    animations: Res<Assets<AnimationClip>>,
) {
    let now = clock.now();
    for (root_entity, mut root) in &mut roots {
        if !root.ready {
            continue;
        }
        let Ok(figure) = figures.get(root.figure) else {
            continue;
        };
        let shown = locomotion(&root.def, figure.speed_m_s(), figure.pose());
        let mut target = [0.0_f32; 6];
        let mut rate = [1.0_f32; 6];
        for weighted in &shown {
            target[index_of(weighted.clip)] = weighted.weight;
            rate[index_of(weighted.clip)] = weighted.rate;
        }
        let eased = if root.def.blend_s > 0.0 {
            ((now - root.at_s) / root.def.blend_s).clamp(0.0, 1.0)
        } else {
            1.0
        };
        root.at_s = now;
        for (weight, goal) in root.weights.iter_mut().zip(target) {
            *weight += (goal - *weight) * eased;
        }
        let weights = root.weights;
        for entity in children.iter_descendants(root_entity) {
            let Ok(mut player) = players.get_mut(entity) else {
                continue;
            };
            for clip in &root.clips {
                let index = index_of(clip.clip);
                let duration = animations.get(&clip.animation).map_or(0.0, AnimationClip::duration);
                let time = clip_time(now, figure.phase(), rate[index], duration, clip.clip.looping());
                if let Some(active) = player.animation_mut(clip.node) {
                    active.set_weight(weights[index]).set_speed(0.0).seek_to(time);
                }
            }
        }
    }
}
