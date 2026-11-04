//! The renderer's side of vehicles (docs/simulation/bevy-simulation.md § *Vehicles*). Each class
//! file loads through Bevy; a vehicle's root entity is moved by its `Drive` at the fixed tick, its
//! class's glTF hangs under it with its wheels turning, and a train's carriages trail it along the
//! path it travelled. The motion itself is pure (`vehicle.rs`); this module only puts it on screen.

use bevy::asset::io::Reader;
use bevy::asset::{Asset, AssetLoader, LoadContext};
use bevy::camera::primitives::MeshAabb;
use bevy::prelude::*;
use bevy::reflect::TypePath;

use super::{wheel_angle, VehicleBody, VehicleClass, VehicleDef};
use crate::actors::{bevy_yaw, Body};
use crate::scene_manifest::Vehicle;
use crate::world::{enu, SceneState};

/// A class file (`assets/vehicle/<class>.vehicle.json`), as loaded.
#[derive(Asset, TypePath, Debug)]
pub struct VehicleAsset(pub VehicleDef);

#[derive(Default, TypePath)]
pub struct VehicleLoader;

impl AssetLoader for VehicleLoader {
    type Asset = VehicleAsset;
    type Settings = ();
    type Error = std::io::Error;

    async fn load(&self, reader: &mut dyn Reader, _: &(), _: &mut LoadContext<'_>) -> Result<VehicleAsset, std::io::Error> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes).await?;
        let text = String::from_utf8(bytes).map_err(std::io::Error::other)?;
        VehicleDef::from_json(&text).map(VehicleAsset).map_err(std::io::Error::other)
    }

    fn extensions(&self) -> &[&str] {
        &["vehicle.json"]
    }
}

/// The four class files, loaded at start; a vehicle reads its class's look and limits here.
#[derive(Resource)]
pub struct VehicleClasses(Vec<(VehicleClass, Handle<VehicleAsset>)>);

impl VehicleClasses {
    pub fn load(assets: &AssetServer) -> Self {
        let classes = [VehicleClass::Car, VehicleClass::Bus, VehicleClass::Truck, VehicleClass::Train];
        Self(classes.into_iter().map(|class| (class, assets.load(class.file()))).collect())
    }

    /// Every class file's handle, for the scene to wait on.
    pub fn handles(&self) -> impl Iterator<Item = UntypedHandle> + '_ {
        self.0.iter().map(|(_, handle)| handle.clone().untyped())
    }

    /// A class's definition, once its file has loaded.
    pub fn def<'a>(&self, class: VehicleClass, defs: &'a Assets<VehicleAsset>) -> Option<&'a VehicleDef> {
        let (_, handle) = self.0.iter().find(|(c, _)| *c == class)?;
        defs.get(handle).map(|asset| &asset.0)
    }
}

/// A vehicle on its root entity: its tree and motion, ticked with the people at the fixed rate.
#[derive(Component)]
pub struct VehicleActor {
    pub id: String,
    pub class: VehicleClass,
    pub body: VehicleBody,
    pub ground_z: f32,
    pub cars: u32,
    pub glb: Option<String>,
    pub tint: Option<[f32; 3]>,
    pub tracked: bool,
    attached: bool,
}

impl VehicleActor {
    /// The vehicle at its element's start pose, driven by its tree.
    pub fn new(element: &Vehicle) -> Self {
        let [x, y, z] = element.position_enu;
        Self {
            id: element.id.clone(),
            class: element.class,
            body: VehicleBody::new(element.behaviour.clone(), Vec2::new(x, y), element.yaw_deg.to_radians()),
            ground_z: z,
            cars: element.cars,
            glb: element.glb.clone(),
            tint: element.tint,
            tracked: element.ground_truth,
            attached: false,
        }
    }

