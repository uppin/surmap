# Segmentation cameras and model labels

**Date:** 2026-10-30
**Feature:** Machine 3 simulation

The stereo model now has instance and semantic cameras on the left
eye. `scripts/gz_label_models.py` labels survivors, cars, debris, and
water in the disaster block. The SITL dump can record those images and
the ground-truth camera pose (translation plus quaternion). One flight
exports to a `seg_bench` directory at 1 Hz. SurMap still does not send
flight commands.
