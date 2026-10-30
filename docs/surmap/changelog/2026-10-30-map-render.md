# Rendered live floor plan and map-frame camera

**Date:** 2026-10-30
**Feature:** browser demo / streaming RTAB-Map backend

The floor plan is one server-rendered image of every map point (mean
grey per pixel, opacity rising with point density) inside a grow-only
extent shared with the page, replacing a 4,000-point stride sample that
picked different points on every update and made the map shimmer.

The sidecar sends each frame's map-corrected pose
(`getMapCorrection() · odom`), and the camera marker uses it: after
loop closures it stays on its trajectory instead of drifting off with raw
odometry (measured on NTU VIRAL sbs_01: up to 5.3 m before, 0.09 m
median / 0.37 m p95 after).

Verification: gates green (pytest 584 passed, 2 skipped); real-container
e2e green with map poses required. Whole sbs_01 flight: map events
27 ms median rendering ~1.09M points. With the corrected NTU calibration
the floor plan shows the plaza's facade and its columns.
