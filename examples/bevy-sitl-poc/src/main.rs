//! Disaster-flight simulation (WASM in the browser, or native).
//!
//! Bevy renders a disaster block loaded at runtime from
//! `assets/scene.json` (textures and models fetched, never compiled
//! in), Rapier physics flies a quadcopter in it, Feronia scatters
//! ground debris, and a stereo rig built from the runtime camera
//! profile renders the left/right feeds RTAB-Map receives.

mod actors;
mod behaviour;
mod building;
mod building_fire;
mod building_style;
mod calibration;
mod close_shots;
mod figure_anim;
mod fire;
mod fleet;
mod flight;
mod fx;
mod fxdef;
mod look;
mod prewarm;
mod record;
mod rig;
mod scene_manifest;
mod sea;
mod shots;
mod sky;
mod textures;
mod preview;
mod ui;
mod vehicle;
mod vegetation;
mod view_orbit;
mod wildfire;
mod wind;
#[cfg(test)]
mod realism_tests;
#[cfg(test)]
mod sweep_tests;
mod wire;
mod world;

use bevy::asset::AssetMetaCheck;
use bevy::prelude::*;
use bevy::window::WindowResolution;
use bevy::winit::{UpdateMode, WinitSettings};
use bevy_feronia::asset::backend::mesh_material_backend::MeshMaterialAssetBackendPlugin;
use bevy_feronia::prelude::*;
use bevy_rapier3d::prelude::*;
use calibration::CameraProfile;
use fleet::{viewed_body, ActiveDrone, FleetDrone, FleetRotor};
use look::{apply_look, photographic, Lens};
use shots::{fly_scripted, setup_overview, take_shots, FlightMode, RunMode};
use ui::{setup_button, setup_ui, takeoff_button, update_map_status, update_status};
use world::{build_world, resolve_models, start_loading, ManifestAsset, ManifestLoader};

#[derive(Component)]
pub(crate) struct Drone;

#[derive(Component)]
struct Rotor(f32);

#[derive(Component)]
pub(crate) struct LeftEye;

#[derive(Component)]
pub(crate) struct RightEye;

#[derive(Component)]
pub(crate) struct ChaseCam;

