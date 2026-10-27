# Fixture: ETH3D `cables_2` stereo frames

Ten stereo pairs (every 10th frame) cut from the ETH3D SLAM dataset
sequence `cables_2`, downscaled to 640 px wide JPEGs for the CM5
real-stereo end-to-end tests. The full sequence is 98 frames of a
tabletop cable scene, recorded with a calibrated stereo rig
(baseline ≈ 0.0898 m); `calibration.json` carries the intrinsics scaled
to the fixture resolution plus the frame timestamps.

Source: ETH3D, *A Multi-View Stereo Benchmark with High-Resolution
Images and Multi-Camera Videos* (Schöps et al., CVPR 2017) —
https://www.eth3d.net/slam_datasets (`cables_2_mono.zip` +
`cables_2_stereo.zip`). ETH3D data is provided for non-commercial
research use; this fixture is test data for that purpose. Cite ETH3D
when using it beyond this repo's tests.

The pairs are **not rectified**: the right camera's principal point is
offset (≈ +27 px, +65 px at fixture size), which the reconstruction
compensates by principal-point alignment before block matching. That
is an approximation of true rectification and is one reason the e2e
asserts detection presence and sane depth ranges, not exact geometry.
