//! Close verification stills (screenshot mode): the survey-range stills cannot show a flame
//! sprite or a visor, so these two stand a few metres from the thing they check.

use bevy::camera::RenderTarget;
use bevy::prelude::*;

use crate::actors::Figure;
use crate::look::{photographic, Lens};
use crate::shots::{shot_target, RunMode, Shots};
use crate::wildfire::{SimClock, Wildfire};
use crate::world::enu;

/// The flame still: the eye this far outside the front (south of its southernmost point), its
/// altitude, and the height of the point it looks at.
const FLAME_EYE_OUTSIDE_M: f32 = 8.0;
const FLAME_EYE_ALTITUDE_M: f32 = 2.0;
const FLAME_LOOK_AT_M: f32 = 1.0;
/// The person still: the eye this far in front of the first figure, its altitude, and the height
/// of the head it looks at.
const PERSON_EYE_AHEAD_M: f32 = 4.0;
const PERSON_EYE_ALTITUDE_M: f32 = 1.6;
const PERSON_LOOK_AT_M: f32 = 1.62;

#[derive(Component)]
pub struct FlameCloseCam;

#[derive(Component)]
pub struct PersonCloseCam;

fn camera(commands: &mut Commands, target: Handle<Image>) -> Entity {
    let mut spawned = commands.spawn((
        Camera3d::default(),
        Camera {
            order: 2,
            ..default()
        },
        RenderTarget::Image(target.into()),
        Projection::Perspective(PerspectiveProjection {
            fov: 50f32.to_radians(),
            near: 0.05,
            far: 600.0,
            ..default()
        }),
        Transform::default(),
    ));
    photographic(&mut spawned, Lens::Still);
    spawned.id()
}

/// Both close cameras and their image targets, kept on `Shots`.
pub fn setup_close_shots(
    mut commands: Commands,
    mode: Res<RunMode>,
    mut images: ResMut<Assets<Image>>,
    shots: Option<ResMut<Shots>>,
) {
    let (Some(_), Some(mut shots)) = (mode.screenshot.as_ref(), shots) else {
        return;
    };
    let flame = shot_target(&mut images, 1280, 720);
    let person = shot_target(&mut images, 1280, 720);
    let flame_cam = camera(&mut commands, flame.clone());
    commands.entity(flame_cam).insert(FlameCloseCam);
    let person_cam = camera(&mut commands, person.clone());
    commands.entity(person_cam).insert(PersonCloseCam);
    shots.close_flame = Some(flame);
    shots.close_person = Some(person);
}

/// The flame still looks at the southernmost point of the first fire's front from outside it.
pub fn aim_flame_close(
    clock: SimClock,
    fires: Option<Res<Wildfire>>,
    mut camera: Query<&mut Transform, With<FlameCloseCam>>,
) {
    let (Some(fires), Ok(mut at)) = (fires, camera.single_mut()) else {
        return;
    };
    let front = fires
        .fronts(clock.now())
        .into_iter()
        .next()
        .map(|(_, front)| front)
        .unwrap_or_default();
    let Some(nearest) = front.into_iter().min_by(|a, b| a.y.total_cmp(&b.y)) else {
        return;
    };
    *at = Transform::from_translation(enu(
        nearest.x,
        nearest.y - FLAME_EYE_OUTSIDE_M,
        FLAME_EYE_ALTITUDE_M,
    ))
    .looking_at(enu(nearest.x, nearest.y, FLAME_LOOK_AT_M), Vec3::Y);
}

/// The person still stands in front of the first figure (the way it faces) and looks at its head.
pub fn aim_person_close(
    figures: Query<&Figure>,
    mut camera: Query<&mut Transform, With<PersonCloseCam>>,
) {
    let (Some(figure), Ok(mut at)) = (figures.iter().next(), camera.single_mut()) else {
        return;
    };
    let base = figure.bevy_position();
    let forward = Quat::from_rotation_y(figure.facing_yaw()) * Vec3::NEG_Z;
    let eye = base + forward * PERSON_EYE_AHEAD_M;
    *at = Transform::from_xyz(eye.x, PERSON_EYE_ALTITUDE_M + base.y, eye.z).looking_at(
        Vec3::new(base.x, base.y + PERSON_LOOK_AT_M, base.z),
        Vec3::Y,
    );
}
