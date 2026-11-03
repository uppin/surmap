//! Browser → bridge wire format for the stereo stream.
//!
//! Every message is `u32` little-endian header length, a compact JSON
//! header, then (pairs only) the left and right grey8 payloads of
//! `width * height` bytes each. The goldens in
//! `tests/fixtures/bevy_sim_wire/` pin the bytes for both languages.

#![allow(dead_code)]

use bevy::math::{Quat, Vec3};
use serde::Serialize;

use crate::calibration::CameraProfile;

/// A ground-truth box in ENU metres, sent once in the hello.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct GroundTruthObject {
    pub id: String,
    pub kind: String,
    pub min_enu: [f32; 3],
    pub max_enu: [f32; 3],
}

/// The header of one stereo pair.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PairHeader {
    pub frame_id: u64,
    pub t_ns: u64,
    pub width: u32,
    pub height: u32,
    /// Rig centre in ENU and the rotation taking the rig's
    /// forward-left-up body frame to ENU, `[x, y, z, qx, qy, qz, qw]`.
    pub pose_enu: [f64; 7],
}

#[derive(Serialize)]
struct HelloHeader<'a> {
    #[serde(rename = "type")]
    kind: &'static str,
    camera: &'a CameraProfile,
    objects: &'a [GroundTruthObject],
}

#[derive(Serialize)]
struct PairHeaderJson {
    #[serde(rename = "type")]
    kind: &'static str,
    frame_id: u64,
    t_ns: u64,
    width: u32,
    height: u32,
    encoding: &'static str,
    pose_enu: [f64; 7],
}

fn frame(header_json: String, payloads: &[&[u8]]) -> Vec<u8> {
    let header = header_json.as_bytes();
    let mut out =
        Vec::with_capacity(4 + header.len() + payloads.iter().map(|p| p.len()).sum::<usize>());
    out.extend_from_slice(&(header.len() as u32).to_le_bytes());
    out.extend_from_slice(header);
    for payload in payloads {
        out.extend_from_slice(payload);
    }
    out
}

/// The session opener: the whole camera profile (the bridge derives
/// RTAB-Map's calibration from it) and the ground-truth objects.
pub fn encode_hello(camera: &CameraProfile, objects: &[GroundTruthObject]) -> Vec<u8> {
    let header = HelloHeader { kind: "hello", camera, objects };
    frame(
        serde_json::to_string(&header).expect("hello header serializes"),
        &[],
    )
}

/// One stereo pair; panics if a payload is not `width * height` bytes.
pub fn encode_pair(header: &PairHeader, left_gray: &[u8], right_gray: &[u8]) -> Vec<u8> {
    let expected = (header.width as usize) * (header.height as usize);
    assert!(
        left_gray.len() == expected && right_gray.len() == expected,
        "payload must be width * height bytes: left {} right {} expected {expected}",
        left_gray.len(),
        right_gray.len()
    );
    let json = PairHeaderJson {
        kind: "pair",
        frame_id: header.frame_id,
        t_ns: header.t_ns,
        width: header.width,
        height: header.height,
        encoding: "gray8",
        pose_enu: header.pose_enu,
    };
    frame(
        serde_json::to_string(&json).expect("pair header serializes"),
        &[left_gray, right_gray],
    )
}

/// BGRA8 (as read back, rows `row_bytes` apart) → tightly packed grey8,
/// BT.601 luma `(299 R + 587 G + 114 B + 500) / 1000` on the stored bytes.
pub fn bgra_to_gray8(bgra: &[u8], width: u32, height: u32, row_bytes: u32) -> Vec<u8> {
    let (w, h, stride) = (width as usize, height as usize, row_bytes as usize);
    let mut out = Vec::with_capacity(w * h);
    for row in 0..h {
        let start = row * stride;
        for col in 0..w {
            let i = start + col * 4;
            let (b, g, r) = (
                u32::from(bgra[i]),
                u32::from(bgra[i + 1]),
                u32::from(bgra[i + 2]),
            );
            out.push(((299 * r + 587 * g + 114 * b + 500) / 1000) as u8);
        }
    }
    out
}

