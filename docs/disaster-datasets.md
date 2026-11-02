# Disaster datasets (Boreal Forest Fire, NOAA ERI 2025)

`scripts/download_disaster_data.py` downloads two openly licensed disaster
datasets into a local cache:

| Subcommand | Dataset | Licence | Cache (default) |
|---|---|---|---|
| `boreal` | Boreal Forest Fire: UAV-collected wildfire detection and smoke segmentation (Finland) | CC BY 4.0 | `~/.cache/surmap/boreal-fire` |
| `noaa` | NOAA Emergency Response Imagery of the January 2025 Eaton and Palisades fires | CC0-1.0 | `~/.cache/surmap/noaa-eri-2025` |

`--cache-dir` (or `SURMAP_BOREAL_CACHE` / `SURMAP_NOAA_ERI_CACHE`) picks
another folder. Nothing is committed or re-hosted. Each cache folder gets an
`ATTRIBUTION.md` with the licence and credit text below.

The code is in `src/surmap/datasets/`. The offline tests are in
`tests/test_datasets_disaster.py` and use fake transports, so they open no
socket. Downloads use `urllib` only, with no extra dependencies.

Common behaviour:

- `--dry-run` (alias `--list`) prints the files, their sizes, and how much is
  still missing. It writes nothing.
- Reruns skip files that are already cached with the right size.
- A file is written as `<name>.part` and renamed only after its size matches,
  and its checksum too when the source publishes one (SHA-256 for Boreal,
  MD5 for NOAA objects with a single-part ETag).
- NOAA `.part` files are resumed with an HTTP range request. Fairdata
  ignores ranges, so a Boreal `.part` file starts again from zero.
- A failed file is retried twice, after 2 s and then 4 s.

## Boreal Forest Fire (Fairdata, CC BY 4.0)

