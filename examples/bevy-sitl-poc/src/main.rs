//! Browser-only disaster-flight simulation PoC.
//!
//! Bevy (WASM) renders a simplified disaster block, Rapier physics
//! flies a quadcopter in it, Feronia scatters ground debris, and a
//! stereo rig renders left/right 640x480 feeds while printing the
//! calibration the rig produces. Frames stay in this page: nothing
//! is encoded, uploaded, or sent to a backend.

mod calibration;
mod ui;

use bevy_rapier3d::prelude::*;
use bevy::camera::RenderTarget;
use bevy::prelude::*;
use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat, TextureUsages};
use bevy_feronia::asset::backend::mesh_material_backend::MeshMaterialAssetBackendPlugin;
use bevy_feronia::extension;
use bevy_feronia::prelude::*;
use calibration::StereoCalibration;
use ui::{setup_button, setup_ui, takeoff_button, update_status};

const RIG_FORWARD_M: f32 = 0.30;
const RIG_UP_M: f32 = 0.10;

#[derive(Component)]
struct Drone;

#[derive(Component)]
struct Rotor(f32);

#[derive(Component)]
struct LeftEye;

#[derive(Component)]
struct RightEye;

#[derive(Component)]
struct ChaseCam;

#[derive(Resource, Default)]
struct Flight {
    engaged: bool,
    yaw_deg: f32,
    scattered: bool,
}

fn main() {
    let rig = StereoCalibration::surmap_rig();
    App::new()
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                title: "SurMap Bevy WASM disaster simulation (PoC)".into(),
                canvas: Some("#bevy-canvas".into()),
                fit_canvas_to_parent: true,
                prevent_default_event_handling: true,
                ..default()
            }),
            ..default()
        }))
        .add_plugins(RapierPhysicsPlugin::<NoUserData>::default())
        .add_plugins(MeshMaterialAssetBackendPlugin)
        .add_plugins(ExtendedWindAffectedScatterPlugin)
        .insert_state(HeightMapState::Setup)
        .insert_state(ScatterState::Setup)
        .insert_resource(rig)
        .init_resource::<Flight>()
        .add_systems(
            Startup,
            (setup_world, setup_drone, setup_cameras, setup_ui, setup_button).chain(),
        )
        .add_systems(
            Update,
            (
                read_controls,
                takeoff_button,
                follow_drone_rig,
                chase_camera,
                spin_rotors,
                scatter_once,
                update_status,
            ),
        )
        .add_systems(FixedUpdate, apply_thrust)
        .run();
}

