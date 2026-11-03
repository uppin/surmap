//! One preset-styled building as entities: a collider, a dark interior, each floor's wall, frame,
//! pane, glow and soot meshes, and the roof. The handles are kept so a fire can change them.

use bevy::mesh::Mesh;
use bevy::prelude::*;
use bevy_rapier3d::prelude::*;

use super::look::BuildingLook;
use super::meshes::MeshBuilder;
use super::roofs::build_roof;
use super::surface::Surfaces;
use super::walls::{build_floors, FloorPlan, Opening, Shell};
use crate::building_style::{FacadePreset, Glazing, GlazingKind, ResolvedStyle, RoofPreset};
use crate::scene_manifest::{Building, PbrTextureSet};
use crate::world::enu;

/// One floor's entities. A part is `None` when the floor's glazing has none of it.
pub struct FloorView {
    pub wall: Entity,
    pub panes: Option<Entity>,
    pub glow: Option<Entity>,
    pub soot: Option<Entity>,
    pub openings: Vec<Opening>,
}

pub struct ViewMaterials {
    pub wall: Handle<StandardMaterial>,
    pub burnt_wall: Handle<StandardMaterial>,
    pub roof: Handle<StandardMaterial>,
    pub burnt_roof: Handle<StandardMaterial>,
}

/// What the fire needs to change on a building, and what it last showed.
pub struct BuildingView {
    pub id: String,
    /// The building's base pose; local points map to the world through it.
    pub pose: Transform,
    pub size: Vec3,
    /// Height of the highest point of the roof, m.
    pub roof_top_m: f32,
    pub floors: Vec<FloorView>,
    pub roof: Entity,
    pub materials: ViewMaterials,
    /// (burning floors, burnt floors) as last drawn.
    pub shown: (Vec<u32>, Vec<u32>),
    pub emitters: Vec<Entity>,
    pub light: Option<Entity>,
}

/// The loaded presets a building is drawn from; `punched` and `curtain` are the shipped default
/// glazings, used when a building asks for a kind its facade does not carry.
pub struct Presets<'a> {
    pub look: &'a BuildingLook,
    pub facade: &'a FacadePreset,
    pub roof: &'a RoofPreset,
    pub punched: Option<&'a Glazing>,
    pub curtain: Option<&'a Glazing>,
    /// The glow of a burning floor's windows (colour, intensity), when the scene can burn.
    pub glow: Option<([f32; 3], f32)>,
}

/// The facade's glazing with the building's own overrides on top. A kind the facade does not
/// carry takes its other fields from the shipped default of that kind.
pub fn merged_glazing(facade: &FacadePreset, own: Option<&Glazing>, presets: &Presets) -> Glazing {
    let Some(own) = own else {
        return facade.glazing.clone();
    };
    let base = if own.kind == facade.glazing.kind {
        &facade.glazing
    } else {
        match own.kind {
            GlazingKind::Punched => presets.punched.unwrap_or(&facade.glazing),
            GlazingKind::CurtainWall => presets.curtain.unwrap_or(&facade.glazing),
            GlazingKind::None => &facade.glazing,
        }
    };
    Glazing {
        kind: own.kind,
        window_ratio: own.window_ratio.or(base.window_ratio),
        pane_m: own.pane_m.or(base.pane_m),
        bay_m: own.bay_m.or(base.bay_m),
        mullion_m: own.mullion_m.or(base.mullion_m),
        glass: own.glass.clone().or_else(|| base.glass.clone()),
        frame: own.frame.clone().or_else(|| base.frame.clone()),
        mullion: own.mullion.clone().or_else(|| base.mullion.clone()),
        recess_m: own.recess_m.or(base.recess_m),
        frame_m: own.frame_m.or(base.frame_m),
        spandrel_m: own.spandrel_m.or(base.spandrel_m),
        spandrel: own.spandrel.clone().or_else(|| base.spandrel.clone()),
    }
}

fn mesh_entity(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    builder: MeshBuilder,
    material: &Handle<StandardMaterial>,
    name: String,
    hidden: bool,
) -> Option<Entity> {
    if builder.is_empty() {
        return None;
    }
    let visibility = if hidden {
        Visibility::Hidden
    } else {
        Visibility::Inherited
    };
    Some(
        commands
            .spawn((
                Name::new(name),
                Mesh3d(meshes.add(builder.build())),
                MeshMaterial3d(material.clone()),
                visibility,
            ))
            .id(),
    )
}