    /// The vehicle as a moving body in a track frame; `None` when it is not tracked.
    pub fn body(&self) -> Option<Body> {
        let drive = &self.body.drive;
        self.tracked.then(|| Body {
            id: self.id.clone(),
            enu: Vec3::new(drive.position.x, drive.position.y, self.ground_z),
            action: self.body.runner.as_ref().and_then(|runner| runner.action()).map(str::to_owned),
            kind: self.class.kind().to_owned(),
            yaw_deg: drive.heading_rad.to_degrees(),
            pose: None,
        })
    }
}

/// A train's carriage: placed each frame at its pose along the path its locomotive travelled.
#[derive(Component)]
pub struct Carriage {
    pub vehicle: Entity,
    /// 1 for the carriage behind the locomotive, and so on.
    pub index: u32,
}

/// A wheel node of a vehicle's model: its rest pose, its axle's centre, and its vehicle.
#[derive(Component)]
pub struct Wheel {
    rest: Transform,
    pivot: Vec3,
    vehicle: Entity,
}

/// A vehicle whose body has been tinted.
#[derive(Component)]
pub struct Tinted;

/// Each vehicle's root follows its drive, and each carriage follows the travelled path.
pub fn place_vehicles(
    classes: Option<Res<VehicleClasses>>,
    defs: Res<Assets<VehicleAsset>>,
    actors: Query<&VehicleActor>,
    mut vehicles: Query<(&VehicleActor, &mut Transform), Without<Carriage>>,
    mut carriages: Query<(&Carriage, &mut Transform), Without<VehicleActor>>,
) {
    let Some(classes) = classes else { return };
    for (actor, mut transform) in &mut vehicles {
        let drive = &actor.body.drive;
        *transform = Transform::from_translation(enu(drive.position.x, drive.position.y, actor.ground_z))
            .with_rotation(Quat::from_rotation_y(bevy_yaw(Vec2::from_angle(drive.heading_rad))));
    }
    for (carriage, mut transform) in &mut carriages {
        let Ok(actor) = actors.get(carriage.vehicle) else { continue };
        let Some(spacing) = classes.def(actor.class, &defs).and_then(|def| def.carriage_spacing_m) else { continue };
        let poses = actor.body.drive.carriage_poses(actor.cars, spacing);
        let Some(&(at, heading)) = poses.get(carriage.index as usize - 1) else { continue };
        *transform = Transform::from_translation(enu(at.x, at.y, actor.ground_z))
            .with_rotation(Quat::from_rotation_y(bevy_yaw(Vec2::from_angle(heading))));
    }
}

/// Once a class file has loaded, a vehicle hangs its glTF under its root, turned so the nose
/// points along its forward, and a train spawns its carriages behind the locomotive.
pub fn attach_vehicles(
    mut commands: Commands,
    assets: Res<AssetServer>,
    classes: Option<Res<VehicleClasses>>,
    defs: Res<Assets<VehicleAsset>>,
    mut state: Option<ResMut<SceneState>>,
    mut vehicles: Query<(Entity, &mut VehicleActor)>,
) {
    let Some(classes) = classes else { return };
    for (root, mut actor) in &mut vehicles {
        if actor.attached {
            continue;
        }
        let Some(def) = classes.def(actor.class, &defs) else { continue };
        actor.attached = true;
        let turn = Quat::from_rotation_y(def.model_yaw_deg.to_radians());
        // The class's model, and its carriages, are authored at the same scale.
        let pose = Transform::from_rotation(turn).with_scale(Vec3::splat(def.model_scale));
        let glb = actor.glb.clone().unwrap_or_else(|| def.glb.clone());
        let model: Handle<Scene> = assets.load(GltfAssetLabel::Scene(0).from_asset(glb));
        if let Some(state) = state.as_mut() {
            state.pending.push(model.clone().untyped());
        }
        commands.entity(root).with_child((SceneRoot(model), pose));
        let (Some(carriage_glb), Some(_)) = (def.carriage_glb.clone(), def.carriage_spacing_m) else { continue };
        for index in 1..=actor.cars {
            let scene: Handle<Scene> = assets.load(GltfAssetLabel::Scene(0).from_asset(carriage_glb.clone()));
            if let Some(state) = state.as_mut() {
                state.pending.push(scene.clone().untyped());
            }
            commands
                .spawn((Carriage { vehicle: root, index }, Transform::default(), Visibility::default()))
                .with_child((SceneRoot(scene), pose));
        }
    }
}

