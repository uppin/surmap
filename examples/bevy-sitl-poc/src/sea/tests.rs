use super::*;

const BOAT: f32 = 1.0;
const SHIP: f32 = 0.1;

/// The largest heave, pitch and roll over a minute at 10 Hz.
fn worst_over_a_minute(sea: SeaState, response: f32) -> VesselMotion {
    (0..600).map(|n| vessel_motion(sea, response, n as f32 / 10.0, 0.3)).fold(VesselMotion::default(), |worst, m| VesselMotion {
        heave_m: worst.heave_m.max(m.heave_m.abs()),
        pitch_rad: worst.pitch_rad.max(m.pitch_rad.abs()),
        roll_rad: worst.roll_rad.max(m.roll_rad.abs()),
    })
}

#[test]
fn a_calm_wind_leaves_still_water() {
    let calm = sea_state(0.0);

    assert_eq!(worst_over_a_minute(calm, BOAT), VesselMotion::default());
}

#[test]
fn a_stronger_wind_rocks_a_boat_harder() {
    let breeze = worst_over_a_minute(sea_state(3.0), BOAT);
    let gale = worst_over_a_minute(sea_state(12.0), BOAT);

    assert!(gale.heave_m > breeze.heave_m && gale.roll_rad > breeze.roll_rad, "{breeze:?} {gale:?}");
}

#[test]
fn a_ship_barely_moves_where_a_boat_rocks() {
    let sea = sea_state(10.0);

    let (boat, ship) = (worst_over_a_minute(sea, BOAT), worst_over_a_minute(sea, SHIP));

    assert!(ship.pitch_rad < boat.pitch_rad * 0.2 && ship.heave_m < boat.heave_m, "{boat:?} {ship:?}");
}

#[test]
fn a_boat_never_heaves_beyond_the_wave_height() {
    let sea = sea_state(12.0);

    assert!(worst_over_a_minute(sea, BOAT).heave_m <= sea.wave_height_m / 2.0 + 1e-4);
}

#[test]
fn small_water_caps_the_waves_whatever_the_wind() {
    assert!(sea_state(40.0).wave_height_m <= 1.0, "{:?}", sea_state(40.0));
}

#[test]
fn the_same_vessel_rocks_the_same_way_every_run() {
    let sea = sea_state(8.0);

    assert_eq!(vessel_motion(sea, BOAT, 12.3, 0.7), vessel_motion(sea, BOAT, 12.3, 0.7));
    assert_ne!(vessel_motion(sea, BOAT, 12.3, 0.7), vessel_motion(sea, BOAT, 12.3, 0.1));
}