pub fn spawn_building(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    surfaces: &mut Surfaces,
    building: &Building,
    style: &ResolvedStyle,
    presets: &Presets,
) -> BuildingView {
    let [east, north, up] = building.size_m;
    let size = Vec3::new(east, up, north);
    let look = presets.look;
    let facade_key = &style.facade;
    let glazing = merged_glazing(presets.facade, style.glazing.as_ref(), presets);
    let curtain = glazing.kind == GlazingKind::CurtainWall;
    let wall_tint = style.facade_colour.filter(|_| presets.facade.colourable);
    let facade = surfaces.material(
        &format!("{facade_key}#material"),
        &presets.facade.material,
        wall_tint,
        false,
    );
    let burnt_wall = surfaces.material(
        &format!("{facade_key}#burnt"),
        &presets.facade.burnt,
        None,
        false,
    );
    let wall = match (&glazing.spandrel, curtain) {
        (Some(spandrel), true) => {
            surfaces.material(&format!("{facade_key}#spandrel"), spandrel, None, false)
        }
        _ => facade.clone(),
    };
    let roof_tint = style.roof_colour.filter(|_| presets.roof.colourable);
    let roof_material = surfaces.material(
        &format!("{}#material", style.roof),
        &presets.roof.material,
        roof_tint,
        true,
    );
    let burnt_roof = surfaces.material(
        &format!("{}#burnt", style.roof),
        &presets.roof.burnt,
        None,
        true,
    );
    let part = |surfaces: &mut Surfaces, key: &str, set: &Option<PbrTextureSet>| {
        set.as_ref()
            .map(|def| surfaces.material(&format!("{facade_key}#{key}"), def, None, false))
    };
    let frame = part(
        surfaces,
        "frame",
        if curtain {
            &glazing.mullion
        } else {
            &glazing.frame
        },
    );
    let pane = part(surfaces, "glass", &glazing.glass);
    let glow = presets.glow.map(|(colour, intensity)| {
        let c = Color::srgb(colour[0], colour[1], colour[2]).to_linear();
        surfaces.flat(StandardMaterial {
            base_color: Color::BLACK,
            emissive: LinearRgba::rgb(c.red, c.green, c.blue) * intensity,
            cull_mode: None,
            ..default()
        })
    });
    let soot = surfaces.flat(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        alpha_mode: AlphaMode::Blend,
        cull_mode: None,
        ..default()
    });
    let [ir, ig, ib] = look.interior.colour;
    let interior = surfaces.flat(StandardMaterial {
        base_color: Color::srgb(ir, ig, ib),
        perceptual_roughness: 1.0,
        ..default()
    });

    let shell = Shell {
        size,
        floors: style.floors,
    };
    let plans: Vec<FloorPlan> = (0..style.floors)
        .map(|floor| {
            let shop = floor < look.shopfront.floors;
            let own = style.glazing.as_ref().and_then(|g| g.window_ratio);
            let ratio = own
                .or(shop.then_some(style.ground_window_ratio).flatten())
                .or(style.window_ratio);
            FloorPlan {
                glazing: &glazing,
                window_ratio: ratio,
            }
        })
        .collect();
    let floor_meshes = build_floors(shell, &plans, look);
    let roof_meshes = build_roof(style.roof_shape, size, look);
    let roof_meshes_rise = roof_meshes.rise_m;

    let pose = Transform::from_translation(enu(
        building.position_enu[0],
        building.position_enu[1],
        building.position_enu[2],
    ))
    .with_rotation(Quat::from_rotation_y(building.yaw_deg.to_radians()));
    let id = &building.id;
    let mut children: Vec<Entity> = Vec::new();
    let mut floors = Vec::new();
    for (index, meshes_of) in floor_meshes.into_iter().enumerate() {
        let name = |part: &str| format!("{id} floor {index} {part}");
        let wall_entity = mesh_entity(commands, meshes, meshes_of.wall, &wall, name("wall"), false);
        let wall_entity =
            wall_entity.unwrap_or_else(|| commands.spawn(Name::new(name("wall"))).id());
        let frames = frame
            .as_ref()
            .and_then(|m| mesh_entity(commands, meshes, meshes_of.frame, m, name("frame"), false));
        let panes = pane
            .as_ref()
            .and_then(|m| mesh_entity(commands, meshes, meshes_of.pane, m, name("pane"), false));
        let glow_entity = glow
            .as_ref()
            .and_then(|m| mesh_entity(commands, meshes, meshes_of.glow, m, name("glow"), true));
        let soot_entity = mesh_entity(commands, meshes, meshes_of.soot, &soot, name("soot"), true);
        children.extend(
            [Some(wall_entity), frames, panes, glow_entity, soot_entity]
                .into_iter()
                .flatten(),
        );
        floors.push(FloorView {
            wall: wall_entity,
            panes,
            glow: glow_entity,
            soot: soot_entity,
            openings: meshes_of.openings,
        });
    }
    let roof = mesh_entity(
        commands,
        meshes,
        roof_meshes.roof,
        &roof_material,
        format!("{id} roof"),
        false,
    )
    .unwrap_or_else(|| commands.spawn(Name::new(format!("{id} roof"))).id());
    children.push(roof);
    children.extend(mesh_entity(
        commands,
        meshes,
        roof_meshes.trim,
        &facade,
        format!("{id} trim"),
        false,
    ));
    let inset = look.interior.inset_m;
    let core = Cuboid::from_size(Vec3::new(
        size.x - 2.0 * inset,
        size.y,
        size.z - 2.0 * inset,
    ));
    children.push(
        commands
            .spawn((
                Name::new(format!("{id} interior")),
                Mesh3d(meshes.add(Mesh::from(core))),
                MeshMaterial3d(interior),
                Transform::from_xyz(0.0, size.y / 2.0, 0.0),
            ))
            .id(),
    );
    children.push(
        commands
            .spawn((
                Name::new(format!("{id} collider")),
                RigidBody::Fixed,
                Collider::cuboid(size.x / 2.0, size.y / 2.0, size.z / 2.0),
                Transform::from_xyz(0.0, size.y / 2.0, 0.0),
            ))
            .id(),
    );
    commands
        .spawn((Name::new(id.clone()), pose, Visibility::default()))
        .add_children(&children);
    BuildingView {
        id: id.clone(),
        pose,
        size,
        roof_top_m: size.y + roof_meshes_rise,
        floors,
        roof,
        materials: ViewMaterials {
            wall,
            burnt_wall,
            roof: roof_material,
            burnt_roof,
        },
        shown: (Vec::new(), Vec::new()),
        emitters: Vec::new(),
        light: None,
    }
}
