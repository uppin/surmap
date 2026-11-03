//! Preset-styled buildings and their fires at run time (docs/simulation/bevy-simulation.md §
//! *Buildings and building fires*). The manifest names districts and presets; this plans which
//! preset files to fetch, resolves each building's style once they are in, builds the walls, roofs
//! and glazing, and — when anything can burn — the `BuildingBlaze` the behaviour clock steps and
//! `fire_view` draws.

use std::collections::BTreeMap;

use bevy::ecs::system::SystemParam;
use bevy::prelude::*;

use crate::building_fire::{BuildingFireTuning, BuildingFires, Footprint, Ignition};
use crate::building_style::{
    district_path, facade_path, resolve, Glazing, OwnStyle, PlacedDistrict, ResolvedStyle,
};
use crate::fxdef::FxAsset;
use crate::scene_manifest::{Building, DistrictDef, Element, SceneManifest};
use crate::world::{build_world, ManifestAsset, SceneState};

mod assets;
mod fire_view;
mod look;
mod meshes;
mod roofs;
mod spawn;
mod surface;
mod walls;

use assets::{
    DistrictAsset, DistrictLoader, FacadeAsset, FacadeLoader, LookAsset, LookLoader, RoofAsset,
    RoofLoader, TuningAsset, TuningLoader,
};
pub use fire_view::BuildingBlaze;
use fire_view::{Kind, Layer};
use spawn::{spawn_building, Presets};
use surface::Surfaces;

/// The tuning file a scene with a wildfire but no building fire uses.
const DEFAULT_TUNING: &str = "building/fire.json";
const LOOK: &str = "building/look.json";

pub struct BuildingPlugin;

impl Plugin for BuildingPlugin {
    fn build(&self, app: &mut App) {
        app.init_asset::<FacadeAsset>()
            .init_asset_loader::<FacadeLoader>()
            .init_asset::<RoofAsset>()
            .init_asset_loader::<RoofLoader>()
            .init_asset::<DistrictAsset>()
            .init_asset_loader::<DistrictLoader>()
            .init_asset::<TuningAsset>()
            .init_asset_loader::<TuningLoader>()
            .init_asset::<LookAsset>()
            .init_asset_loader::<LookLoader>()
            .add_systems(
                Update,
                (raise_buildings, fire_view::update_building_fires)
                    .chain()
                    .after(build_world)
                    .after(crate::actors::tick_behaviours),
            );
    }
}

