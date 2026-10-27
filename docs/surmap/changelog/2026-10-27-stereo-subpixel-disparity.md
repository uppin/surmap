# Stereo subpixel disparity

**Date:** 2026-10-27
**Feature:** Survey data APIs

`StereoReconstructor` matched at integer disparity, which quantizes
depth into shells: at the default 160 px matching width on a
driving-scale rig (f·B ≈ 55 px·m at 1/7 scale) adjacent shells sit
2–9 m apart at car range, so reconstructed points jitter metres
frame to frame and no static-reference differencing can hold.
Disparity is now refined to subpixel precision by parabolic
interpolation of the matching-cost curve around the integer
minimum, and the matching width is a constructor parameter
(`match_width_px`, default 160 = previous behaviour) so callers
with longer-range rigs can trade speed for finer depth shells.

Proven by a synthetic fractional-disparity pair whose median depth
must land on the true plane rather than either neighbouring
integer shell, and by the KITTI moving-object E2E on the
`#moving-objects` stack, which motivated the fix.
