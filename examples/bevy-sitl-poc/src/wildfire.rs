//! The scenario's weather and fires at run time: the one wind (driving Feronia, the spread model
//! and every particle), each fire's flames, embers and smoke along its perimeter, its scorched
//! ground with the glowing front, its light, and the rain around the cameras. Every look number
//! lives in the fx files (`fxdef.rs`); the geometry of the front is `fire.rs`.

use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use bevy_feronia::prelude::GlobalWind;
use bevy_hanabi::prelude::*;

use crate::fire::FireSpec;
use crate::fx::{self, Emission, WIND_PROPERTY};
use crate::fxdef::{FxAsset, FxDef, GroundDef, LightDef};
use crate::record::SimTime;
use crate::scene_manifest::{FireDef, Weather};
use crate::wind::WindModel;
use crate::world::enu;
use crate::ChaseCam;

/// Vertices of the perimeter a fire's front is sampled at.
const PERIMETER_POINTS: usize = 48;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Kind {
    Flames,
    Embers,
    Smoke,
}

#[derive(Component)]
pub struct FireEmitter;

#[derive(Component)]
pub struct RainEmitter {
    camera: Entity,
}

#[derive(Component)]
pub struct RainTagged;

/// The effect, spacing and refresh of one particle kind of one fire, once its file has loaded.
struct Layer {
    kind: Kind,
    fx: Handle<FxAsset>,
    effect: Option<Handle<EffectAsset>>,
    emitters: Vec<Entity>,
    spacing_m: f32,
    image: Option<Handle<Image>>,
}

struct FireRuntime {
    id: String,
    spec: FireSpec,
    layers: Vec<Layer>,
    next_refresh_s: f32,
    ground: Option<GroundDef>,
    light_def: Option<LightDef>,
    disk: Handle<Mesh>,
    ring: Handle<Mesh>,
    scorch: Option<(Entity, Entity)>,
    light: Option<Entity>,
}

/// The scenario's wind, its fires and its rain, once the manifest has built.
#[derive(Resource)]
pub struct Wildfire {
    pub wind: WindModel,
    fires: Vec<FireRuntime>,
    rain: Option<RainRuntime>,
}

struct RainRuntime {
    rain_mm_h: f32,
    fx: Handle<FxAsset>,
    effect: Option<Handle<EffectAsset>>,
}

impl Wildfire {
    pub fn new(
        weather: Option<&Weather>,
        fires: &[FireDef],
        assets: &AssetServer,
        meshes: &mut Assets<Mesh>,
        pending: &mut Vec<UntypedHandle>,
    ) -> Self {
        let mut load = |path: &str| -> Handle<FxAsset> {
            let handle = assets.load(path.to_owned());
            pending.push(handle.clone().untyped());
            handle
        };
        let wind = weather.map_or(
            WindModel {
                from_deg: 0.0,
                speed_m_s: 0.0,
                gust_m_s: 0.0,
            },
            |w| WindModel::from(&w.wind),
        );
        let rain = weather.filter(|w| w.rain_mm_h > 0.0).map(|w| RainRuntime {
            rain_mm_h: w.rain_mm_h,
            fx: load(&w.rain_fx),
            effect: None,
        });
        let fires = fires
            .iter()
            .map(|fire| {
                let mut layers = vec![
                    layer(Kind::Flames, load(&fire.effects.flames)),
                    layer(Kind::Embers, load(&fire.effects.embers)),
                ];
                if fire.smoke {
                    layers.push(layer(Kind::Smoke, load(&fire.effects.smoke)));
                }
                FireRuntime {
                    id: fire.id.clone(),
                    spec: FireSpec::from(fire),
                    layers,
                    next_refresh_s: f32::MIN,
                    ground: None,
                    light_def: None,
                    disk: meshes.add(empty_mesh()),
                    ring: meshes.add(empty_mesh()),
                    scorch: None,
                    light: None,
                }
            })
            .collect();
        Self { wind, fires, rain }
    }

    /// Whether any fire has burnt the ENU point `p` by `t_s`.
    pub fn burnt(&self, p: Vec2, t_s: f32) -> bool {
        let wind = self.wind.velocity_enu(t_s);
        self.fires.iter().any(|f| f.spec.burnt(p, t_s, wind))
    }