/// Whether a building is drawn from presets: it names one, or a district holds its centre.
pub fn is_styled(building: &Building, districts: &[DistrictDef]) -> bool {
    building.facade.is_some()
        || building.roof.is_some()
        || districts
            .iter()
            .any(|d| d.holds(building.position_enu[0], building.position_enu[1]))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Stage {
    /// Waiting for the look, the tuning and the districts.
    Districts,
    /// Waiting for the facade and roof presets the districts drew.
    Presets,
}

/// The preset files a scene waits on, and what it resolved from them so far.
#[derive(Resource)]
pub struct BuildingPlan {
    stage: Stage,
    look: Handle<LookAsset>,
    tuning: Option<Handle<TuningAsset>>,
    districts: Vec<(DistrictDef, Handle<DistrictAsset>)>,
    facades: BTreeMap<String, Handle<FacadeAsset>>,
    roofs: BTreeMap<String, Handle<RoofAsset>>,
    fx: Vec<(Kind, Handle<FxAsset>)>,
    /// `(element index, style)` of each styled building.
    styled: Vec<(usize, ResolvedStyle)>,
}

/// Start loading `path`, and wait for it before the scene counts as ready.
fn fetch<A: Asset>(
    assets: &AssetServer,
    pending: &mut Vec<UntypedHandle>,
    path: &str,
) -> Handle<A> {
    let handle = assets.load(path.to_owned());
    pending.push(handle.clone().untyped());
    handle
}

/// Start loading what the styled buildings of `manifest` need; `None` when there are none.
pub fn plan(
    manifest: &SceneManifest,
    assets: &AssetServer,
    pending: &mut Vec<UntypedHandle>,
) -> Option<BuildingPlan> {
    let styled = manifest
        .elements
        .iter()
        .any(|e| matches!(e, Element::Building(b) if is_styled(b, &manifest.districts)));
    if !styled {
        return None;
    }
    let tuning_path = manifest
        .building_fires
        .first()
        .map(|f| f.tuning.clone())
        .or_else(|| (!manifest.fires.is_empty()).then(|| DEFAULT_TUNING.to_owned()));
    let districts = manifest
        .districts
        .iter()
        .map(|d| {
            (
                d.clone(),
                fetch(
                    assets,
                    pending,
                    &district_path(&d.preset).unwrap_or_default(),
                ),
            )
        })
        .collect();
    let look = fetch(assets, pending, LOOK);
    let tuning = tuning_path.map(|path| fetch(assets, pending, &path));
    Some(BuildingPlan {
        stage: Stage::Districts,
        look,
        tuning,
        districts,
        facades: BTreeMap::new(),
        roofs: BTreeMap::new(),
        fx: Vec::new(),
        styled: Vec::new(),
    })
}

/// What the behaviour clock needs of the buildings: their fire, and whether they are still being
/// raised (its ticks wait for them, so no tick runs without the fire it should have seen).
#[derive(SystemParam)]
pub struct BuildingClock<'w> {
    pub blaze: Option<ResMut<'w, BuildingBlaze>>,
    pub raising: Option<Res<'w, BuildingPlan>>,
}

/// The loaded preset assets a plan reads.
#[derive(SystemParam)]
pub struct PresetAssets<'w> {
    looks: Res<'w, Assets<LookAsset>>,
    tunings: Res<'w, Assets<TuningAsset>>,
    districts: Res<'w, Assets<DistrictAsset>>,
    facades: Res<'w, Assets<FacadeAsset>>,
    roofs: Res<'w, Assets<RoofAsset>>,
}

/// What raising the buildings builds with.
#[derive(SystemParam)]
pub struct Raising<'w, 's> {
    commands: Commands<'w, 's>,
    assets: Res<'w, AssetServer>,
    meshes: ResMut<'w, Assets<Mesh>>,
    materials: ResMut<'w, Assets<StandardMaterial>>,
    presets: PresetAssets<'w>,
    manifests: Res<'w, Assets<ManifestAsset>>,
}

fn footprint(building: &Building, floors: u32) -> Footprint {
    let (half_east, half_north) = (building.size_m[0] / 2.0, building.size_m[1] / 2.0);
    let (sin, cos) = building.yaw_deg.to_radians().sin_cos();
    let centre = Vec2::new(building.position_enu[0], building.position_enu[1]);
    let polygon_enu = [
        (-half_east, -half_north),
        (half_east, -half_north),
        (half_east, half_north),
        (-half_east, half_north),
    ]
    .map(|(x, y)| centre + Vec2::new(x * cos - y * sin, x * sin + y * cos))
    .to_vec();
    Footprint {
        id: building.id.clone(),
        polygon_enu,
        floors,
    }
}

fn own_style(building: &Building) -> OwnStyle {
    OwnStyle {
        facade: building.facade.clone(),
        roof: building.roof.clone(),
        roof_shape: building.roof_shape,
        facade_colour: building.facade_colour,
        roof_colour: building.roof_colour,
        floors: building.floors,
        glazing: building.glazing.clone(),
    }
}

fn loaded<A: Asset>(assets: &AssetServer, handles: impl IntoIterator<Item = Handle<A>>) -> bool {
    handles
        .into_iter()
        .all(|h| assets.is_loaded_with_dependencies(h.id()))
}

