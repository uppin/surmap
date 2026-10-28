# Initial discovery — Meta Model API scene note

## Combined conclusions

- `main` has no `surmap.labelling` package and no Meta Model API client. PR #28
  (branch `cursor/readme-meta-models-24f9`, open, not merged) adds `HACKATHON.md`
  and the README model policy. That file still says the three credit sources are
  planned and that nothing in `src/` calls them.
- The follow-up names `MetaMuseSceneClient.note(labels, frame_jpeg) -> str` in
  `src/surmap/labelling/meta_muse.py`, tested from `tests/test_labelling_meta_muse.py`.
- The live contract, checked by the owner on 2026-10-28, is `POST
  https://api.meta.ai/v1/responses` with `Authorization: Bearer $MODEL_API_KEY`,
  model `muse-spark-1.3`, Responses API `input` items, and `stream: false`.
  The API's default `reasoning.effort` is `high`. This client sends `low`.
- A response `output` list has a `reasoning` item and then a `message` item.
  The note is the `output_text` parts of `message` items only.
- Meta's image-understanding guide sends a frame as an `input_image` part whose
  `image_url` is a plain string (public URL or `data:` URL), inside a user
  message. That is the image part this client sends. Chat Completions'
  nested `image_url` object is a different API.
- Muse Wonder ids and `meta-models/muse-spark-open-1026` are out of scope.
  The repository is public: the key stays in `MODEL_API_KEY` and is never
  written into source, logs, or error text.
- HTTP dependencies in this tree are stdlib (`urllib` in `surmap.demo.datasets`).
  No `httpx` or `requests` dependency. Tests are pytest, mypy strict, Given /
  When / Then. Optional live calls use an env gate (`SURMAP_REQUIRE_*` pattern).
- `docs/architecture.md` §3.2 still says "newest Meta Llama". PR #28 left it
  alone because PR #18 edits that file. This change does not edit it.

## Exploration 1

Sequence: `gh` view of PR #28 and comment 6479195054; `git show` of
`HACKATHON.md` and `README.md` on `cursor/readme-meta-models-24f9`; glob of
`src/surmap/**/*.py`; grep for `urllib`, `MODEL_API_KEY`, `labelling`; read of
`pyproject.toml`, `src/surmap/demo/datasets.py` (download helper),
`src/surmap/survey/sam3.py` (adapter seam), `tests/test_survey_sam_policy.py`
and `tests/test_moving_kitti_e2e.py` (skip gate); Meta docs
`https://dev.meta.ai/docs/image-understanding` and the Responses schemas.

Findings: the scene note is a new adapter, not a change to the geometric
pipeline. The credits table in `HACKATHON.md` is the stable cell that must
stop saying the scene note is only planned. A fake transport is the test seam;
the live call stays behind `SURMAP_LIVE_META=1`.