    /// Every fire's id and front at `t_s`, for the recorder.
    pub fn fronts(&self, t_s: f32) -> Vec<(String, Vec<Vec2>)> {
        let wind = self.wind.velocity_enu(t_s);
        self.fires
            .iter()
            .map(|f| (f.id.clone(), f.spec.perimeter(t_s, wind, PERIMETER_POINTS)))
            .collect()
    }

    /// Where the first fire ignites, ENU.
    pub fn first_ignition(&self) -> Option<Vec2> {
        self.fires.first().map(|f| f.spec.ignition)
    }

    pub fn has_fires(&self) -> bool {
        !self.fires.is_empty()
    }
}

fn layer(kind: Kind, fx: Handle<FxAsset>) -> Layer {
    Layer {
        kind,
        fx,
        effect: None,
        emitters: Vec::new(),
        spacing_m: 2.0,
        image: None,
    }
}

fn empty_mesh() -> Mesh {
    let mut mesh = Mesh::new(
        PrimitiveTopology::TriangleList,
        RenderAssetUsages::default(),
    );
    mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, Vec::<[f32; 3]>::new());
    mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, Vec::<[f32; 3]>::new());
    mesh.insert_indices(Indices::U32(Vec::new()));
    mesh
}

/// Bevy xz of an ENU wind velocity (m/s).
fn bevy_wind(enu_velocity: Vec2) -> Vec3 {
    Vec3::new(enu_velocity.x, 0.0, -enu_velocity.y)
}

fn sim_seconds(sim: &SimTime, time: &Time) -> f32 {
    sim.0.unwrap_or(time.elapsed_secs())
}

/// Feronia's wind follows the scenario's wind model every frame.
pub fn drive_wind(
    time: Res<Time>,
    sim: Res<SimTime>,
    scene: Option<Res<Wildfire>>,
    mut wind: ResMut<GlobalWind>,
) {
    let Some(scene) = scene else { return };
    let current = scene.wind.feronia(sim_seconds(&sim, &time));
    if wind.current != current {
        wind.current = current;
    }
}

/// Build effect assets once their files have loaded.
fn ready_effect(fx: &Assets<FxAsset>, handle: &Handle<FxAsset>) -> Option<FxDef> {
    fx.get(handle).map(|a| a.0.clone())
}

/// Per frame: place and feed every fire's particle emitters, scorched ground and light.
#[allow(clippy::too_many_arguments)]
pub fn update_fires(
    mut commands: Commands,
    time: Res<Time>,
    sim: Res<SimTime>,
    scene: Option<ResMut<Wildfire>>,
    fxs: Res<Assets<FxAsset>>,
    mut effects: ResMut<Assets<EffectAsset>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut standard: ResMut<Assets<StandardMaterial>>,
    mut images: ResMut<Assets<Image>>,
    mut discs: ResMut<fx::SoftDiscs>,
    mut emitters: Query<&mut EffectProperties, With<FireEmitter>>,
    mut transforms: Query<&mut Transform>,
    mut lights: Query<&mut PointLight>,
) {
    let Some(mut scene) = scene else { return };
    let now = sim_seconds(&sim, &time);
    let wind = scene.wind.velocity_enu(now);
    for fire in &mut scene.fires {
        for layer in &mut fire.layers {
            if layer.effect.is_none() {
                if let Some(def) = ready_effect(&fxs, &layer.fx) {
                    layer.spacing_m = def.emitter_spacing_m;
                    layer.image = (def.shape == crate::fxdef::Shape::SoftDisc)
                        .then(|| discs.handle(&mut images, def.softness));
                    let rate = rate_per_emitter(&def, layer.spacing_m);
                    let name = format!("{} {:?}", fire.id, layer.kind);
                    layer.effect = Some(effects.add(fx::effect(
                        &def,
                        &name,
                        rate,
                        Emission::Around(layer.spacing_m / 2.0),
                    )));
                    if layer.kind == Kind::Flames {
                        fire.ground = def.ground;
                        fire.light_def = def.light;
                        fire.next_refresh_s = f32::MIN;
                    }
                }
            }
        }
        let refresh_s = fire
            .layers
            .first()
            .and_then(|l| fxs.get(&l.fx))
            .map_or(0.5, |a| a.0.refresh_s);
        // A clock that ran backwards (a new still) re-places everything at once.
        if now >= fire.next_refresh_s || now + refresh_s < fire.next_refresh_s {
            refresh_fire(
                &mut commands,
                fire,
                now,
                wind,
                &mut meshes,
                &mut standard,
                &mut transforms,
                &mut lights,
            );
            fire.next_refresh_s = now + refresh_s;
        }
    }
    let wind_property = bevy_wind(wind);
    for mut properties in &mut emitters {
        properties.set(WIND_PROPERTY, wind_property.into());
    }
}

