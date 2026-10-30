# Initial Discovery: KITTI outdoor demo scene

**Changeset**: [2026-10-30-kitti-demo.md](./2026-10-30-kitti-demo.md)
**Date**: 2026-10-30
**Passes**: 1

## Combined Conclusions

- **Registry is ready for a second format.** `DatasetSpec.dataset_format`
  exists (default `"euroc"`) but `ensure_dataset` rejects anything else.
  Extraction (`_extract`) copies `mav0/cam0|cam1|imu0` members; pairs are
  cam0/cam1 PNGs with identical `<t_ns>.png` names; calibration is read
  from `mav0/camN/sensor.yaml` (`intrinsics`, `resolution`, `T_BS`
  `data`, `distortion_coefficients`).
- **Display size is hard-coded 376×240** (`datasets.py` `DISPLAY_*`,
  `server.py` ×10, `page.py` canvas + `drawImage`, `StreamingRtabmapBackend`
  `width=376,height=240` defaults the demo never overrides, sidecar
  `jsonLong(..., 376/240)` fallbacks, `fetch_rtabmap_fixture.py`
  `OUTPUT_WIDTH`). KITTI 2011_09_26 rectified frames are 1242×375.
- **EuRoC-tuned depth constants.** Sidecar keyframe cap `p.z > 6.f`
  (`main.cpp`); overlay ramp `DEPTH_STOPS` 1/3/6 m (`server.py`); page
  dot size `point.d < 1.5`. KITTI: fx ≈ 721 px at 1242 wide, baseline
  ≈ 0.54 m → at 620 wide `fx·b ≈ 193 px·m` vs EuRoC's ≈ 25.
- **Playback rate** is the CLI `--fps` default `20.0` (`scripts/demo.py`);
  KITTI raw is ~10 Hz.
- **Batch mode needs IMU** (`SidecarRtabmapBackend(imu_yaml=…,
  imu_csv=…)`); KITTI raw has no `imu0` in EuRoC form.
- **KITTI raw access (checked 2026-10-30).** Direct S3 URLs answer
  200 without login: `…/raw_data/2011_09_26_drive_0009/2011_09_26_drive_0009_sync.zip`
  (1,791,264,044 B), `…/raw_data/2011_09_26_calib.zip` (4,068 B). Licence
  (cvlibs.net/datasets/kitti): "Creative Commons Attribution-NonCommercial-
  ShareAlike 3.0"; "made available for academic use only". The user
  accepted use with attribution, download-on-first-run, never bundled.

## Exploration 1: registry, display size and depth constants — 2026-10-30

**Agent**: parent Grep/Read, curl HEAD, WebFetch
**Scope**: what a KITTI scene needs from the demo pipeline

### Sequence

1. `scripts/demo.py --list-datasets` — one entry, `euroc-v1-01-easy`.
2. Read `src/surmap/demo/datasets.py` 1–260 — spec, cache, extraction, calibration.
3. Grep `DISPLAY_WIDTH|DISPLAY_HEIGHT|376|, 240|p.z > 6` in `src scripts deploy`.
4. Read `deploy/rtabmap-stream/main.cpp` 74–85, 170–200 — hello parsing.
5. curl HEAD on four KITTI drive zips and the 2011_09_26 calib zip.
6. WebFetch cvlibs KITTI raw page and KITTI home page — access and licence.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Grep | `DISPLAY_WIDTH\|DISPLAY_HEIGHT\|376\|, 240` | `src scripts deploy` | `datasets.py:35-36`, `page.py:40,84`, `server.py:263,306,415,451-462,510-511`, `streaming.py:210`, `main.cpp:176-177`, `fetch_rtabmap_fixture.py:73` |
| Grep | `p.z > 6` | `deploy` | `main.cpp:295` |

### Inspected files

#### `src/surmap/demo/datasets.py`

```python
@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    ...
    dataset_format: str = "euroc"
...
    if spec.dataset_format != "euroc":
        raise ValueError(f"unsupported dataset format: {spec.dataset_format}")
```

#### `src/surmap/demo/server.py`

```python
with Image.open(prepared.frame_path(channel, t_ns)) as frame:
    frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT)).convert("L").save(...)
```

### Findings

HEAD results: drive 0005 645,940,900 B; 0009 1,791,264,044 B; 0059
1,517,489,971 B; 0093 1,720,308,957 B; calib 4,068 B — all HTTP 200.