fn setup_drone(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let body = commands
        .spawn((
            Drone,
            RigidBody::Dynamic,
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
    let frame = commands
        .spawn((
            Mesh3d(meshes.add(Cuboid::new(0.36, 0.12, 0.36))),
            mat(&mut materials, Color::srgb(0.20, 0.22, 0.25)),
            Transform::from_xyz(0.0, 0.0, 0.0),
        ))
        .id();
    commands.entity(body).add_child(frame);
    for (i, (x, z)) in [
        (-0.24, -0.24),
        (0.24, -0.24),
        (-0.24, 0.24),
        (0.24, 0.24),
    ]
    .iter()
    .enumerate()
    {
        let rotor = commands
            .spawn((
                Rotor(if i % 2 == 0 { 28.0 } else { -28.0 }),
                Mesh3d(meshes.add(Cylinder::new(0.16, 0.015))),
                mat(&mut materials, Color::srgb(0.08, 0.08, 0.09)),
                Transform::from_xyz(*x, 0.09, *z),
            ))
            .id();
        commands.entity(body).add_child(rotor);
    }
}

fn mat(materials: &mut Assets<StandardMaterial>, color: Color) -> MeshMaterial3d<StandardMaterial> {
    MeshMaterial3d(materials.add(StandardMaterial {
        base_color: color,
        perceptual_roughness: 0.95,
        ..default()
    }))
}

fn setup_world(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    commands.spawn((
        DirectionalLight {
            illuminance: 9_000.0,
            shadows_enabled: false,
            ..default()
        },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.insert_resource(ClearColor(Color::srgb(0.45, 0.52, 0.60)));

    // Ground: dirt plane carrying both the physics floor and the
    // Feronia scatter root (wind-blown debris across the block).
    let ground_mesh = meshes.add(Cuboid::new(140.0, 0.2, 200.0));
    commands.spawn((
        Mesh3d(ground_mesh.clone()),
        mat(&mut materials, Color::srgb(0.42, 0.34, 0.24)),
        Transform::from_xyz(0.0, -0.1, -45.0),
        RigidBody::Fixed,
        Collider::cuboid(70.0, 0.1, 100.0),
        ScatterRoot::default(),
        children![(
            extension::scatter_layer("Ground debris"),
            DistributionDensity(28.),
            InstanceJitterStrength::default(),
            InstanceScaleRange::default(),
            InstanceRotationYawRange::default(),
            WindAffected,
            children![
                (
                    Name::new("Debris chunk"),
                    MeshMaterial3d(materials.add(StandardMaterial {
                        base_color: Color::srgb(0.55, 0.52, 0.48),
                        perceptual_roughness: 1.0,
                        ..default()
                    })),
                    Mesh3d(meshes.add(Cuboid::new(0.5, 0.22, 0.34))),
                    Transform::from_xyz(0., 0.12, 0.),
                ),
                (
                    Name::new("Debris chunk"),
                    LevelOfDetail(1),
                    MeshMaterial3d(materials.add(StandardMaterial {
                        base_color: Color::srgb(0.40, 0.38, 0.35),
                        perceptual_roughness: 1.0,
                        ..default()
                    })),
                    Mesh3d(meshes.add(Cuboid::new(0.5, 0.22, 0.34))),
                    Transform::from_xyz(0., 0.12, 0.),
                ),
            ]
        )],
    ));

    // Avenue along x = 0 (north = -z in Bevy) and cross street at y = 60.
    for (x, z, w, d) in [
        (0.0, -45.0, 10.0, 190.0),
        (0.0, -60.0, 110.0, 10.0),
    ] {
        commands.spawn((
            Mesh3d(meshes.add(Cuboid::new(w, 0.06, d))),
            mat(&mut materials, Color::srgb(0.16, 0.16, 0.17)),
            Transform::from_xyz(x, 0.03, z),
        ));
    }
    // Flood pond near (10, 38) ENU.
    commands.spawn((
        Mesh3d(meshes.add(Cuboid::new(32.0, 0.05, 36.0))),
        mat(&mut materials, Color::srgb(0.15, 0.30, 0.42)),
        Transform::from_xyz(10.0, 0.06, -38.0),
    ));
    // Helipad at the origin, kept clear.
    commands.spawn((
        Mesh3d(meshes.add(Cuboid::new(8.0, 0.07, 8.0))),
        mat(&mut materials, Color::srgb(0.25, 0.26, 0.27)),
        Transform::from_xyz(0.0, 0.035, 0.0),
    ));

    // Pancaked buildings and rubble: grey slabs with colliders.
    let slab = Color::srgb(0.52, 0.52, 0.50);
    let dark = Color::srgb(0.38, 0.38, 0.37);
    for (x, z, w, h, d, ry) in [
        (-16.0, -30.0, 12.0, 3.0, 10.0, 0.0),
        (-18.0, -33.0, 11.0, 0.6, 9.0, 0.12),
        (18.0, -52.0, 14.0, 5.0, 10.0, 0.0),
        (16.0, -86.0, 12.0, 3.4, 10.0, 0.0),
        (-20.0, -88.0, 10.0, 6.0, 9.0, -0.08),
        (24.0, -14.0, 9.0, 2.2, 8.0, 0.2),
        (-14.0, -8.0, 7.0, 1.4, 6.0, 0.4),
        (28.0, -70.0, 8.0, 1.8, 7.0, -0.3),
    ] {
        commands.spawn((
            Mesh3d(meshes.add(Cuboid::new(w, h, d))),
            mat(&mut materials, if h > 3.0 { slab } else { dark }),
            Transform::from_xyz(x, h / 2.0, z).with_rotation(Quat::from_rotation_y(ry)),
            RigidBody::Fixed,
            Collider::cuboid(w / 2.0, h / 2.0, d / 2.0),
        ));
    }
    // Cars at odd angles, one overturned.
    for (x, z, ry, flip) in [
        (4.0, -24.0, 0.5, 0.0),
        (-4.0, -48.0, -0.9, 0.0),
        (12.0, -40.0, 0.2, std::f32::consts::PI),
    ] {
        commands.spawn((
            Mesh3d(meshes.add(Cuboid::new(1.8, 0.55, 4.2))),
            mat(&mut materials, Color::srgb(0.55, 0.30, 0.16)),
            Transform::from_xyz(x, 0.55, z).with_rotation(
                Quat::from_rotation_y(ry) * Quat::from_rotation_x(flip),
            ),
            RigidBody::Fixed,
            Collider::cuboid(0.9, 0.275, 2.1),
        ));
    }

    // Survivors at the ground-truth ENU poses (x east, y north -> -z).
    let people = [
        (-3.5, 16.0, 0.0),
        (-5.0, 54.0, 0.0),
        (-4.0, 42.0, 2.2),
        (-14.0, 86.0, 3.4),
        (-1.0, 72.0, 0.0),
        (-2.0, 64.0, 0.0),
        (6.0, 76.0, 1.8),
    ];
    for (i, (x, north, up)) in people.iter().enumerate() {
        let coat = if i % 2 == 0 {
            Color::srgb(0.95, 0.42, 0.05)
        } else {
            Color::srgb(0.96, 0.82, 0.08)
        };
        commands.spawn((
            Mesh3d(meshes.add(Capsule3d::new(0.17, 1.05))),
            mat(&mut materials, coat),
            Transform::from_xyz(*x, up + 0.72, -*north),
        ));
        commands.spawn((
            Mesh3d(meshes.add(Sphere::new(0.13))),
            mat(&mut materials, Color::srgb(0.85, 0.65, 0.50)),
            Transform::from_xyz(*x, up + 1.62, -*north),
        ));
    }
}

fn render_target(images: &mut Assets<Image>, rig: &StereoCalibration) -> Handle<Image> {
    let mut image = Image::new_fill(
        Extent3d {
            width: rig.width,
            height: rig.height,
            depth_or_array_layers: 1,
        },
        TextureDimension::D2,
        &[24, 28, 34, 255],
        TextureFormat::Bgra8UnormSrgb,
        bevy::asset::RenderAssetUsages::default(),
    );
    image.texture_descriptor.usage =
        TextureUsages::TEXTURE_BINDING | TextureUsages::COPY_DST | TextureUsages::RENDER_ATTACHMENT;
    images.add(image)
}

fn setup_cameras(
    mut commands: Commands,
    mut images: ResMut<Assets<Image>>,
    rig: Res<StereoCalibration>,
) {
    let projection = || {
        Projection::Perspective(PerspectiveProjection {
            fov: rig.vertical_fov_rad(),
            near: 0.1,
            far: 250.0,
            ..default()
        })
    };
    commands.spawn((
        ChaseCam,
        Camera3d::default(),
        AmbientLight {
            color: Color::WHITE,
            brightness: 500.0,
            ..default()
        },
        Camera {
            order: 0,
            ..default()
        },
        projection(),
        Transform::from_xyz(6.0, 4.0, 8.0).looking_at(Vec3::new(0.0, 0.5, 0.0), Vec3::Y),
    ));
    let left_target = render_target(&mut images, &rig);
    let right_target = render_target(&mut images, &rig);
    commands.insert_resource(StereoFeeds {
        left: left_target.clone(),
        right: right_target.clone(),
    });
    commands.spawn((
        LeftEye,
        Camera3d::default(),
        Camera {
            order: 1,
            ..default()
        },
        RenderTarget::Image(left_target.into()),
        projection(),
        Transform::from_xyz(-0.035, 0.55, 0.0),
    ));
    commands.spawn((
        RightEye,
        Camera3d::default(),
        Camera {
            order: 1,
            ..default()
        },
        RenderTarget::Image(right_target.into()),
        projection(),
        Transform::from_xyz(0.035, 0.55, 0.0),
    ));
}

#[derive(Resource)]
struct StereoFeeds {
    left: Handle<Image>,
    right: Handle<Image>,
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

fn follow_drone_rig(
    drone: Query<&Transform, With<Drone>>,
    mut left: Query<&mut Transform, (With<LeftEye>, Without<Drone>, Without<RightEye>)>,
    mut right: Query<&mut Transform, (With<RightEye>, Without<Drone>, Without<LeftEye>)>,
    rig: Res<StereoCalibration>,
) {
    let Ok(body) = drone.single() else { return };
    let mount = Vec3::new(0.0, RIG_UP_M, -RIG_FORWARD_M);
    for (eye, offset) in [
        (left.single_mut(), rig.left_translation_m),
        (right.single_mut(), rig.right_translation_m),
    ] {
        let Ok(mut eye) = eye else { return };
        let local = Vec3::new(offset[0], offset[1], offset[2]) + mount;
        eye.translation = body.translation + body.rotation * local;
        eye.rotation = body.rotation;
    }
}

fn chase_camera(
    drone: Query<&Transform, With<Drone>>,
    mut cam: Query<&mut Transform, (With<ChaseCam>, Without<Drone>)>,
    time: Res<Time>,
) {
    let (Ok(body), Ok(mut eye)) = (drone.single(), cam.single_mut()) else {
        return;
    };
    let back = body.rotation * Vec3::new(5.0, 2.6, 7.5);
    let target = body.translation + back;
    let blend = 1.0 - (-3.0 * time.delta_secs()).exp();
    eye.translation = eye.translation.lerp(target, blend);
    eye.look_at(body.translation + Vec3::new(0.0, 0.3, 0.0), Vec3::Y);
}

fn spin_rotors(
    flight: Res<Flight>,
    time: Res<Time>,
    mut rotors: Query<(&Rotor, &mut Transform)>,
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

