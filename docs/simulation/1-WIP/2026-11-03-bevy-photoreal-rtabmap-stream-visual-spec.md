# Visual spec — photo-real Bevy disaster block

**Changeset:** `2026-11-03-bevy-photoreal-rtabmap-stream.md` · **Owner of every visual decision:** the
planner. The implementer builds exactly what is written here. Where this spec is silent, or a value
does not work, the implementer **does not choose**: it stops at the next checkpoint and reports what
it found (screenshot + one line). Numbers marked *(tune)* are first values the planner will adjust
after seeing screenshots.

## 0. Look in one sentence

A real-looking residential block **the morning after an earthquake**: low warm sun through dust haze,
cracked asphalt, mud around a flood pond, pancaked concrete buildings with tilted slabs and rubble
fans, intact buildings around the block for depth. Matte, dusty, desaturated — never glossy, never
toy-like. Survivors' high-vis clothes are the only saturated colour.

## 1. Review loop — how visual work proceeds

1. `--screenshot <dir> --at <t_s>` (native, `cargo run --release`) flies `survey-loop` to `t_s` and
   writes three PNGs, then exits:
   - `chase.png` — the chase camera at 1280×720;
   - `left.png` — the left eye, 640×480, exactly what is streamed (after the sensor model);
   - `overview.png` — 1280×720 from ENU (−40, −5, 35) looking at ENU (0, 45, 0), FOV 50° vertical.
2. Standard set: `--at 8`, `--at 20`, `--at 45`, written to `<scratchpad>/shots/<checkpoint>/t<t>/`.
3. **Checkpoints** (the implementer ends its turn with `STATUS: incomplete` and
   `REASON: visual checkpoint V<n>` after producing the set):
   - **V1** materials + layout (§3, §4) under the existing light;
   - **V2** light, sky, shadows, fog, exposure, tonemapping (§5);
   - **V3** GLB props + debris (§4.4, §6);
   - **V4** eye sensor model (§7) — `left.png` and its grey8 conversion side by side;
   - **V5** final, plus the same views in Chrome/WebGPU (`trunk serve`) to confirm parity.
4. The planner replies with numbered corrections; each is applied literally.

## 2. Assets — CC0 only, curated by the planner

Sources: **ambientCG** (textures, CC0) and **Poly Haven** (models, HDRIs, CC0). Nothing stylised
(no Kenney, Quaternius). Before any asset is pinned, the implementer builds a **shortlist**:
for each slot below, up to 4 candidates found through the sources' public listings (ambientCG
`https://ambientcg.com/api/v2/full_json?type=Material&q=<term>`, Poly Haven
`https://api.polyhaven.com/assets?t=models|textures`), each with its preview image downloaded to
`<scratchpad>/shortlist/<slot>/<id>.png`, plus `<scratchpad>/shortlist/index.md` (slot, id, source
page, licence, download URL, size). Then it stops (`REASON: asset shortlist`). The planner picks;
only picked assets go into `assets.lock.json`.

| Slot | Look | Search terms |
|---|---|---|
| `asphalt` | dark grey, worn, cracked, a few patches | asphalt, road |
| `ground` | dry-to-damp brown dirt with small stones | ground, dirt, soil |
| `mud` | wet dark mud near water | mud, ground wet |
| `concrete_slab` | weathered cast concrete, stains | concrete |
| `facade` | plain plaster/concrete facade for background buildings | facade, plaster, painted plaster |
| `rubble` (model) | broken concrete / brick rubble pile or chunks | rubble, debris, rock, brick |
| `props` (models) | barrels, crates, road barrier, tyre, dumpster, wooden pallet, fallen branch | as named |
| `vehicle` (model) | any photo-scanned / realistic car or van | car, van, vehicle |

### 2.1 Picks (planner, 2026-11-03, from the shortlist contact sheet)

All Poly Haven, CC0, 2K. Textures: download the individual JPGs `_diff_2k`, `_nor_gl_2k`,
`_arm_2k` (no zips). Models: the 2K `.gltf` entry file plus every file it references.

| Slot | Asset | Use |
|---|---|---|
| `asphalt` | `aerial_asphalt_01` | roads |
| `ground` | `rocks_ground_02` | block ground + apron |
| `mud` | `brown_mud_03` | pond rim |
| `concrete_slab` | `concrete_floor_worn_001` | pancaked slabs **and** rubble chunks and the debris scatter |
| `facade` | `white_plaster_02` | background buildings |
| `rubble` (model) | **none** — rejected (natural sandstone/moss rocks, not broken concrete) | chunks stay procedural (§4.1, §4.4) in `concrete_slab` |
| props | `concrete_road_barrier` ×5, `old_tyre` ×4, `Barrel_01` ×3 | §4.4 |
| vehicle | `covered_car` ×1 (the site nearest the pond) | the other two vehicle sites stay procedural (§4.3) |

