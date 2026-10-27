# CM5 stereo reconstruction

**Date:** 2026-10-27
**Type:** Feature
**Packages:** surmap

Added `surmap.survey.stereo` (`StereoRig`, `FrameImage`,
`decode_grayscale`, `StereoReconstructor` with left-right consistency
checking), wired it into `stream_survey` and the `cm5_main` default,
and added numpy + Pillow. Fixture: ten ETH3D `cables_2` pairs under
`tests/fixtures/eth3d_cables2/`. Verification: V1 fail→pass — unit
tests plus a real-socket e2e asserting scene batches on all ten
frames (4,187 points after dedup; 403 passed at wrap, gates clean).
