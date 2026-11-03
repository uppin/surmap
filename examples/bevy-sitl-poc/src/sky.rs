//! The manifest's HDRI as sky and image-based light on every camera.
//!
//! Bevy 0.18's procedural `Atmosphere` serves a single camera (its
//! buffer is written from `Query::single`), and this scene renders four
//! — chase, two eyes, overview — which must all see one sky. So the
//! equirectangular HDRI named in `scene.json` is baked into a cubemap
//! here at load time (no offline tool, no rebuild) and handed to each
//! camera as `Skybox` + `GeneratedEnvironmentMapLight`. The sun is put
//! where the HDRI's brightest texel is, so light and sky always agree.

use bevy::core_pipeline::Skybox;
use bevy::light::GeneratedEnvironmentMapLight;
use bevy::prelude::*;
use bevy::render::render_resource::{
    Extent3d, TextureDimension, TextureFormat, TextureViewDescriptor, TextureViewDimension,
};

/// The HDRI being loaded, and what it is baked with.
#[derive(Resource)]
pub struct SkySource {
    pub equirect: Handle<Image>,
    pub brightness: f32,
    pub baked: bool,
}

/// Cube face resolution of the baked sky.
const FACE: u32 = 512;

/// Unit direction (Bevy: x east, y up, -z north) for a cube texel, in
/// wgpu face order +X, -X, +Y, -Y, +Z, -Z.
pub fn cube_direction(face: u32, u: f32, v: f32) -> Vec3 {
    match face {
        0 => Vec3::new(1.0, -v, -u),
        1 => Vec3::new(-1.0, -v, u),
        2 => Vec3::new(u, 1.0, v),
        3 => Vec3::new(u, -1.0, -v),
        4 => Vec3::new(u, -v, 1.0),
        _ => Vec3::new(-u, -v, -1.0),
    }
    .normalize()
}

/// Equirect (u, v in 0..1) of a direction; u = 0.5 looks north (-z).
pub fn equirect_uv(dir: Vec3) -> Vec2 {
    let lon = dir.x.atan2(-dir.z);
    let lat = dir.y.clamp(-1.0, 1.0).asin();
    Vec2::new(0.5 + lon / std::f32::consts::TAU, 0.5 - lat / std::f32::consts::PI)
}

pub fn equirect_direction(uv: Vec2) -> Vec3 {
    let lon = (uv.x - 0.5) * std::f32::consts::TAU;
    let lat = (0.5 - uv.y) * std::f32::consts::PI;
    Vec3::new(lon.sin() * lat.cos(), lat.sin(), -lon.cos() * lat.cos())
}

/// IEEE half from f32 (round to nearest, finite HDR values only).
pub fn f16_bits(value: f32) -> u16 {
    let bits = value.to_bits();
    let sign = ((bits >> 16) & 0x8000) as u16;
    let exp = ((bits >> 23) & 0xff) as i32 - 127 + 15;
    let mant = bits & 0x7f_ffff;
    if exp <= 0 {
        return sign;
    }
    if exp >= 31 {
        return sign | 0x7bff;
    }
    let rounded = (mant + 0x1000) >> 13;
    if rounded == 0x400 {
        return sign | (((exp + 1) as u16) << 10);
    }
    sign | ((exp as u16) << 10) | rounded as u16
}

struct Equirect<'a> {
    texels: &'a [u8],
    width: u32,
    height: u32,
}

impl Equirect<'_> {
    fn rgb(&self, x: u32, y: u32) -> [f32; 3] {
        let i = ((y * self.width + x) * 16) as usize;
        let f = |k: usize| f32::from_le_bytes(self.texels[i + k * 4..i + k * 4 + 4].try_into().expect("4 bytes"));
        [f(0), f(1), f(2)]
    }

    fn sample(&self, dir: Vec3) -> [f32; 3] {
        let uv = equirect_uv(dir);
        let x = ((uv.x.rem_euclid(1.0)) * self.width as f32) as u32 % self.width;
        let y = ((uv.y * self.height as f32) as u32).min(self.height - 1);
        self.rgb(x, y)
    }

    /// The upper hemisphere's brightest texel, as a direction.
    fn sun(&self) -> Vec3 {
        let (mut best, mut at) = (f32::MIN, (0, 0));
        for y in 0..self.height / 2 {
            for x in 0..self.width {
                let [r, g, b] = self.rgb(x, y);
                let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
                if luma > best {
                    (best, at) = (luma, (x, y));
                }
            }
        }
        let uv = Vec2::new((at.0 as f32 + 0.5) / self.width as f32, (at.1 as f32 + 0.5) / self.height as f32);
        equirect_direction(uv)
    }
}

