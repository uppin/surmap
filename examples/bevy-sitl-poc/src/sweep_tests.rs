//! The sim-disaster-2 sweep's contracts (`docs/simulation/1-WIP/2026-11-04-sim-disaster-2-sweep.md`):
//! flame flipbooks, pre-warmed smoke, per-window glow, metallic packing, the figure's visor and
//! per-stand grass placement.

use bevy::math::Vec2;

use crate::actors::FigureDef;
use crate::building::look::BuildingLook;
use crate::fxdef::{FxDef, SpeciesDef};
use crate::scene_manifest::Vegetation;
use crate::textures::pack_metallic_roughness;
use crate::vegetation::grass_instances;

fn shipped(path: &str) -> String {
    std::fs::read_to_string(format!("{}/assets/{path}", env!("CARGO_MANIFEST_DIR")))
        .unwrap_or_else(|e| panic!("assets/{path} is shipped: {e}"))
}

fn fx(name: &str) -> FxDef {
    FxDef::from_json(&shipped(&format!("fx/{name}.fx.json")))
        .unwrap_or_else(|e| panic!("{name}: {e}"))
}

#[test]
fn flames_and_window_flames_play_a_flipbook_of_flame_tongues() {
    for name in ["flames", "window_flames"] {
        let book = fx(name)
            .flipbook
            .unwrap_or_else(|| panic!("{name} has a flipbook"));

        assert!(
            book.texture.starts_with("textures/fx/") && book.texture.ends_with(".png"),
            "{}",
            book.texture
        );
        assert!(book.columns * book.rows > 1 && book.fps > 0.0);
    }
}

#[test]
fn a_flipbook_without_frames_is_refused() {
    let text = r#"{"colour_gradient": [[0, [1,1,1], 1, 1], [1, [1,1,1], 1, 0]],
        "size_m": [1, 2], "lifetime_s": [1, 2], "motion": {"up": 1, "wind_coupling": 0.5},
        "blend": "additive", "spawn": {"per_second": 10}, "max_particles": 100,
        "flipbook": {"texture": "textures/fx/flame.png", "columns": 0, "rows": 4, "fps": 24}}"#;

    assert!(FxDef::from_json(text).is_err());
}

#[test]
fn shipped_smokes_prewarm_at_least_their_longest_lifetime() {
    for name in ["smoke", "building_smoke"] {
        let smoke = fx(name);

        assert!(
            smoke.prewarm_s >= smoke.lifetime_s[1],
            "{name}: prewarm {} < lifetime {}",
            smoke.prewarm_s,
            smoke.lifetime_s[1]
        );
    }
}

fn shipped_fire_look() -> crate::building::look::FireLook {
    BuildingLook::from_json(&shipped("building/look.json"))
        .expect("look.json")
        .fire
}

#[test]
fn window_glow_varies_between_windows_within_its_range() {
    let look = shipped_fire_look();
    let v = look.glow_variation;

    let glows: Vec<f32> = (0..64).map(|w| look.window_glow(7, w, 3.0)).collect();

    assert!(v > 0.0, "look.json declares a glow variation");
    assert!(
        glows
            .iter()
            .all(|g| (1.0 - v - 1e-4..=1.0 + v + 1e-4).contains(g)),
        "{glows:?}"
    );
    let spread = glows.iter().cloned().fold(f32::MIN, f32::max)
        - glows.iter().cloned().fold(f32::MAX, f32::min);
    assert!(spread > v * 0.5, "windows differ: spread {spread}");
}

#[test]
fn window_glow_is_seeded_and_flickers_in_time() {
    let look = shipped_fire_look();

    assert_eq!(look.window_glow(7, 3, 2.0), look.window_glow(7, 3, 2.0));
    assert_ne!(
        look.window_glow(7, 3, 2.0),
        look.window_glow(8, 3, 2.0),
        "another building differs"
    );
    let over_time: Vec<f32> = (0..20)
        .map(|i| look.window_glow(7, 3, i as f32 * 0.1))
        .collect();
    assert!(
        over_time.windows(2).any(|p| (p[0] - p[1]).abs() > 1e-3),
        "flickers: {over_time:?}"
    );
}

#[test]
fn a_roughness_map_keeps_the_presets_metallic() {
    let roughness = [64, 64, 64, 255, 200, 200, 200, 255];

    let packed = pack_metallic_roughness(&roughness, 0.8);

    assert_eq!(packed, vec![255, 64, 204, 255, 255, 200, 204, 255]);
}

#[test]
fn the_figure_wears_a_visor_on_the_front_of_its_head() {
    let figure = FigureDef::from_json(&shipped("behaviour/person.figure.json")).expect("figure");

    let visor = figure.visor.expect("a visor makes the heading readable");
    assert!(visor.offset_m[2] < 0.0, "in front: {:?}", visor.offset_m);
    assert!(
        visor.offset_m[1] > 1.4,
        "at head height: {:?}",
        visor.offset_m
    );
}

fn a_stand(seed: u64) -> Vegetation {
    Vegetation {
        id: "grass".into(),
        species: "species/dry_grass.species.json".into(),
        position_enu: [10.0, 20.0, 0.0],
        size_m: [20.0, 10.0],
        density_per_100m2: 30.0,
        seed,
    }
}

fn dry_grass() -> SpeciesDef {
    SpeciesDef::from_json(&shipped("species/dry_grass.species.json")).expect("dry grass")
}

#[test]
fn a_stands_grass_is_its_own_seed_s_and_repeats_for_it() {
    let def = dry_grass();

    let a = grass_instances(&a_stand(1), &def);
    let again = grass_instances(&a_stand(1), &def);
    let b = grass_instances(&a_stand(2), &def);

    assert_eq!(a, again);
    assert_ne!(a, b);
}

#[test]
fn grass_fills_its_stand_at_its_density() {
    let def = dry_grass();
    let stand = a_stand(1);

    let clumps = grass_instances(&stand, &def);

    let expected = 20.0 * 10.0 / 100.0 * 30.0 * def.plants_per_unit;
    assert!(
        (clumps.len() as f32 - expected).abs() <= expected * 0.05 + 1.0,
        "{} vs {expected}",
        clumps.len()
    );
    assert!(
        clumps
            .iter()
            .all(|p| (0.0..=20.0).contains(&p.x) && (15.0..=25.0).contains(&p.y)),
        "inside the 20 × 10 m stand around (10, 20)"
    );
}
