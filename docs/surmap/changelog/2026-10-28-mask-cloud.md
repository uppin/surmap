# SAM masks projected onto the cloud

**Date:** 2026-10-28
**Feature:** Survey data APIs

A SAM polygon can now claim camera-frame cloud points.
`surmap.survey.mask_cloud.points_in_mask` keeps points whose pinhole
projection lies inside the polygon and inside the frame, drops points
at or nearer than 5 cm, and transforms the survivors into the map frame
with the RTAB-Map pose when one is supplied. An empty polygon claims
nothing. The points are a registration layer and are not written into
RTAB-Map.
