//! A burning building on screen: broken panes, interior glow, charred wall bands and soot on each
//! floor, flames at its windows, smoke from the top burning floor and the roof, embers, and one
//! light. The state is `BuildingFires` (stepped with the behaviour clock); this only draws it.

use bevy::ecs::system::SystemParam;
use bevy::prelude::*;
use bevy_hanabi::prelude::*;

use super::look::BuildingLook;
use super::spawn::BuildingView;
use crate::building_fire::{BuildingFires, FloorState};
use crate::fx::{self, Emission, SoftDiscs};
use crate::fxdef::{FxAsset, FxDef, Shape, Spawn};
use crate::wildfire::FireEmitter;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Flames,
    Smoke,
    Embers,
}

/// One particle kind: its file, and its effect once the file has loaded.
pub struct Layer {
    pub kind: Kind,
    pub fx: Handle<FxAsset>,
    effect: Option<Handle<EffectAsset>>,
    spacing_m: f32,
    image: Option<Handle<Image>>,
}

impl Layer {
    pub fn new(kind: Kind, fx: Handle<FxAsset>) -> Self {
        Self {
            kind,
            fx,
            effect: None,
            spacing_m: 2.0,
            image: None,
        }
    }
}

/// The buildings that can burn, their fire and how they look doing it.
#[derive(Resource)]
pub struct BuildingBlaze {
    pub fires: BuildingFires,
    pub views: Vec<BuildingView>,
    pub look: BuildingLook,
    pub layers: Vec<Layer>,
    /// The buildings the manifest lights, in order: (id, floor).
    pub declared: Vec<(String, u32)>,
}

impl BuildingBlaze {
    /// The first declared fire's building: its ENU centre, its height and the ignition floor's
    /// middle height (for aiming a review still).
    pub fn first_fire(&self) -> Option<(Vec2, f32, f32)> {
        let (id, floor) = self.declared.first()?;
        let view = self.views.iter().find(|v| &v.id == id)?;
        let footprint = self.fires.buildings().iter().find(|b| &b.id == id)?;
        let centre = footprint.polygon_enu.iter().copied().sum::<Vec2>()
            / footprint.polygon_enu.len() as f32;
        let floor_m = view.size.y / view.floors.len() as f32;
        Some((centre, view.size.y, (*floor as f32 + 0.5) * floor_m))
    }

    /// One `building_fires.jsonl` line: every building with a floor alight or burnt out.
    pub fn record_line(&self, t_ns: u64) -> String {
        let buildings: Vec<serde_json::Value> = self
            .views
            .iter()
            .filter_map(|view| {
                let (burning, burnt) = self.fires.burning_and_burnt(&view.id);
                (!burning.is_empty() || !burnt.is_empty())
                    .then(|| serde_json::json!({"id": view.id, "burning": burning, "burnt": burnt}))
            })
            .collect();
        serde_json::json!({"t_ns": t_ns, "buildings": buildings}).to_string()
    }
}

/// The effect files and the particle effects built from them.
#[derive(SystemParam)]
pub struct BlazeEffects<'w> {
    fxs: Res<'w, Assets<FxAsset>>,
    effects: ResMut<'w, Assets<EffectAsset>>,
    images: ResMut<'w, Assets<Image>>,
    discs: ResMut<'w, SoftDiscs>,
}

fn rate_per_emitter(def: &FxDef, spacing_m: f32) -> f32 {
    match def.spawn {
        Spawn::PerMetre(per_metre) => per_metre * spacing_m,
        Spawn::PerSecond(rate) | Spawn::PerMmH(rate) => rate,
    }
}

impl BlazeEffects<'_> {
    /// Build each layer's effect once its file has loaded; true when all are ready.
    fn ready(&mut self, layers: &mut [Layer]) -> bool {
        for layer in layers.iter_mut().filter(|l| l.effect.is_none()) {
            let Some(def) = self.fxs.get(&layer.fx).map(|a| a.0.clone()) else {
                continue;
            };
            layer.spacing_m = def.emitter_spacing_m;
            layer.image = (def.shape == Shape::SoftDisc)
                .then(|| self.discs.handle(&mut self.images, def.softness));
            let radius = def.emit_radius_m.unwrap_or(layer.spacing_m / 2.0);
            let rate = rate_per_emitter(&def, layer.spacing_m);
            let name = format!(
                "building {}",
                layer.fx.path().map_or_else(String::new, |p| p.to_string())
            );
            layer.effect =
                Some(
                    self.effects
                        .add(fx::effect(&def, &name, rate, Emission::Around(radius))),
                );
        }
        layers.iter().all(|l| l.effect.is_some())
    }
}

/// Points around a `size.x` × `size.z` rectangle centred on the origin at height `y`, `spacing_m` apart.
fn ring(size: Vec3, y: f32, spacing_m: f32) -> Vec<Vec3> {
    let (a, b) = (size.x / 2.0, size.z / 2.0);
    let corners = [
        Vec3::new(-a, y, -b),
        Vec3::new(a, y, -b),
        Vec3::new(a, y, b),
        Vec3::new(-a, y, b),
    ];
    let mut points = Vec::new();
    for (from, to) in corners.iter().zip(corners.iter().cycle().skip(1)) {
        let pieces = ((from.distance(*to) / spacing_m).ceil() as usize).max(1);
        points.extend((0..pieces).map(|i| from.lerp(*to, i as f32 / pieces as f32)));
    }
    points
}

