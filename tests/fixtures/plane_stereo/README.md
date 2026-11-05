# Fixture: photo-textured plane stereo pairs

Ten 640×480 stereo pairs for the stereo reconstruction tests and the CM5 end-to-end test.
`scripts/render_plane_stereo_fixture.py` renders them deterministically. Each pair is the ELP
rig (fx 381.36, 0.07 m baseline) looking at a tilted plane about 0.45 m away, so every
pixel's true depth is known. `calibration.json` records the rig and each pair's plane
(`plane_normal · p = plane_offset_m` in the left camera frame).

The right camera's principal point sits (+10, +12) px from the left one's, as on an
unrectified rig. The tests pass that offset to `StereoReconstructor(alignment_offset=...)`.
Without it, about 25% of the points land on the plane; with it, more than 99%.

Texture: Poly Haven `rocks_ground_02` (CC0-1.0, https://polyhaven.com/a/rocks_ground_02),
pinned in `examples/bevy-sitl-poc/assets/assets.lock.json`. The rendered frames are
Apache-2.0 with the rest of the repository.

Regenerate:

```bash
uv run python scripts/fetch_sim_assets.py
uv run python scripts/render_plane_stereo_fixture.py
```