/// Particles per second one emitter spawns.
fn rate_per_emitter(def: &FxDef, spacing_m: f32) -> f32 {
    match def.spawn {
        crate::fxdef::Spawn::PerMetre(per_metre) => per_metre * spacing_m,
        crate::fxdef::Spawn::PerSecond(rate) => rate,
        crate::fxdef::Spawn::PerMmH(rate) => rate,
    }
}

/// The ENU point `fraction` (0..1) of the way round a closed polygon, by arc length.
pub fn along(points: &[Vec2], length: f32, fraction: f32) -> Vec2 {
    let mut remaining = fraction * length;
    for (a, b) in points.iter().zip(points.iter().cycle().skip(1)) {
        let edge = a.distance(*b);
        if remaining <= edge {
            return a.lerp(*b, if edge > 0.0 { remaining / edge } else { 0.0 });
        }
        remaining -= edge;
    }
    points[0]
}

fn enu_at(p: Vec2) -> Vec3 {
    enu(p.x, p.y, 0.0)
}

fn perimeter_length(points: &[Vec2]) -> f32 {
    points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .map(|(a, b)| a.distance(*b))
        .sum()
}

#[allow(clippy::too_many_arguments)]
fn refresh_fire(
    commands: &mut Commands,
    fire: &mut FireRuntime,
    now: f32,
    wind: Vec2,
    meshes: &mut Assets<Mesh>,
    standard: &mut Assets<StandardMaterial>,
    transforms: &mut Query<&mut Transform>,
    lights: &mut Query<&mut PointLight>,
) {
    let front = fire.spec.perimeter(now, wind, PERIMETER_POINTS);
    if front.len() < 3 {
        for layer in &mut fire.layers {
            for emitter in layer.emitters.drain(..) {
                commands.entity(emitter).despawn();
            }
        }
        return;
    }
    let length = perimeter_length(&front);
    for layer in &mut fire.layers {
        let Some(effect) = layer.effect.clone() else {
            continue;
        };
        let images = layer.image.clone().into_iter().collect::<Vec<_>>();
        let wanted = ((length / layer.spacing_m).ceil() as usize).max(1);
        while layer.emitters.len() > wanted {
            commands
                .entity(layer.emitters.pop().expect("non-empty"))
                .despawn();
        }
        let place =
            |index: usize| enu_at(along(&front, length, (index as f32 + 0.5) / wanted as f32));
        for (index, emitter) in layer.emitters.iter().enumerate() {
            if let Ok(mut transform) = transforms.get_mut(*emitter) {
                transform.translation = place(index);
            }
        }
        while layer.emitters.len() < wanted {
            let at = place(layer.emitters.len());
            let id = commands
                .spawn((
                    FireEmitter,
                    ParticleEffect::new(effect.clone()),
                    EffectProperties::default(),
                    EffectMaterial { images: images.clone() },
                    Transform::from_translation(at),
                ))
                .id();
            layer.emitters.push(id);
        }
    }
    let centroid = front.iter().copied().sum::<Vec2>() / front.len() as f32;
    if let Some(ground) = fire.ground {
        let (disk, ring) = scorch_meshes(&front, centroid, ground);
        if let Some(mesh) = meshes.get_mut(&fire.disk) {
            *mesh = disk;
        }
        if let Some(mesh) = meshes.get_mut(&fire.ring) {
            *mesh = ring;
        }
        if fire.scorch.is_none() {
            let [r, g, b] = ground.colour;
            let ashes = standard.add(StandardMaterial {
                base_color: Color::srgb(r, g, b),
                perceptual_roughness: ground.roughness,
                cull_mode: None,
                ..default()
            });
            let glow = Color::srgb(
                ground.glow_colour[0],
                ground.glow_colour[1],
                ground.glow_colour[2],
            )
            .to_linear();
            let rim = standard.add(StandardMaterial {
                base_color: Color::srgb(r, g, b),
                perceptual_roughness: ground.roughness,
                emissive: LinearRgba::rgb(glow.red, glow.green, glow.blue) * ground.glow_intensity,
                cull_mode: None,
                ..default()
            });
            let a = commands
                .spawn((
                    Name::new(format!("{} ashes", fire.id)),
                    Mesh3d(fire.disk.clone()),
                    MeshMaterial3d(ashes),
                    Transform::default(),
                ))
                .id();
            let b = commands
                .spawn((
                    Name::new(format!("{} front", fire.id)),
                    Mesh3d(fire.ring.clone()),
                    MeshMaterial3d(rim),
                    Transform::default(),
                ))
                .id();
            fire.scorch = Some((a, b));
        }
    }
    if let Some(light) = fire.light_def {
        let at = enu(centroid.x, centroid.y, light.height_m);
        match fire.light {
            Some(entity) => {
                if let Ok(mut transform) = transforms.get_mut(entity) {
                    transform.translation = at;
                }
                if let Ok(mut point) = lights.get_mut(entity) {
                    point.intensity = light.lumens_per_m * length;
                }
            }
            None => {
                let [r, g, b] = light.colour;
                fire.light = Some(
                    commands
                        .spawn((
                            Name::new(format!("{} glow", fire.id)),
                            PointLight {
                                color: Color::srgb(r, g, b),
                                intensity: light.lumens_per_m * length,
                                range: light.range_m,
                                shadows_enabled: false,
                                ..default()
                            },
                            Transform::from_translation(at),
                        ))
                        .id(),
                );
            }
        }
    }
}

