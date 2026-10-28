# Initial Discovery: Baseten Muse Spark Open labels

**Changeset**: [2026-10-28-baseten-muse-labels.md](./2026-10-28-baseten-muse-labels.md)
**Date**: 2026-10-28
**Passes**: 1

## Combined Conclusions

SurMap has no labelling package. Semantic labels are described in
`docs/architecture.md` §3.2 as a future Models API call (the text
still says "newest Meta Llama") and in `README.md` / `HACKATHON.md`
on PR #28 as Muse Spark Open on Baseten, status planned. The
follow-up on PR #28 asks for `LabelClient` and
`BasetenMuseLabelClient` in `src/surmap/labelling/baseten_muse.py`,
with tests that inject a fake HTTP transport. The SLAM hexagon
(`slam/base.py`, `slam/rtabmap.py`, `slam/fake.py`) is the pattern:
a protocol, an adapter that fails by name when its dependency is
missing, and an in-memory adapter. HTTP in this repo is stdlib
`urllib`, not a new client library. Live suites are gated by
`SURMAP_REQUIRE_*=1`. `src/surmap/docs/todo/` holds moving-object
follow-ups only; none name labelling. `docs/architecture.md` §3.2
is also edited by open PR #18, so this change does not touch it.

## Exploration 1: labelling seam and hackathon docs — 2026-10-28

**Agent**: parent Grep/Glob/Read
**Scope**: where a Baseten label client would land, and what PR #28 already says

### Sequence

1. `gh api` comment 6479193887 — the follow-up task text.
2. `gh pr view 28` — PR open, head `cursor/readme-meta-models-24f9`, not merged.
3. `git show` of `HACKATHON.md` and `README.md` on that branch — Baseten row is Planned; no `src/` client.
4. Glob `src/surmap/**/*.py` — no `labelling` package.
5. Read `src/surmap/types.py`, `slam/base.py`, `slam/rtabmap.py` — port, frozen contracts, typed native boundary.
6. Grep `SURMAP_REQUIRE_|urllib|httpx` — live tests use env flags; HTTP is urllib; no httpx dependency.
7. Read `docs/architecture.md` §3.2 and the `Landmark` contract — label, description, confidence, model id.
8. Glob `src/surmap/docs/todo/` — moving-object items only.

### Grep / glob

| Tool | Pattern / glob | Path scope | Notable hits |
|------|----------------|------------|--------------|
| Glob | `src/surmap/**/*.py` | repo | no labelling module |
| Grep | `Baseten\|Muse\|label` | `docs/architecture.md` | §3.2 LLM via Models API, still "newest Meta Llama" |
| Grep | `SURMAP_REQUIRE_\|urllib` | repo | gated e2e tests; urllib in scripts and demo |

### Inspected files

#### `src/surmap/slam/rtabmap.py`

**Why**: how an optional dependency fails before use.
**Excerpt**: `RtabmapUnavailable` is raised from the constructor when the binding cannot be loaded, with install guidance and no silent fallback.

#### `HACKATHON.md` (PR #28)

**Why**: the status row this task must change.
**Excerpt**: Baseten status "Planned". Intro says none of the three credits is called from `src/`. "Not in this tree" lists Baseten with Meta Model API and Modal.

### Findings

- New code belongs in `src/surmap/labelling/`, with the protocol and in-memory client beside the Baseten adapter, matching the SLAM split even though the task names one module.
- Do not add an HTTP dependency. Inject a transport protocol so unit tests never call `urlopen`.
- Gate the live test on `SURMAP_LIVE_BASETEN=1` and a non-empty `BASETEN_API_KEY`.
- Update `HACKATHON.md` so it does not still say Baseten is absent from `src/`.
- Leave `docs/architecture.md` §3.2 for PR #18.
