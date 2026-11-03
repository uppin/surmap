//! Page UI: stereo feed panel, calibration readout, status line,
//! and the take-off/land button. Drawn by Bevy itself; the feeds are
//! the drone cameras' render targets.

use bevy::prelude::*;
use bevy_rapier3d::prelude::Velocity;

use crate::calibration::CameraProfile;
use crate::{Drone, Flight, StereoFeeds};

#[derive(Component)]
pub(crate) struct StatusText;

#[derive(Component)]
pub(crate) struct TakeoffButton;

pub(crate) fn setup_ui(mut commands: Commands, feeds: Res<StereoFeeds>, rig: Res<CameraProfile>) {
    // Stereo feeds + the calibration this rig produces, drawn by Bevy.
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                right: Val::Px(12.0),
                top: Val::Px(12.0),
                width: Val::Px(324.0),
                flex_direction: FlexDirection::Column,
                row_gap: Val::Px(6.0),
                padding: UiRect::all(Val::Px(8.0)),
                ..default()
            },
            BackgroundColor(Color::srgba(0.05, 0.07, 0.09, 0.88)),
        ))
        .with_children(|panel| {
            for (label, handle) in [("LEFT", feeds.left.clone()), ("RIGHT", feeds.right.clone())] {
                panel.spawn((
                    Text::new(label),
                    TextFont {
                        font_size: 11.0,
                        ..default()
                    },
                    TextColor(Color::srgb(0.65, 0.75, 0.85)),
                ));
                panel.spawn((
                    ImageNode::new(handle),
                    Node {
                        width: Val::Px(308.0),
                        height: Val::Px(231.0),
                        ..default()
                    },
                ));
            }
            panel.spawn((
                Text::new(format!(
                    "CAMERA PROFILE {} ({:?})\n{}x{}  fx={} fy={}  cx={} cy={}\nbaseline={} m  pitch={} deg  rate={} Hz\nRTAB-Map gets its calibration from this same file",
                    rig.id,
                    rig.model,
                    rig.width,
                    rig.height,
                    rig.fx,
                    rig.fy,
                    rig.cx,
                    rig.cy,
                    rig.baseline_m,
                    rig.mount.pitch_deg,
                    rig.rate_hz,
                )),
                TextFont {
                    font_size: 11.0,
                    ..default()
                },
                TextColor(Color::srgb(0.80, 0.87, 0.94)),
            ));
        });
    commands.spawn((
        StatusText,
        Text::new("landed | Space: take off"),
        TextFont {
            font_size: 14.0,
            ..default()
        },
        TextColor(Color::WHITE),
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(12.0),
            top: Val::Px(12.0),
            ..default()
        },
    ));
}

pub(crate) fn setup_button(mut commands: Commands) {
    commands
        .spawn((
            TakeoffButton,
            Button,
            Node {
                position_type: PositionType::Absolute,
                left: Val::Px(12.0),
                bottom: Val::Px(12.0),
                padding: UiRect::axes(Val::Px(18.0), Val::Px(10.0)),
                ..default()
            },
            BackgroundColor(Color::srgb(0.13, 0.42, 0.24)),
        ))
        .with_children(|button| {
            button.spawn((
                Text::new("Take off"),
                TextFont {
                    font_size: 16.0,
                    ..default()
                },
                TextColor(Color::WHITE),
            ));
        });
}

pub(crate) fn takeoff_button(
    mut flight: ResMut<Flight>,
    mut buttons: Query<(&Interaction, &mut BackgroundColor, &Children), With<TakeoffButton>>,
    mut labels: Query<&mut Text>,
    mut was_pressed: Local<bool>,
) {
    for (interaction, mut background, children) in &mut buttons {
        let pressed = *interaction == Interaction::Pressed;
        if pressed && !*was_pressed {
            flight.engaged = !flight.engaged;
        }
        *was_pressed = pressed;
        background.0 = if flight.engaged {
            Color::srgb(0.45, 0.20, 0.16)
        } else {
            Color::srgb(0.13, 0.42, 0.24)
        };
        if let Some(child) = children.first() {
            if let Ok(mut label) = labels.get_mut(*child) {
                label.0 = if flight.engaged {
                    "Land".into()
                } else {
                    "Take off".into()
                };
            }
        }
    }
}

pub(crate) fn update_status(
    flight: Res<Flight>,
    drone: Query<(&Transform, &Velocity), With<Drone>>,
    mut status: Query<&mut Text, With<StatusText>>,
) {
    let (Ok((body, velocity)), Ok(mut text)) = (drone.single(), status.single_mut()) else {
        return;
    };
    text.0 = format!(
        "{}  alt {:.1} m  speed {:.1} m/s  yaw {:.0} deg\nWASD move | Q/E yaw | R/F up/down | Space {}",
        if flight.engaged { "FLYING" } else { "LANDED" },
        body.translation.y,
        velocity.linvel.length(),
        flight.yaw_deg,
        if flight.engaged { "land" } else { "take off" },
    );
}