/// The scorched disk inside the front and the glowing rim `glow_width_m` wide just inside it,
/// as flat meshes `height_m` above the ground. ENU counter-clockwise is counter-clockwise from
/// above in Bevy, so both face up.
fn scorch_meshes(front: &[Vec2], centroid: Vec2, ground: GroundDef) -> (Mesh, Mesh) {
    let inner: Vec<Vec2> = front
        .iter()
        .map(|p| {
            *p + (centroid - *p).normalize_or_zero()
                * ground.glow_width_m.min(p.distance(centroid) * 0.9)
        })
        .collect();
    let at = |p: Vec2| enu(p.x, p.y, ground.height_m).to_array();
    let mut disk = (Vec::new(), Vec::new());
    for (a, b) in inner.iter().zip(inner.iter().cycle().skip(1)) {
        let base = disk.0.len() as u32;
        disk.0.extend([at(centroid), at(*a), at(*b)]);
        disk.1.extend([base, base + 1, base + 2]);
    }
    let mut ring = (Vec::new(), Vec::new());
    for i in 0..front.len() {
        let j = (i + 1) % front.len();
        let base = ring.0.len() as u32;
        ring.0
            .extend([at(front[i]), at(front[j]), at(inner[j]), at(inner[i])]);
        ring.1
            .extend([base, base + 1, base + 3, base + 1, base + 2, base + 3]);
    }
    (flat_mesh(disk), flat_mesh(ring))
}

fn flat_mesh((positions, indices): (Vec<[f32; 3]>, Vec<u32>)) -> Mesh {
    let normals = vec![[0.0, 1.0, 0.0]; positions.len()];
    Mesh::new(
        PrimitiveTopology::TriangleList,
        RenderAssetUsages::default(),
    )
    .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
    .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
    .with_inserted_indices(Indices::U32(indices))
}

