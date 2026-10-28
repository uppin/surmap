# Semantic map snapshot

Status: the file export of a semantic map. GeoJSON stays an open
decision (`docs/architecture.md` §12). This JSON file is the export
until that decision is made. A map question-answering feature and a
3D viewer read this document; they do not invent a second layout.

Produced by `surmap.map.snapshot.write_snapshot`. Read back with
`read_snapshot`. Built with `build_snapshot` from `ObjectTrack3D`
tracks and `GpsCheckpoint` fixes. No network.

## File

UTF-8 JSON, one object. `write_snapshot` pretty-prints with a trailing
newline and does not escape non-ASCII characters.

```json
{
  "schema": "surmap.semantic_map_snapshot.v1",
  "origin": {
    "t_ns": 1000000000,
    "lat": 54.0,
    "lon": 25.0,
    "alt": 100.0,
    "accuracy_m": 2.5
  },
  "landmarks": [],
  "dynamic": []
}
```

`schema` is exactly `surmap.semantic_map_snapshot.v1`. `read_snapshot`
rejects any other value.

`origin` is the earliest GPS fix by `t_ns`, or `null` when the session
has no fix. Ties keep the earlier fix in input order.

| Field | Type | Meaning |
|---|---|---|
| `t_ns` | integer | Fix time, monotonic nanoseconds |
| `lat` | number | Degrees north |
| `lon` | number | Degrees east |
| `alt` | number | Metres |
| `accuracy_m` | number | Fix accuracy, metres |

## Layers

`landmarks` and `dynamic` use the same object shape. They are not
merged, and there is no combined point list.

| Array | What is in it |
|---|---|
| `landmarks` | Tracks `classify_motion` calls `static` or `unknown` |
| `dynamic` | Tracks `classify_motion` calls `moving` |

`classify_motion` is called at build time. A `motion` flag already
stored on the track is not used. The default threshold is 0.5 m
between the first and last centroid; a shift of exactly 0.5 m stays
`static`. A track with no observations is omitted. Duplicate
`track_id`s raise `ValueError`.

Both arrays are ordered by numeric track id.

A moving track's `xyz`, `observations`, and `mask_points` exist only
on its `dynamic` entry.

## Landmark object

```json
{
  "id": "7",
  "xyz": {"x": 0.0, "y": 0.0, "z": 0.0},
  "lat": 54.0,
  "lon": 25.0,
  "alt": 100.0,
  "label": "roof",
  "description": "flat roof",
  "model_id": "baseten/muse-spark-open",
  "motion": "static",
  "t_ns": 1250000000,
  "anchor_t_ns": 1000000000,
  "offset_ns": 250000000,
  "observations": [
    {"t_ns": 1000000000, "xyz": {"x": 0.0, "y": 0.0, "z": 0.0}},
    {"t_ns": 1250000000, "xyz": {"x": 0.0, "y": 0.0, "z": 0.0}}
  ],
  "mask_points": [
    {"x": 0.2, "y": 0.0, "z": 0.0}
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Decimal `track_id`. Stable for that track in the session, unique in the file. Not a random id. |
| `xyz` | `{x,y,z}` | Latest observation centroid, metres in the map frame |
| `lat`, `lon`, `alt` | number or `null` | WGS84 position. `null` when `origin` is `null` |
| `label` | string | Track label |
| `description` | string | Caller-supplied text. `""` when omitted |
| `model_id` | string | Model that produced the label. `""` when omitted |
| `motion` | string | `static`, `moving`, or `unknown` |
| `t_ns` | integer | Time of the latest observation |
| `anchor_t_ns` | integer or `null` | `t_ns` of the nearest GPS fix. `null` when there is no fix |
| `offset_ns` | integer or `null` | `t_ns - anchor_t_ns`, signed. `null` when there is no fix |
| `observations` | array | Every sighting, input order: `{t_ns, xyz}` |
| `mask_points` | array or `null` | Map-frame xyz cloud. `null` if the caller did not attach one |

`xyz` axes, and every `mask_points` / `observations` xyz, are map-frame
metres: **x east, y north, z up**, relative to `origin`.

`mask_points` is how a mask cloud (map-frame points that fell inside a
SAM polygon) is attached. The snapshot does not compute the cloud.
`null` means no cloud was attached. `[]` means a cloud was attached
and contained no points. Points stay on the entry they were attached
to, including a `dynamic` entry.

## Anchoring

Two different uses of GPS:

1. **Origin.** The earliest fix. `xyz` is an east/north/up offset from
   that fix. `lat` / `lon` / `alt` are that origin plus the offset.
   They are not the nearest fix's coordinates.
2. **Time association.** The fix with the smallest absolute `t_ns`
   difference. `offset_ns` is the signed gap. An equal distance uses
   the earlier fix. The position is not snapped to that fix.

Conversion, with `xyz` in metres:

```text
lat = origin.lat + y / 111320
lon = origin.lon + x / (111320 * cos(origin.lat in radians))
alt = origin.alt + z
```

111320 m is one degree of latitude in this file. Longitude uses the
same length scaled by the cosine of the origin latitude. At the
equator, 111320 m east and 111320 m north is one degree each. Relative
geometry that is more precise than this stays in `xyz`.

With no fix, `origin` is `null` and every landmark's `lat`, `lon`,
`alt`, `anchor_t_ns`, and `offset_ns` are `null`. `xyz` is still
present.

## Integers

`t_ns`, `anchor_t_ns`, and `offset_ns` are JSON integers, not strings.
Python's decoder keeps them exact. A consumer that parses JSON numbers
as IEEE-754 doubles cannot represent every integer above 2^53−1
(about 104 days of nanoseconds). A flight-length monotonic timestamp
fits in that range; a nanosecond Unix timestamp does not. These values
are monotonic-clock nanoseconds, the same clock as `GpsCheckpoint.t_ns`.

## What a viewer can assume

- One `id` identifies one track in this file, in either array, not both.
- `motion` on a `landmarks` entry is `static` or `unknown`. `motion` on
  a `dynamic` entry is `moving`.
- `mask_points`, when present, are in the same frame as `xyz`.
- The file is a snapshot. Readers do not write it back in place.
