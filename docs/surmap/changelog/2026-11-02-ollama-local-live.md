# Fully local Ollama live scoring

**Date:** 2026-11-02
**Feature:** Mission demo

Made `mission_demo.py --live` runnable with no hosted service and no
API key: with `SURMAP_LIVE_OLLAMA=1`, a vision model served by a
local Ollama fills all three live roles — person boxes, per-object
labels, and the scene note — behind the existing ports. The model is
the operator's choice via `--ollama-model` or `SURMAP_OLLAMA_MODEL`;
no model name is baked in, and boxes are carried as rectangle mask
polygons (coarser than SAM masks, stated in the adapter). Verified
live against `gemma4:e4b-mlx` on the Mac SITL capture: the run wrote
`basis: "live"` with a local scene note and no hosted calls.