#[derive(Resource, Default)]
struct Flight {
    engaged: bool,
    yaw_deg: f32,
    scattered: bool,
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mode = RunMode::from_args(&args).unwrap_or_else(|e| panic!("{e}"));
    let resolution = if mode.unattended() {
        WindowResolution::new(1280, 720).with_scale_factor_override(1.0)
    } else {
        WindowResolution::default()
    };
    let interactive = !mode.unattended();
    let hidden = !mode.record.is_none();
    let look_at = shots::LookAt::from_args(&args);
    let sim_time = record::SimTime(mode.screenshot.as_ref().map(|plan| plan.at_s));
    let mut recorder = mode.record.clone().map(record::Recorder::new);
    #[cfg(target_arch = "wasm32")]
    let linked_scenario = mode.scenario.clone();
    let mut app = App::new();
    app
        .add_plugins(
            DefaultPlugins
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "SurMap Bevy disaster simulation".into(),
                        canvas: Some("#bevy-canvas".into()),
                        fit_canvas_to_parent: true,
                        prevent_default_event_handling: true,
                        resolution,
                        // A recording renders only the offscreen eyes: keep it off the desktop.
                        visible: !hidden,
                        ..default()
                    }),
                    ..default()
                })
                // No `.meta` files exist; on wasm each miss would be an HTTP 404.
                .set(AssetPlugin { meta_check: AssetMetaCheck::Never, ..default() }),
        )
        .add_plugins(RapierPhysicsPlugin::<NoUserData>::default())
        .add_plugins(MeshMaterialAssetBackendPlugin)
        .add_plugins(building::BuildingPlugin)
        .add_plugins(ExtendedWindAffectedScatterPlugin)
        .add_plugins((
            InstancedWindAffectedScatterPlugin,
            bevy_eidolon::prelude::GpuComputeCullCorePlugin,
            bevy_eidolon::prelude::GpuCullComputePlugin::<InstancedWindAffectedMaterial>::default(),
            bevy_hanabi::HanabiPlugin,
        ))
        .init_asset::<fxdef::FxAsset>()
        .init_asset_loader::<fxdef::FxLoader>()
        .init_asset::<fxdef::SpeciesAsset>()
        .init_asset_loader::<fxdef::SpeciesLoader>()
        .init_asset::<actors::FigureAsset>()
        .init_asset_loader::<actors::FigureLoader>()
        .init_asset::<vehicle::scene::VehicleAsset>()
        .init_asset_loader::<vehicle::scene::VehicleLoader>()
        .init_resource::<actors::Behaviour>()
        .init_resource::<actors::rig::Rigs>()
        .init_resource::<fx::SoftDiscs>()
        .init_resource::<prewarm::Prewarm>()
        .init_resource::<textures::RoughnessPacking>()
        .init_resource::<vegetation::PendingStands>()
        .init_resource::<vegetation::PineKits>()
        .init_asset::<ManifestAsset>()
        .init_asset_loader::<ManifestLoader>()
        .init_asset::<rig::ProfileAsset>()
        .init_asset_loader::<rig::ProfileLoader>()
        .insert_state(HeightMapState::Setup)
        .insert_state(ScatterState::Setup)
        // Unattended runs keep rendering with the window hidden or unfocused.
        .insert_resource(WinitSettings { focused_mode: UpdateMode::Continuous, unfocused_mode: UpdateMode::Continuous })
        .insert_resource(mode)
        .insert_resource(sim_time)
        .insert_resource(look_at)
        .init_resource::<Flight>()
        .init_resource::<view_orbit::ViewOrbit>()
        .add_systems(Startup, move |mut commands: Commands| {
            if let Some(recorder) = recorder.take() {
                commands.insert_resource(recorder);
            }
        })
        .add_systems(Startup, (start_loading, setup_drone, setup_cameras, setup_overview, close_shots::setup_close_shots).chain())
        .add_systems(Update, (setup_ui, setup_button).chain().run_if(move || interactive).run_if(resource_added::<StereoFeeds>))
        .add_systems(
            Update,
            (
                build_world,
                rig::spawn_rig,
                textures::generate_mips,
                resolve_models,
                read_controls,
                takeoff_button,
                fly_scripted,
                follow_drone_rig.after(fly_scripted).after(fleet::fly_fleet),
                chase_camera.after(fly_scripted).after(fleet::fly_fleet).after(view_orbit::read_trackpad),
                spin_rotors,
                scatter_once,
                update_status.after(fleet::fly_fleet),
                update_map_status,
                take_shots,
                shots::aim_overview_at_fire,
                shots::aim_people_cam,
                shots::aim_at_buildings,
                record::record_frames.after(fly_scripted).after(fleet::fly_fleet).after(actors::tick_behaviours),
                apply_look,
                sky::bake_sky,
            ),
        )
        .add_systems(Update, view_orbit::read_trackpad)
        .add_systems(
            Update,
            (
                actors::tick_behaviours,
                wildfire::drive_wind,
                (vegetation::sync_vegetation_wind, vegetation::grow_stands, vegetation::scatter_stands.run_if(in_state(ScatterState::Ready)), vegetation::show_grass, vegetation::burn_vegetation),
                wildfire::update_fires,
                wildfire::rain_around_cameras,
                actors::animate_figures,
                actors::attach_bodies,
                actors::pose_figures,
                actors::attach_visors,
                vehicle::scene::attach_vehicles,
                vehicle::scene::tint_vehicles,
                vehicle::scene::spin_wheels,
                vehicle::scene::place_vehicles,
                actors::rig::prepare_rigs,
                actors::rig::spawn_rigs,
                actors::rig::drive_rigs,
            )
                .chain()
                .after(build_world),
        )
        .add_systems(
            Update,
            (fleet::spawn_fleet, fleet::fly_fleet, fleet::spin_fleet_rotors).chain().after(build_world),
        )
        .add_systems(
            Update,
            (prewarm::prewarm_effects.before(take_shots), close_shots::aim_flame_close, close_shots::aim_person_close),
        )
        .add_systems(FixedUpdate, apply_thrust);
    // The station link, only on a page opened with `?fleet=1` for a scenario.
    #[cfg(target_arch = "wasm32")]
    if let (true, Some(scenario)) = (fleet::link_wasm::page_fleet_enabled(), linked_scenario.clone()) {
        app.add_plugins(fleet::link_wasm::FleetLinkPlugin { scenario });
    }
    // The stereo stream, only on a page opened with `?bridge=ws://…`.
    #[cfg(target_arch = "wasm32")]
    if let Some(url) = fleet::bridge_wasm::page_bridge_url() {
        app.add_plugins(fleet::bridge_wasm::BridgeStreamPlugin { url, scenario: linked_scenario });
    }
    let exit = app.run();
    if exit.is_error() {
        std::process::exit(1);
    }
}