/// Resolve every styled building from the loaded districts, then name the presets they need.
fn resolve_styles(
    plan: &mut BuildingPlan,
    manifest: &SceneManifest,
    raising: &Raising,
    assets: &AssetServer,
    pending: &mut Vec<UntypedHandle>,
) -> Result<(), String> {
    let placed: Vec<PlacedDistrict> = plan
        .districts
        .iter()
        .filter_map(|(def, handle)| {
            let preset = raising.presets.districts.get(handle)?.0.clone();
            Some(PlacedDistrict {
                id: def.id.clone(),
                centre: Vec2::new(def.position_enu[0], def.position_enu[1]),
                size_m: Vec2::new(def.size_m[0], def.size_m[1]),
                seed: def.seed,
                preset,
            })
        })
        .collect();
    let mut wanted_glazing = false;
    for (index, element) in manifest.elements.iter().enumerate() {
        let Element::Building(building) = element else {
            continue;
        };
        if !is_styled(building, &manifest.districts) {
            continue;
        }
        let centre = Vec2::new(building.position_enu[0], building.position_enu[1]);
        let style = resolve(
            &building.id,
            centre,
            building.size_m[2],
            &own_style(building),
            &placed,
        )?;
        wanted_glazing |= style.glazing.is_some();
        plan.styled.push((index, style));
    }
    let mut facades: Vec<String> = plan.styled.iter().map(|(_, s)| s.facade.clone()).collect();
    if wanted_glazing {
        // The shipped default of each glazing kind, for a building that asks for the other one.
        facades.extend(["plaster", "glass"].map(|name| facade_path(name).unwrap_or_default()));
    }
    for path in facades {
        plan.facades
            .entry(path.clone())
            .or_insert_with(|| fetch(assets, pending, &path));
    }
    for (_, style) in &plan.styled {
        plan.roofs
            .entry(style.roof.clone())
            .or_insert_with(|| fetch(assets, pending, &style.roof));
    }
    if let Some(tuning) = plan
        .tuning
        .as_ref()
        .and_then(|h| raising.presets.tunings.get(h))
    {
        let effects = &tuning.0.effects;
        plan.fx = vec![
            (Kind::Flames, fetch(assets, pending, &effects.window_flames)),
            (Kind::Smoke, fetch(assets, pending, &effects.smoke)),
            (Kind::Embers, fetch(assets, pending, &effects.embers)),
        ];
    }
    Ok(())
}

/// The fire for every styled building, lit where the manifest says; `Err` names a fire that
/// cannot burn.
fn build_fires(
    manifest: &SceneManifest,
    plan: &BuildingPlan,
    tuning: BuildingFireTuning,
) -> Result<BuildingFires, String> {
    let footprints: Vec<Footprint> = plan
        .styled
        .iter()
        .filter_map(|(index, style)| match &manifest.elements[*index] {
            Element::Building(b) => Some(footprint(b, style.floors)),
            _ => None,
        })
        .collect();
    let mut ignitions = Vec::new();
    for fire in &manifest.building_fires {
        let Some(target) = footprints.iter().find(|f| f.id == fire.building) else {
            return Err(format!(
                "building fire {}: {} is not drawn from presets",
                fire.id, fire.building
            ));
        };
        if fire.floor >= target.floors {
            return Err(format!(
                "building fire {}: floor {} is not below {}'s {} floors",
                fire.id, fire.floor, fire.building, target.floors
            ));
        }
        ignitions.push(Ignition {
            building: fire.building.clone(),
            floor: fire.floor,
            start_s: fire.start_s,
        });
    }
    Ok(BuildingFires::new(footprints, ignitions, tuning))
}

