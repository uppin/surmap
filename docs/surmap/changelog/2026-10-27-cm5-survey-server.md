# CM5 survey server

**Date:** 2026-10-27
**Feature:** Survey data APIs

Exposed the CM5 as a ConnectRPC bidirectional server: raw stereo
frames and calibration in, incremental point batches tagged with a designation (a map-layer id), and
requested video channels out. Completed pairs drive RTAB-Map (through
its port) and per-object point sources; an unposed pair places no
points in the map.