/// The rig's Bevy transform (x right/east, y up, -z north; the rig looks
/// down its own -z) as the wire's ENU pose of its forward-left-up frame.
pub fn rig_pose_enu(translation: Vec3, rotation: Quat) -> [f64; 7] {
    use bevy::math::{DMat3, DQuat, DVec3};
    let to_enu = |v: Vec3| DVec3::new(f64::from(v.x), f64::from(-v.z), f64::from(v.y));
    let forward = to_enu(rotation * Vec3::NEG_Z);
    let left = to_enu(rotation * Vec3::NEG_X);
    let up = to_enu(rotation * Vec3::Y);
    let quat = DQuat::from_mat3(&DMat3::from_cols(forward, left, up));
    [
        f64::from(translation.x),
        f64::from(-translation.z),
        f64::from(translation.y),
        quat.x,
        quat.y,
        quat.z,
        quat.w,
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    const HELLO_GOLDEN: &[u8] = include_bytes!("../../../tests/fixtures/bevy_sim_wire/hello.bin");
    const PAIR_GOLDEN: &[u8] = include_bytes!("../../../tests/fixtures/bevy_sim_wire/pair.bin");

    fn a_car() -> GroundTruthObject {
        GroundTruthObject {
            id: "car-1".into(),
            kind: "car".into(),
            min_enu: [1.0, 2.0, 0.0],
            max_enu: [3.0, 6.5, 1.5],
        }
    }

    fn a_tiny_pair_header() -> PairHeader {
        PairHeader {
            frame_id: 7,
            t_ns: 700_000_000,
            width: 4,
            height: 2,
            pose_enu: [1.0, 3.0, 2.0, 0.0, 0.0, 0.0, 1.0],
        }
    }

    /// Positions equal; quaternions equal up to sign (q and -q are one rotation).
    fn assert_pose_close(actual: [f64; 7], expected: [f64; 7]) {
        let near = |a: &[f64], e: &[f64]| a.iter().zip(e).all(|(a, e)| (a - e).abs() < 1e-5);
        let flipped: Vec<f64> = expected[3..].iter().map(|v| -v).collect();
        let rotation = near(&actual[3..], &expected[3..]) || near(&actual[3..], &flipped);
        assert!(
            near(&actual[..3], &expected[..3]) && rotation,
            "pose {actual:?} != {expected:?}"
        );
    }

    #[test]
    fn hello_matches_the_shared_golden_bytes() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/assets/cameras/elp-stereo-pinhole.camera.json");
        let rig = CameraProfile::from_json(&std::fs::read_to_string(path).expect("profile")).expect("valid");

        let message = encode_hello(&rig, &[a_car()]);

        assert_eq!(message, HELLO_GOLDEN);
    }

    #[test]
    fn pair_matches_the_shared_golden_bytes() {
        let left: Vec<u8> = (0..8).collect();
        let right: Vec<u8> = (8..16).collect();

        let message = encode_pair(&a_tiny_pair_header(), &left, &right);

        assert_eq!(message, PAIR_GOLDEN);
    }

    #[test]
    #[should_panic(expected = "width * height")]
    fn pair_refuses_a_payload_of_the_wrong_size() {
        encode_pair(&a_tiny_pair_header(), &[0; 7], &[0; 8]);
    }

    #[test]
    fn grey_conversion_weights_red_green_and_blue_like_bt601() {
        let pure_red_green_blue_white = [
            0, 0, 255, 255, 0, 255, 0, 255, 255, 0, 0, 255, 255, 255, 255, 255,
        ];

        let grey = bgra_to_gray8(&pure_red_green_blue_white, 4, 1, 16);

        assert_eq!(grey, vec![76, 150, 29, 255]);
    }

    #[test]
    fn grey_conversion_skips_the_row_padding_of_a_readback() {
        let mut padded = vec![9_u8; 2 * 12];
        padded[0..8].copy_from_slice(&[10, 10, 10, 255, 20, 20, 20, 255]);
        padded[12..20].copy_from_slice(&[30, 30, 30, 255, 40, 40, 40, 255]);

        let grey = bgra_to_gray8(&padded, 2, 2, 12);

        assert_eq!(grey, vec![10, 20, 30, 40]);
    }

    #[test]
    fn an_unrotated_rig_looks_north_in_enu() {
        let pose = rig_pose_enu(Vec3::new(1.0, 2.0, -3.0), Quat::IDENTITY);

        let half = std::f64::consts::FRAC_1_SQRT_2;
        assert_pose_close(pose, [1.0, 3.0, 2.0, 0.0, 0.0, half, half]);
    }

    #[test]
    fn a_rig_yawed_left_by_ninety_degrees_looks_west_in_enu() {
        let yawed = Quat::from_rotation_y(std::f32::consts::FRAC_PI_2);

        let pose = rig_pose_enu(Vec3::ZERO, yawed);

        assert_pose_close(pose, [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]);
    }
}
