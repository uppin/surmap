# 2026-11-03 — Fisheye camera profiles and per-profile render tests

**Category:** Deferred scope (developer request during PR #89)
**Source:** PR #89, stack `#sim-disaster` n1
**Packages:** examples/bevy-sitl-poc, deploy/rtabmap-stream
**Consent:** Developer, 2026-11-03: "let's wrap the PR with TODO and we'll address the correctness in next PRs".
**Priority:** 2
**Status:** Open

## What is left

- Render `fisheye_equidistant` profiles: a wide pinhole pass remapped through the
  profile's Kannala–Brandt model (`CameraProfile::unproject` is implemented and tested);
  today such a profile is refused at load (`rig.rs`).
- Native GPU render tests per profile: markers at known 3D points must land within 1 px
  of `CameraProfile::project` (pinhole, off-centre pinhole, fisheye); gated like the
  docker e2es because CI has no GPU.
- The sidecar rectifies with OpenCV's pinhole `stereoRectify`; fisheye input needs
  `cv::fisheye::stereoRectify` in `deploy/rtabmap-stream/main.cpp`.
- The 2.5–2.7 % odometry drift on the 13 m block leg is not baseline-limited (30 cm gives
  the same, with the opposite sign); investigate alongside, with profiles varied in JSON.