/// Points over the roof, `spacing_m` apart.
fn roof_points(size: Vec3, y: f32, spacing_m: f32) -> Vec<Vec3> {
    let columns = ((size.x / spacing_m).floor() as i32).max(1);
    let rows = ((size.z / spacing_m).floor() as i32).max(1);
    let at = |i: i32, n: i32, extent: f32| (i as f32 + 0.5) / n as f32 * extent - extent / 2.0;
    (0..columns)
        .flat_map(|i| {
            (0..rows).map(move |j| Vec3::new(at(i, columns, size.x), y, at(j, rows, size.z)))
        })
        .collect()
}

fn spawn_emitters(
    commands: &mut Commands,
    view: &mut BuildingView,
    layers: &[Layer],
    burning: &[u32],
) {
    for emitter in view.emitters.drain(..) {
        commands.entity(emitter).despawn();
    }
    let Some(&top) = burning.last() else { return };
    let floor_m = view.size.y / view.floors.len() as f32;
    for layer in layers {
        let Some(effect) = layer.effect.clone() else {
            continue;
        };
        let local: Vec<Vec3> = match layer.kind {
            Kind::Flames => burning
                .iter()
                .flat_map(|f| {
                    let openings = &view.floors[*f as usize].openings;
                    let width = openings.first().map_or(1.0, |o| o.width_m);
                    let stride = ((layer.spacing_m / width).round() as usize).max(1);
                    openings
                        .iter()
                        .step_by(stride)
                        .map(|o| o.at)
                        .collect::<Vec<_>>()
                })
                .collect(),
            Kind::Smoke => {
                let mut points = ring(view.size, (top + 1) as f32 * floor_m, layer.spacing_m);
                points.extend(roof_points(view.size, view.roof_top_m, layer.spacing_m));
                points
            }
            Kind::Embers => ring(view.size, (top + 1) as f32 * floor_m, layer.spacing_m),
        };
        let images: Vec<Handle<Image>> = layer.image.clone().into_iter().collect();
        for point in local {
            let id = commands
                .spawn((
                    FireEmitter,
                    ParticleEffect::new(effect.clone()),
                    EffectProperties::default(),
                    EffectMaterial {
                        images: images.clone(),
                    },
                    Transform::from_translation(view.pose.transform_point(point)),
                ))
                .id();
            view.emitters.push(id);
        }
    }
}

/// Per frame: bring each building's floors, emitters and light to the fire's current state.
pub fn update_building_fires(
    mut commands: Commands,
    blaze: Option<ResMut<BuildingBlaze>>,
    mut effects: BlazeEffects,
) {
    let Some(mut blaze) = blaze else { return };
    let blaze = &mut *blaze;
    let ready = effects.ready(&mut blaze.layers);
    if !ready {
        return;
    }
    for view in &mut blaze.views {
        let state = blaze.fires.burning_and_burnt(&view.id);
        if state == view.shown {
            continue;
        }
        let (burning, burnt) = &state;
        if view.shown.0.is_empty() && view.shown.1.is_empty() {
            info!(
                "{} caught fire at {:.1} s",
                view.id,
                blaze.fires.ignited_at(&view.id).unwrap_or_default()
            );
        }
        for (index, floor) in view.floors.iter().enumerate() {
            let floor_state = blaze.fires.floor(&view.id, index as u32);
            let on = |entity: Option<Entity>, show: bool, commands: &mut Commands| {
                if let Some(entity) = entity {
                    commands.entity(entity).insert(if show {
                        Visibility::Inherited
                    } else {
                        Visibility::Hidden
                    });
                }
            };
            on(
                floor.panes,
                floor_state == FloorState::Intact,
                &mut commands,
            );
            on(
                floor.glow,
                floor_state == FloorState::Burning,
                &mut commands,
            );
            on(floor.soot, floor_state != FloorState::Intact, &mut commands);
            let wall = if floor_state == FloorState::Intact {
                view.materials.wall.clone()
            } else {
                view.materials.burnt_wall.clone()
            };
            commands.entity(floor.wall).insert(MeshMaterial3d(wall));
        }
        let roof = if burnt.len() == view.floors.len() {
            view.materials.burnt_roof.clone()
        } else {
            view.materials.roof.clone()
        };
        commands.entity(view.roof).insert(MeshMaterial3d(roof));
        spawn_emitters(&mut commands, view, &blaze.layers, burning);
        if let Some(light) = view.light.take() {
            commands.entity(light).despawn();
        }
        if let Some(&top) = burning.last() {
            let floor_m = view.size.y / view.floors.len() as f32;
            let look = blaze.look.fire.light;
            view.light = Some(
                commands
                    .spawn((
                        Name::new(format!("{} fire light", view.id)),
                        PointLight {
                            color: Color::srgb(look.colour[0], look.colour[1], look.colour[2]),
                            intensity: look.lumens_per_floor * burning.len() as f32,
                            range: look.range_m,
                            shadows_enabled: false,
                            ..default()
                        },
                        Transform::from_translation(view.pose.transform_point(Vec3::new(
                            0.0,
                            (top as f32 + 0.5) * floor_m,
                            0.0,
                        ))),
                    ))
                    .id(),
            );
        }
        view.shown = state;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_ring_walks_the_walls_at_the_given_spacing() {
        let points = ring(Vec3::new(8.0, 10.0, 4.0), 5.0, 2.0);

        assert_eq!(points.len(), 4 + 2 + 4 + 2);
        assert!(points.iter().all(|p| p.y == 5.0));
    }

    #[test]
    fn roof_points_cover_the_roof_evenly() {
        let points = roof_points(Vec3::new(8.0, 10.0, 8.0), 10.0, 4.0);

        assert_eq!(points.len(), 4);
        assert!(points.iter().all(|p| p.x.abs() <= 4.0 && p.z.abs() <= 4.0));
    }
}