fn setup_drone(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mode: Res<RunMode>,
) {
    let body_kind = match mode.flight {
        FlightMode::Manual => RigidBody::Dynamic,
        FlightMode::SurveyLoop => RigidBody::KinematicPositionBased,
    };
    let body = commands
        .spawn((
            Drone,
            body_kind,
            Collider::cuboid(0.18, 0.08, 0.18),
            AdditionalMassProperties::Mass(1.2),
            LockedAxes::ROTATION_LOCKED_X | LockedAxes::ROTATION_LOCKED_Z,
            Damping {
                linear_damping: 0.4,
                angular_damping: 2.0,
            },
            Velocity::zero(),
            ExternalForce::default(),
            Transform::from_xyz(0.0, 0.45, 0.0),
            Visibility::default(),
        ))
        .id();
    attach_drone_parts(&mut commands, &mut meshes, &mut materials, body);
}

/// The drone's frame and four rotors, as children of `body`; the rotors' entities.
pub(crate) fn attach_drone_parts(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    body: Entity,
) -> Vec<Entity> {
    let frame = commands
        .spawn((
            Mesh3d(meshes.add(Cuboid::new(0.36, 0.12, 0.36))),
            mat(materials, Color::srgb(0.20, 0.22, 0.25)),
            Transform::from_xyz(0.0, 0.0, 0.0),
        ))
        .id();
    commands.entity(body).add_child(frame);
    [(-0.24, -0.24), (0.24, -0.24), (-0.24, 0.24), (0.24, 0.24)]
        .iter()
        .enumerate()
        .map(|(i, (x, z))| {
            let rotor = commands
                .spawn((
                    Rotor(if i % 2 == 0 { 28.0 } else { -28.0 }),
                    Mesh3d(meshes.add(Cylinder::new(0.16, 0.015))),
                    mat(materials, Color::srgb(0.08, 0.08, 0.09)),
                    Transform::from_xyz(*x, 0.09, *z),
                ))
                .id();
            commands.entity(body).add_child(rotor);
            rotor
        })
        .collect()
}

fn mat(materials: &mut Assets<StandardMaterial>, color: Color) -> MeshMaterial3d<StandardMaterial> {
    MeshMaterial3d(materials.add(StandardMaterial {
        base_color: color,
        perceptual_roughness: 0.95,
        ..default()
    }))
}

/// The chase view at startup; the eyes follow once the camera profile loads (`rig.rs`).
fn setup_cameras(mut commands: Commands) {
    let mut chase = commands.spawn((
        ChaseCam,
        Camera {
            order: 0,
            ..default()
        },
        Projection::Perspective(PerspectiveProjection {
            fov: 60f32.to_radians(),
            near: 0.1,
            far: 600.0,
            ..default()
        }),
        Transform::from_xyz(6.0, 4.0, 8.0).looking_at(Vec3::new(0.0, 0.5, 0.0), Vec3::Y),
    ));
    photographic(&mut chase, Lens::Chase);
}

#[derive(Resource)]
pub(crate) struct StereoFeeds {
    pub(crate) left: Handle<Image>,
    pub(crate) right: Handle<Image>,
}

fn read_controls(
    keys: Res<ButtonInput<KeyCode>>,
    mut flight: ResMut<Flight>,
    mut drone: Query<&mut Transform, With<Drone>>,
) {
    if keys.just_pressed(KeyCode::Space) {
        flight.engaged = !flight.engaged;
    }
    let mut yaw = 0.0;
    if keys.pressed(KeyCode::KeyQ) {
        yaw += 1.0;
    }
    if keys.pressed(KeyCode::KeyE) {
        yaw -= 1.0;
    }
    if yaw != 0.0 {
        flight.yaw_deg = (flight.yaw_deg + yaw * 1.2).rem_euclid(360.0);
        if let Ok(mut transform) = drone.single_mut() {
            transform.rotation = Quat::from_rotation_y(flight.yaw_deg.to_radians());
        }
    }
}