/// Advance the plan: resolve once the districts are in, build once the presets are.
pub fn raise_buildings(
    mut state: ResMut<SceneState>,
    plan: Option<ResMut<BuildingPlan>>,
    mut raising: Raising,
) {
    let Some(mut plan) = plan else { return };
    let Some(ManifestAsset(manifest)) = raising
        .manifests
        .get(&state.manifest)
        .map(|m| ManifestAsset(m.0.clone()))
    else {
        return;
    };
    let assets: AssetServer = (*raising.assets).clone();
    if plan.stage == Stage::Districts {
        let ready = loaded(&assets, [plan.look.clone()])
            && loaded(&assets, plan.tuning.clone())
            && loaded(&assets, plan.districts.iter().map(|(_, h)| h.clone()));
        if !ready {
            return;
        }
        let mut pending = std::mem::take(&mut state.pending);
        let resolved = resolve_styles(&mut plan, &manifest, &raising, &assets, &mut pending);
        state.pending = pending;
        if let Err(why) = resolved {
            state.failed = Some(why);
            raising.commands.remove_resource::<BuildingPlan>();
            return;
        }
        plan.stage = Stage::Presets;
        return;
    }
    let ready = loaded(&assets, plan.facades.values().cloned())
        && loaded(&assets, plan.roofs.values().cloned())
        && loaded(&assets, plan.fx.iter().map(|(_, h)| h.clone()));
    if !ready {
        return;
    }
    let result = raise(&mut state, &plan, &manifest, &mut raising);
    raising.commands.remove_resource::<BuildingPlan>();
    match result {
        Ok(()) => state.buildings_ready = true,
        Err(why) => state.failed = Some(why),
    }
}

fn raise(
    state: &mut SceneState,
    plan: &BuildingPlan,
    manifest: &SceneManifest,
    raising: &mut Raising,
) -> Result<(), String> {
    let look = &raising
        .presets
        .looks
        .get(&plan.look)
        .ok_or("building/look.json did not load")?
        .0;
    let tuning = plan
        .tuning
        .as_ref()
        .and_then(|h| raising.presets.tunings.get(h))
        .map(|t| t.0.clone());
    let glazing_of = |name: &str| -> Option<&Glazing> {
        let handle = plan.facades.get(&facade_path(name).ok()?)?;
        raising.presets.facades.get(handle).map(|f| &f.0.glazing)
    };
    let (punched, curtain) = (glazing_of("plaster"), glazing_of("glass"));
    let mut surfaces = Surfaces::new(&raising.assets, &mut raising.materials, &mut state.pending);
    let mut views = Vec::new();
    for (index, style) in &plan.styled {
        let Element::Building(building) = &manifest.elements[*index] else {
            continue;
        };
        let facade = plan
            .facades
            .get(&style.facade)
            .and_then(|h| raising.presets.facades.get(h))
            .ok_or(format!("{} did not load", style.facade))?;
        let roof = plan
            .roofs
            .get(&style.roof)
            .and_then(|h| raising.presets.roofs.get(h))
            .ok_or(format!("{} did not load", style.roof))?;
        let presets = Presets {
            look,
            facade: &facade.0,
            roof: &roof.0,
            punched,
            curtain,
            glow: tuning.as_ref().map(|t| (t.glow_colour, t.glow_intensity)),
        };
        views.push(spawn_building(
            &mut raising.commands,
            &mut raising.meshes,
            &mut surfaces,
            building,
            style,
            &presets,
        ));
    }
    info!(
        "raised {} preset-styled buildings; fire tuning {}",
        views.len(),
        if tuning.is_some() { "loaded" } else { "absent" }
    );
    if let Some(tuning) = tuning {
        let fires = build_fires(manifest, plan, tuning)?;
        let layers = plan
            .fx
            .iter()
            .map(|(kind, handle)| Layer::new(*kind, handle.clone()))
            .collect();
        let declared = manifest
            .building_fires
            .iter()
            .map(|f| (f.building.clone(), f.floor))
            .collect();
        raising.commands.insert_resource(BuildingBlaze {
            fires,
            views,
            look: look.clone(),
            layers,
            declared,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests;
