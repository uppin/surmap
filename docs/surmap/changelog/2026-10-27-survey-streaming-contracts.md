# Survey streaming contracts

**Date:** 2026-10-27
**Feature:** Survey data APIs

Defined the `surmap.survey.v1` wire contract for the Board and GPU APIs:
two bidirectional ConnectRPC streams (CM5 survey, station SAM) sharing a
config-first raw-frame input, point/video output tagged with a
designation (a map-layer id: 1 = RTAB-Map scene, 2/3 = video channels,
100 + track_id per object),
SAM detection vectors keyed by frame_id, and Python helpers for that id.
Removed the unavailable overstack epic tooling from the agent stack
workflow; stack topology now comes from the `gh stack` object and PR
bases, with waves recorded in changesets and PR bodies.
