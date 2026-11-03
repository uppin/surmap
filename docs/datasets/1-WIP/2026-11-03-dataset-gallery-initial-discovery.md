# Initial Discovery — Dataset Gallery

## Exploration 1

- `src/surmap/demo/datasets.py`: `DATASETS` registry (`DatasetSpec`), `ensure_dataset`,
  `cached_dataset`, `_extract_kitti_raw` (grey `image_00/01` only, ignores `image_02/03`
  colour and `oxts/` GPS), `PreparedDataset.frame_path` (EuRoC layout).
- `src/surmap/demo/server.py`: `DemoPlayer` plays EuRoC-layout pairs; `_display_jpeg`
  always converts to `L` (grey); `make_demo_server(catalog=...)`; `/datasets` JSON.
- `src/surmap/agent/`: tools are proto rpcs in `proto/surmap/agent/v1/survey_tools.proto`,
  contracts via `src/surmap/agent/contracts.py`, handlers in
  `src/surmap/agent/tools/handlers.py` over `SurveyWorkspace` (`tools/port.py`),
  default adapter `DemoWorkspace` (`tools/workspace.py`). Existing tools:
  `list_demos`, `run_demo`, `prompt_sam`, `find_objects`, `get_frame`, ...
- `web/agent-chat/`: React chat (`ChatPage.tsx`), port in `src/ports.ts`, Connect
  adapter in `src/adapters/connect-chat.ts`, generated TS in `src/gen/`.
- KITTI raw sync zip contains `image_00/01` grey, `image_02/03` colour, `oxts/` GPS.

## Combined Conclusions

Gallery belongs in the chat app (user decision), driven by an extensible
catalogue in `surmap.demo.datasets` + `surmap.demo.gallery`. KITTI ships as
one drive in grey and colour variants sharing one download. Split agent
tools (`list_datasets`, `run_rtabmap`, `run_sam_on_dataset`, ...) extend
`SurveyTools`. GPS previews come from KITTI `oxts` extracted at prepare
time, with a static centre fallback in the spec.