fn bake_cube(equirect: &Equirect) -> Image {
    let mut data = Vec::with_capacity((FACE * FACE * 6 * 8) as usize);
    for face in 0..6 {
        for y in 0..FACE {
            for x in 0..FACE {
                let u = 2.0 * (x as f32 + 0.5) / FACE as f32 - 1.0;
                let v = 2.0 * (y as f32 + 0.5) / FACE as f32 - 1.0;
                let [r, g, b] = equirect.sample(cube_direction(face, u, v));
                for c in [r, g, b, 1.0] {
                    data.extend_from_slice(&f16_bits(c).to_le_bytes());
                }
            }
        }
    }
    let mut image = Image::new(
        Extent3d { width: FACE, height: FACE, depth_or_array_layers: 6 },
        TextureDimension::D2,
        data,
        TextureFormat::Rgba16Float,
        bevy::asset::RenderAssetUsages::default(),
    );
    image.texture_view_descriptor = Some(TextureViewDescriptor {
        dimension: Some(TextureViewDimension::Cube),
        ..default()
    });
    image
}

/// Once the HDRI is in: bake it, light every camera with it, aim the sun.
pub fn bake_sky(
    mut commands: Commands,
    source: Option<ResMut<SkySource>>,
    mut images: ResMut<Assets<Image>>,
    cameras: Query<Entity, With<Camera3d>>,
    mut sun: Query<&mut Transform, With<DirectionalLight>>,
) {
    let Some(mut source) = source else { return };
    if source.baked {
        return;
    }
    let Some(hdri) = images.get(&source.equirect) else { return };
    let Some(texels) = hdri.data.as_deref() else { return };
    let size = hdri.texture_descriptor.size;
    if hdri.texture_descriptor.format != TextureFormat::Rgba32Float {
        error!("sky HDRI must load as Rgba32Float, got {:?}", hdri.texture_descriptor.format);
        source.baked = true;
        return;
    }
    let equirect = Equirect { texels, width: size.width, height: size.height };
    let towards_sun = equirect.sun();
    let baked = bake_cube(&equirect);
    let cube = images.add(baked);
    for camera in &cameras {
        commands.entity(camera).insert((
            Skybox { image: cube.clone(), brightness: source.brightness, ..default() },
            GeneratedEnvironmentMapLight {
                environment_map: cube.clone(),
                intensity: source.brightness,
                ..default()
            },
        ));
    }
    for mut transform in &mut sun {
        *transform = Transform::from_translation(towards_sun).looking_at(Vec3::ZERO, Vec3::Y);
    }
    source.baked = true;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_direction_survives_the_equirect_round_trip() {
        let dir = Vec3::new(0.3, 0.5, -0.8).normalize();

        let back = equirect_direction(equirect_uv(dir));

        assert!(back.abs_diff_eq(dir, 1e-5), "{back:?}");
    }

    #[test]
    fn the_centre_of_each_cube_face_looks_down_its_axis() {
        let axes = [Vec3::X, Vec3::NEG_X, Vec3::Y, Vec3::NEG_Y, Vec3::Z, Vec3::NEG_Z];

        let centres: Vec<Vec3> = (0..6).map(|f| cube_direction(f, 0.0, 0.0)).collect();

        assert_eq!(centres, axes);
    }

    #[test]
    fn halves_encode_one_two_and_a_half() {
        assert_eq!((f16_bits(1.0), f16_bits(2.0), f16_bits(0.5)), (0x3c00, 0x4000, 0x3800));
    }
}