**ARM maps** (Poly Haven `_arm`: R = ambient occlusion, G = roughness, B = metalness). Manifest
contract addition (planner): `PbrTextureSet` gains `arm: Option<String>`; when set it is used as
**both** `metallic_roughness_texture` and `occlusion_texture`, with `metallic = 1.0` and
`perceptual_roughness = 1.0` multipliers (B is real metalness here); `roughness` is used only when
`arm` is absent (then §3's `metallic = 0.0` rule applies). Models' own glTF materials are used as
loaded.

**Ground-truth objects**: every vehicle (`kind: "car"`) and every pancaked site's slab stack
(`kind: "collapsed_building"`, box = the slabs' bounds, rubble fan excluded).

Textures (for reference only — superseded by §2.1): the **2K-JPG** variants (members `_Color`, `_NormalGL`, `_Roughness`). Normal maps are
**OpenGL (+Y)**, Bevy's convention. If no CC0 realistic vehicle exists, cars stay procedural (§4.3) —
the implementer reports that, it does not substitute a stylised one.

Models may be `.glb` or `.gltf` (+ `.bin` + textures). Every file of a model is pinned in the lock
with its own sha256; the manifest names the entry file. Total fetched size ≤ 150 MB.

## 3. Materials — exact PBR setup

- Colour textures sRGB; normal and roughness **linear** (`ImageLoaderSettings { is_srgb: false }`).
- Every tiled material uses a sampler with `AddressMode::Repeat` on U and V, anisotropy 8, linear
  mip filtering. Tiling is by **world size**: `uv_transform = Affine2::from_scale(size_m * uv_scale)`
  where `uv_scale` is repeats per metre (manifest).
- Meshes that carry normal maps get tangents (`Mesh::generate_tangents`).
- ambientCG roughness is greyscale; Bevy reads roughness from G and metallic from B, so
  `metallic = 0.0` (multiplier) and `perceptual_roughness = 1.0` (multiplier) on every textured
  material — never leave metallic at 1.
- `reflectance`: 0.35 for dirt/mud/asphalt/concrete (dusty), 0.5 default elsewhere.

| Material | Slot | `uv_scale` (repeats/m) | Extra |
|---|---|---|---|
| Roads | `asphalt` | 0.25 | `base_color` tint `srgb(0.92, 0.90, 0.88)` (dust) |
| Ground | `ground` | 0.2 | — |
| Pond rim (4 m ring) | `mud` | 0.33 | — |
| Slabs | `concrete_slab` | 0.5 | tint `srgb(0.85, 0.83, 0.80)` |
| Background buildings | `facade` | 0.33 | per-building tint from §4.2 |
| Water | none | — | `base_color srgb(0.16, 0.15, 0.11)`, `perceptual_roughness 0.06`, `reflectance 0.5` |
| Survivor coats | none | — | orange `srgb(0.95, 0.42, 0.05)` / yellow `srgb(0.90, 0.80, 0.10)`, roughness 0.75 |
| Survivor body | none | — | `srgb(0.25, 0.22, 0.20)`, roughness 0.9 |

## 4. Layout (ENU metres; ground truth stays where it is)

The existing positions stay: avenue x = 0 (10 m wide), cross street y = 60, pond 32×36 at
(10, 38), helipad 8×8 at the origin, the 7 survivors at their ground-truth poses. The ground plane is
the 140×200 block, plus an untextured `ground`-material apron to 600×600 so the horizon is not an edge.

### 4.1 Pancaked buildings (the 8 existing slab sites)

Each site: footprint as today; **4 slabs**, 0.30 m thick, stacked with 0.15 m gaps crushed to 0
at one end; slab k (0 = bottom) offset by `(±0.4k, ±0.3k)` m and tilted `3° + 3k°` about a
horizontal axis — signs and axis from a seeded RNG (`seed = site index`), so it is deterministic.
A **rubble fan** on one long side: 25 chunks of `concrete_slab` material, boxes with sides
0.2–0.9 m, random yaw/tilt, spread over a 4 m half-disc (seeded). Colliders: box per slab and chunk.

### 4.2 Background buildings (new)

A ring of 14 intact buildings just outside the block's 140×200 edge, 3 m setback, footprints
10–16 m, heights 9–21 m (seeded), `facade` material with tints cycling
`srgb(0.86,0.83,0.78)`, `srgb(0.78,0.80,0.82)`, `srgb(0.88,0.80,0.70)`. Box colliders. They are
not ground-truth objects.

### 4.3 Vehicles (3 existing sites)

GLB if a vehicle is picked (§2), scaled to 4.4 m length, yaw as today. Otherwise procedural: body
4.4×1.8×0.8 m at 0.35 m clearance, cabin 2.2×1.6×0.6 m set 0.3 m back, 4 wheels (r 0.33 m, w
0.22 m); paint `metallic 0.5`, `perceptual_roughness 0.45`, `clearcoat 1.0`,
`clearcoat_perceptual_roughness 0.2`, colours `srgb(0.55,0.10,0.08)`, `srgb(0.60,0.62,0.64)`,
`srgb(0.10,0.18,0.30)`, then dust: base colour ×0.85. Glass `srgb(0.05,0.06,0.07)`, roughness 0.1.
Tyres `srgb(0.03,0.03,0.03)`, roughness 0.9. Every vehicle is a ground-truth object (`kind: "car"`).

### 4.4 Props and debris

- Props: 12 instances of the picked prop models, placed along the avenue kerbs and near slab sites
  (positions listed in `scene.json`, chosen by the planner from the V1 screenshots).
- Feronia ground scatter: replace the cuboid with the picked `rubble` model(s) if they are small
  chunks; density 28 → 40 *(tune)*, scale 0.3–1.0, only outside roads and the pond.

## 5. Light, sky, atmosphere, post

- **Sun**: `DirectionalLight { illuminance: light_consts::lux::RAW_SUNLIGHT, shadows_enabled: true }`,
  elevation 24°, azimuth 115° (clockwise from north) *(tune)*. Cascades:
  `CascadeShadowConfigBuilder { num_cascades: 4, first_cascade_far_bound: 10.0,
  maximum_distance: 180.0, overlap_proportion: 0.2 }`.
- **Sky + image-based light**: `Atmosphere::EARTH` with `AtmosphereSettings::default()` on every
  camera; `AtmosphereEnvironmentMapLight::default()` for ambient/specular. Remove `AmbientLight`
  and `ClearColor` as light sources. If either type is missing in Bevy 0.18.1, or fails on
  WebGPU, stop at the checkpoint and report it — do not improvise a sky.
- **Haze** (dust): `DistanceFog { color: srgba(0.74, 0.70, 0.62, 1.0),
  falloff: FogFalloff::from_visibility_colors(600.0, srgb(0.45,0.42,0.38), srgb(0.78,0.74,0.66)),
  directional_light_color: srgba(1.0, 0.90, 0.75, 0.4), directional_light_exponent: 24.0 }` *(tune)*.
- **Exposure**: `Exposure { ev100: 14.0 }` *(tune)* — fixed, identical on every camera. No
  `AutoExposure` (the two eyes must match frame to frame).
- **Tonemapping**: `Tonemapping::AgX` on every camera. **Bloom**: chase camera only,
  `Bloom { intensity: 0.05, ..Bloom::NATURAL }`.
- **Anti-aliasing**: chase camera `Msaa::Off` + `TemporalAntiAliasing` +
  `ShadowFilteringMethod::Temporal`; eye cameras `Msaa::Sample4`, no TAA,
  `ShadowFilteringMethod::Gaussian`. No SSAO anywhere (unsupported on WebGPU).
- Every camera `Hdr`. Eye cameras keep the calibrated projection; near 0.1, far 600.

## 6. Physics colliders for models

`collider: "box"` — cuboid from the loaded scene's mesh AABB (union, in instance space);
`"trimesh"` — Rapier trimesh from every mesh of the scene; `"none"` — no collider. Colliders are
added once the scene has spawned (not before the asset loads).

## 7. Eye sensor model (streamed frames only, both eyes)

Applied after tonemapping, as a full-screen pass on the eye cameras only, in display (sRGB) space,
values in 0–1:

- **Vignette**: multiply by `1 − 0.30 · r⁴`, `r` = distance from the principal point normalised so
  the image corner is 1.
- **Shot noise**: Gaussian, σ = `0.010 · sqrt(v)`; **read noise**: Gaussian, σ = `1.2 / 255`.
  Independent per pixel and per eye; seed = `frame_id · 2 + eye` (deterministic, so recordings
  repeat).
- No lens distortion, no blur, no chromatic aberration (calibration declares zero distortion).
- Then quantise to 8 bits; the grey8 conversion is `wire::bgra_to_gray8` on these bytes.

## 8. In-page overlay (Bevy UI)

- Bevy's default font has no `·`, `—`, `°` glyphs (baseline shows □). Overlay strings are ASCII:
  separators `" | "`, `deg` for degrees.
- Status line gains RTAB-Map state from the bridge:
  `RTAB-Map: tracking | frames 412 | posed 405 | keyframes 9 | dropped 0`, or
  `RTAB-Map: LOST` in `srgb(0.95, 0.35, 0.25)`, or `RTAB-Map: not connected` in grey
  `srgb(0.6, 0.6, 0.6)`. Text colour otherwise unchanged.
- The calibration panel's last line becomes `streaming to <bridge url>` or `not streaming`.
- The HTML header copy "Frames stay in this page — nothing is sent to a backend." becomes
  "Stereo frames stream to the local RTAB-Map bridge when `?bridge=` is set."

## 9. What "done" looks like (planner's checklist at V5)

- No flat-coloured surface larger than 1 m² anywhere in the eye view except water and paint.
- Shadows on the ground from slabs, cars and the drone; no shadow acne or peter-panning at t = 20.
- Horizon: haze blends the apron into the sky; no visible ground edge in `overview.png`.
- `left.png` grey histogram uses ≥ 150 of 256 levels; texture detail visible on asphalt at 10 m.
- Chrome/WebGPU and native screenshots match in exposure and colour within eyeballing.