fn apply_thrust(
    keys: Res<ButtonInput<KeyCode>>,
    flight: Res<Flight>,
    mut drone: Query<&mut ExternalForce, With<Drone>>,
) {
    for mut force in &mut drone {
        if !flight.engaged {
            force.force = Vec3::ZERO;
            continue;
        }
        // Hover thrust plus pilot accel, in the drone's yaw frame.
        let yaw = Quat::from_rotation_y(flight.yaw_deg.to_radians());
        let mut accel = Vec3::new(0.0, 9.81, 0.0);
        let mut local = Vec3::ZERO;
        if keys.pressed(KeyCode::KeyW) {
            local.z -= 3.0;
        }
        if keys.pressed(KeyCode::KeyS) {
            local.z += 3.0;
        }
        if keys.pressed(KeyCode::KeyA) {
            local.x -= 3.0;
        }
        if keys.pressed(KeyCode::KeyD) {
            local.x += 3.0;
        }
        if keys.pressed(KeyCode::KeyR) {
            local.y += 2.5;
        }
        if keys.pressed(KeyCode::KeyF) {
            local.y -= 2.5;
        }
        accel += yaw * local;
        force.force = accel * 1.2;
    }
}

/// The eyes: not on any drone's body.
type Eye<T> = (With<T>, Without<Drone>, Without<FleetDrone>);

fn follow_drone_rig(
    drone: Query<&Transform, With<Drone>>,
    fleet: Query<(&FleetDrone, &Transform)>,
    active: Option<Res<ActiveDrone>>,
    mut left: Query<&mut Transform, (Eye<LeftEye>, Without<RightEye>)>,
    mut right: Query<&mut Transform, (Eye<RightEye>, Without<LeftEye>)>,
    rig: Option<Res<CameraProfile>>,
) {
    let viewed = viewed_body(active.as_ref().and_then(|a| a.0.as_deref()), fleet.iter(), drone.single().ok());
    let (Some(body), Some(rig)) = (viewed, rig) else { return };
    for (eye, right_eye) in [(left.single_mut(), false), (right.single_mut(), true)] {
        let Ok(mut eye) = eye else { return };
        let local = rig.mount_offset() + rig.mount_rotation() * rig.eye_translation_m(right_eye);
        eye.translation = body.translation + body.rotation * local;
        eye.rotation = body.rotation * rig.mount_rotation();
    }
}

fn chase_camera(
    drone: Query<&Transform, With<Drone>>,
    fleet: Query<(&FleetDrone, &Transform)>,
    active: Option<Res<ActiveDrone>>,
    mut cam: Query<&mut Transform, (With<ChaseCam>, Without<Drone>, Without<FleetDrone>)>,
    time: Res<Time>,
    mode: Res<RunMode>,
    orbit: Res<view_orbit::ViewOrbit>,
) {
    let viewed = viewed_body(active.as_ref().and_then(|a| a.0.as_deref()), fleet.iter(), drone.single().ok());
    let (Some(body), Ok(mut eye)) = (viewed, cam.single_mut()) else {
        return;
    };
    let target = body.translation + orbit.offset(body.rotation);
    let blend = if mode.screenshot.is_some() { 1.0 } else { 1.0 - (-3.0 * time.delta_secs()).exp() };
    eye.translation = eye.translation.lerp(target, blend);
    eye.look_at(body.translation + Vec3::new(0.0, 0.3, 0.0), Vec3::Y);
}

fn spin_rotors(
    flight: Res<Flight>,
    time: Res<Time>,
    mut rotors: Query<(&Rotor, &mut Transform), Without<FleetRotor>>,
) {
    if !flight.engaged {
        return;
    }
    for (rotor, mut transform) in &mut rotors {
        transform.rotate_y(rotor.0 * time.delta_secs());
    }
}

fn scatter_once(
    mut commands: Commands,
    mut flight: ResMut<Flight>,
    root: Query<Entity, With<ScatterRoot>>,
) {
    if flight.scattered {
        return;
    }
    if let Ok(entity) = root.single() {
        commands.trigger(Scatter::<ExtendedWindAffectedMaterial>::new(entity));
        flight.scattered = true;
    }
}