/// Rain falls in a box around each viewing camera (chase and review stills).
#[allow(clippy::type_complexity)]
pub fn rain_around_cameras(
    mut commands: Commands,
    time: Res<Time>,
    sim: Res<SimTime>,
    scene: Option<ResMut<Wildfire>>,
    fxs: Res<Assets<FxAsset>>,
    mut effects: ResMut<Assets<EffectAsset>>,
    cameras: Query<
        (Entity, &GlobalTransform),
        (
            Or<(With<ChaseCam>, With<crate::shots::OverviewCam>)>,
            Without<RainTagged>,
        ),
    >,
    mut rain: Query<(&RainEmitter, &mut Transform, &mut EffectProperties)>,
    positions: Query<&GlobalTransform, Without<RainEmitter>>,
) {
    let Some(mut scene) = scene else { return };
    let Some(runtime) = scene.rain.as_mut() else {
        return;
    };
    if runtime.effect.is_none() {
        let Some(def) = ready_effect(&fxs, &runtime.fx) else {
            return;
        };
        let side = def.box_m.unwrap_or(60.0);
        let rate = runtime.rain_mm_h * rate_per_emitter(&def, 1.0);
        runtime.effect = Some(effects.add(fx::effect(
            &def,
            "rain",
            rate,
            Emission::Box(Vec3::new(side, side / 2.0, side)),
        )));
    }
    let Some(effect) = runtime.effect.clone() else {
        return;
    };
    for (camera, at) in &cameras {
        commands.entity(camera).insert(RainTagged);
        commands.spawn((
            Name::new("Rain"),
            RainEmitter { camera },
            ParticleEffect::new(effect.clone()),
            EffectProperties::default(),
            Transform::from_translation(at.translation()),
        ));
    }
    let wind = bevy_wind(scene.wind.velocity_enu(sim_seconds(&sim, &time)));
    for (emitter, mut transform, mut properties) in &mut rain {
        if let Ok(at) = positions.get(emitter.camera) {
            transform.translation = at.translation();
        }
        properties.set(WIND_PROPERTY, wind.into());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn square() -> Vec<Vec2> {
        vec![
            Vec2::new(0.0, 0.0),
            Vec2::new(4.0, 0.0),
            Vec2::new(4.0, 4.0),
            Vec2::new(0.0, 4.0),
        ]
    }

    #[test]
    fn a_point_along_the_perimeter_walks_the_edges_by_arc_length() {
        let square = square();

        assert_eq!(along(&square, 16.0, 0.125), Vec2::new(2.0, 0.0));
        assert_eq!(along(&square, 16.0, 0.375), Vec2::new(4.0, 2.0));
    }

    #[test]
    fn a_unit_wind_east_blows_towards_bevy_plus_x() {
        assert_eq!(bevy_wind(Vec2::new(3.0, 0.0)), Vec3::new(3.0, 0.0, 0.0));
        assert_eq!(bevy_wind(Vec2::new(0.0, 3.0)), Vec3::new(0.0, 0.0, -3.0));
    }

    #[test]
    fn the_scorched_disk_and_rim_face_up() {
        let ground = GroundDef {
            height_m: 0.02,
            colour: [0.0; 3],
            roughness: 1.0,
            glow_width_m: 0.5,
            glow_colour: [1.0; 3],
            glow_intensity: 1.0,
        };
        let front = [
            Vec2::new(2.0, 0.0),
            Vec2::new(0.0, 2.0),
            Vec2::new(-2.0, 0.0),
            Vec2::new(0.0, -2.0),
        ];

        let (disk, ring) = scorch_meshes(&front, Vec2::ZERO, ground);

        for mesh in [disk, ring] {
            let positions: Vec<Vec3> = mesh
                .attribute(Mesh::ATTRIBUTE_POSITION)
                .and_then(|a| a.as_float3())
                .expect("positions")
                .iter()
                .map(|p| Vec3::from(*p))
                .collect();
            let indices: Vec<u32> = mesh
                .indices()
                .expect("indexed")
                .iter()
                .map(|i| i as u32)
                .collect();
            assert!(indices.chunks(3).all(|t| {
                let (a, b, c) = (
                    positions[t[0] as usize],
                    positions[t[1] as usize],
                    positions[t[2] as usize],
                );
                (b - a).cross(c - a).y > 0.0
            }));
        }
    }
}