Drone (DJI Phantom 4) 4K video and frames of smoke from prescribed burns in
Finnish boreal forest at four sites: Evo, Heinola, Karkkila and Ruokolahti.
Published by the Finnish Geospatial Research Institute (FGI, National Land
Survey of Finland) with the University of Jyväskylä, on
[Fairdata Etsin](https://etsin.fairdata.fi/dataset/1dce1023-493a-4d63-a906-f2a44f831898),
open access with no sign-up. Data descriptor:
[Scientific Data 12, 1419 (2025)](https://www.nature.com/articles/s41597-025-05634-0).

| `--subset` | Folder | Content | Files | Size |
|---|---|---|---|---|
| `segmentation` (default) | `Boreal-Forest-Fire-Subset-C` | Frames with smoke masks: `images/`, YOLO `labels/`, `sam_masks/` (train/valid/test), hand-drawn `manual_masks/` (test only) | 4,392 | 483.8 MB |
| `bbox` | `Boreal-Forest-Fire-Subset-A` | Frames with bounding-box labels, per site plus `Empty` (no smoke) | 9,909 | 13.1 GB |
| `videos` | `Boreal-Forest-Fire-Subset-B` | 30 s 4K clips (about 0.4 GB each), with `Video-Ground-Truth/` smoke yes/no tables | 290 | 111.5 GB |
| `notebook` | `Visualisation-And-Coordinate-Conversion-Notebook` | Example notebook | 1 | 8.2 KB |
| (whole dataset) | | | 14,592 | 125.1 GB |

Sizes come from the live Metax listing (`boreal --sizes`), as of
2 November 2026. The `segmentation` `test` split is 160 files (13.1 MB).

```bash
S="uv run python scripts/download_disaster_data.py"
$S boreal --sizes                              # per-subset file count and size
$S boreal --package                            # whole segmentation subset, one 479 MB zip
$S boreal --split test                         # segmentation test split, 160 files, 13.1 MB
$S boreal --split test --limit 5               # 5 test frames with their labels and masks
$S boreal --videos 2 --dry-run                 # 2 clips + ground truth, 808.6 MB
$S boreal --subset bbox --site evo --limit 50  # 50 Evo frames with box labels
```

`--limit N` counts samples, not files: a frame keeps its label and masks,
and a clip counts once. Samples are taken in natural name order. `--site`
filters `bbox` and `videos`. `--split` filters `segmentation`.

### How the download works

1. The file list, with sizes and SHA-256 checksums, comes from the public
   Metax v3 API:
   `https://metax.fairdata.fi/v3/datasets/1dce1023-493a-4d63-a906-f2a44f831898/files?pagination=false`
   (about 8 MB of JSON).
2. For each file, `POST https://etsin.fairdata.fi/api/download/authorize`
   with `{"cr_id": "<dataset id>", "file": "<pathname>"}` returns a signed
   `https://download.fairdata.fi/download?token=...` URL. The Etsin web page
   uses this same anonymous call for open datasets. Each URL works once.
3. The file is streamed and SHA-256 checked against Metax.

Fairdata's service is slow per request: about 1 s to authorize and about
2 s to the first byte. File by file, the 4,392-file segmentation subset
would take hours. `--package` instead uses one of the zips that Fairdata
already has ready for a whole subset (listed at
`GET https://etsin.fairdata.fi/api/download/requests?cr_id=<dataset id>`).
It authorizes the zip with `{"cr_id": ..., "package": "<zip name>"}`,
SHA-256 checks it against Fairdata's package checksum, unpacks it with
every member size checked against Metax, and deletes it (`--keep-package`
keeps it). Ready-made zips, as of 2 November 2026: `segmentation`
479.0 MB, `bbox` 13.1 GB, `videos` 111.6 GB, `notebook` 2.9 KB.
`--package` never asks Fairdata to build a new zip. If none exists for a
subset, it says so, and the per-file mode still works. In a test on the
box, the segmentation zip downloaded and unpacked in about 16 s.

These Etsin endpoints are the ones its web UI uses. They are not a
documented public API and could change.

### Attribution (CC BY 4.0)

> Pesonen, J., Raita-Hakola, A.-M., Joutsalainen, J., Hakala, T., Akhtar, W.,
> Karjalainen, V., Koivumäki, N., Markelin, L., Suomalainen, J., Alves de
> Oliveira, R., Pölönen, I., Honkavaara, E. (2025). "Boreal Forest Fire:
> UAV-collected Wildfire Detection and Smoke Segmentation Dataset". Finnish
> Geospatial Research Institute FGI, National Land Survey of Finland.
> Fairdata, https://doi.org/10.23729/fd-72c6cf74-b8eb-3687-860d-bf93a1ab94c9.
> Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
>
> Data descriptor: Scientific Data 12, 1419 (2025),
> https://doi.org/10.1038/s41597-025-05634-0

## NOAA Emergency Response Imagery, 2025 California fires (CC0-1.0)

NOAA NGS Remote Sensing Division aerial imagery of the Eaton and Palisades
burn areas, flown on 28 January 2025 at about 7.5 cm ground sample distance
([NOAA 2025 ERI index](https://storms.ngs.noaa.gov/storms/2025_eri/index.html)).
NOAA's metadata ([InPort item 74399](https://www.fisheries.noaa.gov/inport/item/74399))
gives the licence as CC0-1.0, with data access constraints "None".

The mosaic is cut into Cloud-Optimized GeoTIFF tiles (RGBA, WGS 84, 18,829 px
square) under `s3://noaa-eri-pds/2025_California_Fires/20250128a_RGB/`. The
tiles are read over anonymous HTTPS
(`https://noaa-eri-pds.s3.amazonaws.com/?list-type=2&prefix=...`), with no
AWS credentials or boto3. Each tile name is its north-west corner, and each
tile covers 45″ (0.0125°) a side. For example, `20250128aC1180215w341200n.tif`
starts at 118°02′15″W, 34°12′00″N. Tiles range from 6.4 MB to 1.65 GB.

The same NOAA page also links the Maxar Open Data imagery of the fires
(CC BY-NC 4.0). This tool does not use it, only NOAA's own tiles.

| `--fire` | Area (W, S, E, N) | Tiles | Size |
|---|---|---|---|
| `palisades` | −118.7625, 34.0125, −118.4375, 34.1 | 165 | 200.6 GB |
| `eaton` | −118.2, 34.15, −117.975, 34.225 | 91 | 92.6 GB |
| (all GeoTIFF tiles) | | 256 | 293.1 GB |

The two areas are the extents of the two tile clusters in the bucket,
computed from the tile names, as of 2 November 2026. The same flight folder
also holds 772 un-mosaicked frames under `raw/` (32.4 GB), which this tool
does not download. NOAA's two convenience tarballs under
`2025_California_Fires/downloads/` total 60.7 GB.

```bash
S="uv run python scripts/download_disaster_data.py"
$S noaa --fire palisades --limit 20 --dry-run          # 20 tiles, 10.9 GB
$S noaa --fire palisades --limit 20
$S noaa --fire eaton --limit 2 --max-tile-mb 15        # 2 small edge tiles, 16.4 MB
$S noaa --bbox -118.56 34.03 -118.52 34.06 --dry-run   # tiles touching a box
```

Tiles are ordered north to south, then west to east. `--limit N` caps the
tile count, and `--max-tile-mb` skips large tiles. `--bbox` (WGS 84
degrees) overrides the `--fire` area. Every run also fetches the small tile
index shapefile (`tile_index_20250128a_RGB.{shp,shx,dbf,prj}`, about 100 KB).

### Attribution (CC0-1.0)

CC0 asks for no attribution. NOAA asks for credit for unaltered data, and
for no claim of endorsement by or affiliation with NOAA:

> National Geodetic Survey, 2026: 2025 NOAA NGS Emergency Response Imagery:
> California Fires [InPort metadata record],
> https://www.fisheries.noaa.gov/inport/item/74399. Imagery acquired
> 28 January 2025 by the NOAA NGS Remote Sensing Division. CC0-1.0.

NOAA's metadata also notes that conditions may have changed since the
flight, and that the data should not be used for critical applications
without understanding their limitations.