/// Each wheel node (a glTF node whose name starts with a `wheel_nodes` prefix) turns by the distance
/// its vehicle has rolled, about its own axle through its mesh's centre.
pub fn spin_wheels(
    mut commands: Commands,
    classes: Option<Res<VehicleClasses>>,
    defs: Res<Assets<VehicleAsset>>,
    meshes: Res<Assets<Mesh>>,
    vehicles: Query<(Entity, &VehicleActor)>,
    actors: Query<&VehicleActor>,
    children: Query<&Children>,
    named: Query<(&Name, Option<&Mesh3d>, &Transform), Without<Wheel>>,
    mut wheels: Query<(&Wheel, &mut Transform)>,
) {
    let Some(classes) = classes else { return };
    for (root, actor) in &vehicles {
        let Some(def) = classes.def(actor.class, &defs) else { continue };
        if def.wheel_nodes.is_empty() || !actor.attached {
            continue;
        }
        for node in children.iter_descendants(root) {
            let Ok((name, mesh, rest)) = named.get(node) else { continue };
            if !def.wheel_nodes.iter().any(|prefix| name.as_str().starts_with(prefix.as_str())) {
                continue;
            }
            let Some(aabb) = mesh.and_then(|mesh| meshes.get(&mesh.0)).and_then(|mesh| mesh.compute_aabb()) else {
                continue;
            };
            commands
                .entity(node)
                .insert(Wheel { rest: *rest, pivot: Vec3::from(aabb.center), vehicle: root });
        }
    }
    for (wheel, mut transform) in &mut wheels {
        let Ok(actor) = actors.get(wheel.vehicle) else { continue };
        let Some(radius) = classes.def(actor.class, &defs).and_then(|def| def.wheel_radius_m) else { continue };
        let turn = Quat::from_rotation_x(wheel_angle(actor.body.drive.odometer_m, radius));
        *transform = about_axle(wheel.rest, wheel.pivot, turn);
    }
}

/// `rest` turned by `turn` about `pivot` (in the node's own frame), so the wheel rolls in place.
fn about_axle(rest: Transform, pivot: Vec3, turn: Quat) -> Transform {
    Transform {
        translation: rest.translation + rest.rotation * (rest.scale * (pivot - turn * pivot)),
        rotation: rest.rotation * turn,
        scale: rest.scale,
    }
}

/// A vehicle with a `tint` multiplies its glTF's base colours, once its materials have loaded.
pub fn tint_vehicles(
    mut commands: Commands,
    mut materials: ResMut<Assets<StandardMaterial>>,
    vehicles: Query<(Entity, &VehicleActor), Without<Tinted>>,
    children: Query<&Children>,
    painted: Query<&MeshMaterial3d<StandardMaterial>>,
) {
    for (root, actor) in &vehicles {
        let Some(tint) = actor.tint.filter(|_| actor.attached) else { continue };
        let parts: Vec<(Entity, Handle<StandardMaterial>)> = children
            .iter_descendants(root)
            .filter_map(|node| painted.get(node).ok().map(|m| (node, m.0.clone())))
            .collect();
        let loaded: Vec<(Entity, StandardMaterial)> = parts
            .iter()
            .filter_map(|(node, handle)| materials.get(handle).map(|material| (*node, material.clone())))
            .collect();
        if parts.is_empty() || loaded.len() != parts.len() {
            continue;
        }
        for (node, mut material) in loaded {
            let base = material.base_color.to_srgba();
            material.base_color = Color::srgba(base.red * tint[0], base.green * tint[1], base.blue * tint[2], base.alpha);
            commands.entity(node).insert(MeshMaterial3d(materials.add(material)));
        }
        commands.entity(root).insert(Tinted);
    }
}
