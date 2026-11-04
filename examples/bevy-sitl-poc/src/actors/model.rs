//! A figure's body at run time: the humanoid glTF (if the look declares one) in place of the
//! capsule, its `person` ground-truth box, its coat tint and its clip posed on the simulation clock.

use bevy::animation::graph::{AnimationGraph, AnimationGraphHandle, AnimationNodeIndex};
use bevy::animation::{AnimationClip, AnimationPlayer};
use bevy::gltf::GltfAssetLabel;
use bevy::math::{Quat, Vec3};
use bevy::prelude::{
    AssetServer, Assets, Children, Color, Commands, Component, Entity, Handle, MeshMaterial3d, Name, On, Query, Res,
    ResMut, StandardMaterial, Transform, With, Without,
};
use bevy::scene::{SceneInstanceReady, SceneRoot};

use super::{clip_time, posed_person_truth, Figure, FigureAsset, FigureLook};
use crate::wildfire::SimClock;
use crate::world::GroundTruth;

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
        truth.0.push(posed_person_truth(&figure.id, figure.feet_enu(), def.body_m, figure.pose(), figure.yaw_deg));
        let Some(model) = &def.model else {
            continue;
        };
        // A rigged model is spawned by `rig::spawn_rigs`, which takes the capsule away once the
        // rig is on screen.
        if model.rig.is_some() {
            continue;
        }
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
