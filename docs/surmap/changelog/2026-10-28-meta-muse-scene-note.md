# Meta Model API scene note

**Date:** 2026-10-28
**Feature:** Hackathon credits — hosted Muse Spark scene note

Added `MetaMuseSceneClient` in `surmap.labelling`. One call posts a
mapped JPEG and the on-board labels to `POST
https://api.meta.ai/v1/responses` as `muse-spark-1.3`, with
`reasoning.effort` `low`, and returns the assistant `output_text`.
The prompt asks for a civilian search-and-rescue description of the
mapped area and for no flight advice. The key stays in
`MODEL_API_KEY`. A live call runs only when `SURMAP_LIVE_META=1`.
