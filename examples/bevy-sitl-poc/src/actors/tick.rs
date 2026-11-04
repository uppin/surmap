//! The 10 Hz tick (docs/simulation/bevy-simulation.md § *Behaviour trees*): the wind's tree, then
//! every person's and every vehicle's, run in order up to the simulation's moment on `SimClock`.

use bevy::math::Vec2;
use bevy::prelude::{Assets, Query, Res, ResMut, Resource};

use super::{FigureAsset, FigureLook, Figure, CLOCK_SLACK_S, DT};
use crate::behaviour::{Runner, World};
use crate::building::BuildingClock;
use crate::building_fire::BuildingFires;
use crate::fire::FireSpec;
use crate::scene_manifest::Weather;
use crate::vehicle::scene::{VehicleActor, VehicleAsset, VehicleClasses};
use crate::wildfire::{SimClock, Wildfire};
use crate::wind::WindModel;

/// The scenario's wind tree and the tick count: tick `n` runs at `n / TICK_HZ` seconds.
#[derive(Resource, Default)]
pub struct Behaviour {
    wind: Option<Runner>,
    ticks: u64,
}

impl Behaviour {
    pub fn new(wind: Option<Runner>) -> Self {
        Self { wind, ticks: 0 }
    }
}

/// The scenario's wind tree, when its weather has one; it starts from the weather's wind.
pub fn wind_runner(weather: Option<&Weather>) -> Option<Runner> {
    let weather = weather?;
    let tree = weather.wind.behaviour.clone()?;
    Some(Runner::new(
        tree,
        Vec2::ZERO,
        WindModel::from(&weather.wind),
    ))
}

fn tick_time(ticks: u64) -> f32 {
    ticks as f32 * DT
}

/// Ticks every tree up to the simulation's moment, in order, then moves the figures. It runs
/// before the wind is read, so the vegetation, the fire and the particles see this tick's wind.
pub fn tick_behaviours(
    clock: SimClock,
    look: Option<Res<FigureLook>>,
    looks: Res<Assets<FigureAsset>>,
    scene: Option<ResMut<Wildfire>>,
    buildings: BuildingClock,
    mut behaviour: ResMut<Behaviour>,
    mut figures: Query<&mut Figure>,
    classes: Option<Res<VehicleClasses>>,
    defs: Res<Assets<VehicleAsset>>,
    mut vehicles: Query<&mut VehicleActor>,
) {
    let (Some(look), Some(mut scene)) = (look, scene) else {
        return;
    };
    // The ticks of buildings still being raised would run without their fire: wait for them.
    if buildings.raising.is_some() {
        return;
    }
    let Some(FigureAsset(gait)) = looks.get(&look.0) else {
        return;
    };
    let now = clock.now();
    let mut fires = buildings.blaze.map(|blaze| blaze.map_unchanged(|b| &mut b.fires));
    while tick_time(behaviour.ticks) <= now + CLOCK_SLACK_S {
        let t_s = tick_time(behaviour.ticks);
        tick_once(
            t_s,
            &mut behaviour,
            &mut scene,
            fires.as_deref_mut(),
            &mut figures,
            (classes.as_deref(), &*defs, &mut vehicles),
            gait.yaw_ease_s,
        );
        behaviour.ticks += 1;
    }
}

fn tick_once(
    t_s: f32,
    behaviour: &mut Behaviour,
    scene: &mut Wildfire,
    buildings: Option<&mut BuildingFires>,
    figures: &mut Query<&mut Figure>,
    (classes, defs, vehicles): (Option<&VehicleClasses>, &Assets<VehicleAsset>, &mut Query<&mut VehicleActor>),
    yaw_ease_s: f32,
) {
    let fires: Vec<FireSpec> = scene.fire_specs();
    if let Some(wind) = behaviour.wind.as_mut() {
        let current = wind.wind;
        wind.tick(
            &World {
                t_s,
                fires: &fires,
                burning_areas: &[],
                wind: &current,
                objects: &[],
            },
            DT,
        );
        scene.wind = wind.wind;
    }
    let wind = scene.wind;
    // Buildings alight at this tick, for people to flee from.
    let burning_areas: Vec<Vec<Vec2>> = buildings.map_or_else(Vec::new, |buildings| {
        buildings.step(t_s, DT, wind.velocity_enu(t_s), &fires);
        buildings.burning_footprints()
    });
    let objects: Vec<(String, Vec2)> = figures
        .iter()
        .map(|figure| (figure.id.clone(), figure.position()))
        .chain(vehicles.iter().map(|vehicle| (vehicle.id.clone(), vehicle.body.drive.position)))
        .collect();
    let world = World {
        t_s,
        fires: &fires,
        burning_areas: &burning_areas,
        wind: &wind,
        objects: &objects,
    };
    for mut figure in figures.iter_mut() {
        figure.step(&world, yaw_ease_s);
    }
    if let Some(classes) = classes {
        for mut vehicle in vehicles.iter_mut() {
            if let Some(def) = classes.def(vehicle.class, defs) {
                vehicle.body.tick(def, &world, DT);
            }
        }
    }
}
