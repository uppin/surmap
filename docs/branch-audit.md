# Branch audit

Written for Ginas (@JazzGinas) and Mantas (@uppin). These are suggestions. This audit did not merge, push, delete, close, or retarget any existing branch or pull request.

Figures are against `origin/main` at `38ce16b` (2026-10-30 07:38 +0200, merge of #29), after `git fetch --all --prune` on 2026-10-30. Ahead is commits on the branch that are not on main. Behind is commits on main that are not on the branch. A trial merge is `git merge --no-commit --no-ff` in a detached worktree, then `git merge --abort`. "Already on main" means the branch tip is an ancestor of `origin/main`.

`feat/mission-demo` is pull request #39 (draft). It contains current main (0 behind, 59 ahead) and is a fast-forward. `feat/map-render` also contains current main (0 behind, 18 ahead).

## Suggested merge order

1. **Merge #39 (`feat/mission-demo`) first.** The trial merge into main is clean and brings 122 files. GitHub currently reports it `MERGEABLE` / `CLEAN`. CI on the tip `047676a` is green: `test (3.11)`, `test (3.12)`, `coral-e2e`, `rtabmap-e2e`, `rtabmap-stream-e2e`. It is still a draft, and it still adds `docs/mission/1-WIP/`. The ready-for-review check rejects a ready PR that touches `docs/**/1-WIP/`, so wrap those two files before marking it ready.
2. **Open a PR from `feat/map-render` and merge it second.** The trial merge into today's main is clean (31 files) and would fast-forward. Against #39 the only conflicting file is `uv.lock`. `pyproject.toml` merges on its own and keeps both dependencies: `meta-sam-parser` from #39 and `rosbags` from map-render. Regenerate the lock with `uv lock` after the merge. Landing #39 first leaves that green PR untouched; the lockfile fix then sits on the map-render PR.
3. **Open a PR from `cursor/ask-the-map-2463` and merge it on its own.** It is 3 ahead and 13 behind. The trial merge into main is clean (19 files). Pairwise merges into #39 and into `feat/map-render` are also clean. Order relative to those two does not matter for conflicts. See below for how it fits #39.
4. **Leave `run-full-demo-locally-43aacb7a` out of this sequence.** It conflicts with main. It is an older SAM 2.1 demo, 2 ahead and 9 behind, with no pull request. #39 already carries SAM 3.1.

Every other remote branch is already on main, already inside #39, already inside `feat/map-render`, or is one of the leftovers in the next section.

## Pull requests that become redundant once #39 merges

#39's history merges these branches in by name. Each tip is an ancestor of `feat/mission-demo`, so the commits are fully contained. After #39 is on main, the open PRs can be closed and the branches deleted.

| PR | Branch | Trial merge into main on its own |
|---|---|---|
| #18 | `feat/PX4_sitl` | clean (46 files). Also contains merged #36. |
| #31 | `cursor/baseten-muse-labels-1ad3` | **conflict** on `src/surmap/labelling/__init__.py` |
| #32 | `cursor/modal-sam-gpu-bdcd` | **conflict** on `src/surmap/labelling/__init__.py` |
| #33 | `cursor/meta-sam-model-api-d3e4` | clean (13 files) |
| #34 | `cursor/project-sam-masks-onto-cloud-6d39` | clean (5 files) |
| #35 | `cursor/gps-anchored-map-snapshot-7f14` | clean (6 files) |
| #37 | `cursor/survey-viewer-486d` | clean (19 files) |

#36 (`cursor/disaster-gazebo-world-6e61`) is already merged into `feat/PX4_sitl`. That branch tip is also inside #39.

#31 and #32 conflict with current main if they land alone. #39 already has the resolution, `fix(labelling): export Meta, Baseten, and Modal clients together` (`99b91c3`). Close those two when #39 merges. Merging either of them into main first would stop #39's clean fast-forward.

#29 and #38 are already on main, and #39 contains them too.

## Branches that look stale or deletable

### Already on main (ahead 0)

The tip is an ancestor of main. Deleting the branch drops no commits.

| Branch | Behind | Last commit | Author | PR |
|---|---:|---|---|---|
| `cursor/meta-muse-scene-note-2096` | 2 | 2026-10-29 22:03 +0000 | uppin | merged #29 |
| `cursor/readme-meta-models-24f9` | 10 | 2026-10-28 20:35 +0000 | uppin | merged #28 |
| `feat/cm5-stereo-reconstruction` | 30 | 2026-10-27 08:05 +0200 | uppin | merged #13 |
| `feat/connectrpc-python` | 71 | 2026-10-26 21:51 +0200 | Mantas Indrašius | merged #4 |
| `pr-1-survey-proto` | 61 | 2026-10-27 07:37 +0200 | uppin | merged #6 |
| `pr-2-cm5-point-emitter` | 57 | 2026-10-27 07:38 +0200 | uppin | merged #7 |
| `pr-3-station-sam-policy` | 53 | 2026-10-27 07:38 +0200 | uppin | merged #9 |
| `pr-4-cm5-survey-server` | 47 | 2026-10-27 07:39 +0200 | uppin | merged #10 |
| `pr-5-station-sam-server` | 42 | 2026-10-27 07:39 +0200 | uppin | merged #11 |
| `pr-6-server-deployment` | 38 | 2026-10-27 07:40 +0200 | uppin | merged #12 |

### Moving-object stack, already squashed onto main

PRs #17, #19, #21, #22, #23, and #24 are merged. The stack tip `pr-6-moving-governance` contains the other five tips. Its trial merge into main is clean and **changes 0 files**, so it adds nothing main does not already have. The older tips conflict with main because they are mid-stack snapshots of files main has since rewritten:

| Branch | Ahead | Behind | Trial merge into main | PR |
|---|---:|---:|---|---|
| `docs/moving-object-design` | 8 | 21 | conflict: `docs/moving-object-detection-design.md` | merged #17 |
| `pr-2-moving-snippets` | 16 | 21 | conflict: `docs/moving-object-detection-design.md` | merged #19 |
| `pr-3-moving-differencing` | 22 | 21 | conflict: `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` | merged #21 |
| `pr-4-moving-classification` | 27 | 21 | conflict: `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` | merged #22 |
| `pr-5-moving-placement` | 36 | 21 | conflict: `docs/moving-object-detection-design.md` | merged #23 |
| `pr-6-moving-governance` | 40 | 21 | clean, 0 files | merged #24 |

Last commit on each of these is 2026-10-27 22:29 +0200, author uppin. Suggestion: delete the six branches. Re-merging the conflicting snapshots would fight the squash that already landed.

### Superseded Baseten branch

`cursor/baseten-muse-labels-aeb0` is closed PR #30 (3 ahead, 12 behind, last commit 2026-10-28 20:27 +0000, uppin). It is not inside #39. Trial merge into main conflicts on `HACKATHON.md`, `README.md`, and `src/surmap/labelling/__init__.py`. Trial merge into #39 also conflicts, on those three plus `docs/surmap/changelog/2026-10-28-baseten-muse-labels.md`, `src/surmap/labelling/baseten_muse.py`, and `tests/test_labelling_baseten_muse.py`. The replacement is #31, which #39 already contains. Suggestion: delete the branch.

### Inside `feat/map-render`, safe to delete only while that branch stays

These five are a straight line and every commit is on `feat/map-render`. They are not on main yet. Deleting them is safe if `feat/map-render` is kept. Deleting `feat/map-render` itself would drop the floor plan and the NTU calibration.

| Branch | Ahead | Behind | Last commit | Trial merge into main | Tip |
|---|---:|---:|---|---|---|
| `feat/live-map-display` | 4 | 0 | 2026-10-30 08:39 +0200 | clean, 13 files | tracked RTAB-Map keypoints, depth ramp |
| `feat/kitti-demo` | 6 | 0 | 2026-10-30 08:57 +0200 | clean, 18 files | KITTI outdoor scene |
| `feat/demo-controls` | 9 | 0 | 2026-10-30 09:50 +0200 | clean, 21 files | scene picker and playback controls |
| `feat/map-camera-indicator` | 11 | 0 | 2026-10-30 09:56 +0200 | clean, 23 files | camera indicator on the floor plan |
| `feat/ntu-viral-demo` | 13 | 0 | 2026-10-30 10:44 +0200 | clean, 28 files | NTU VIRAL scene from its ROS 1 bag |
| `feat/map-render` | 18 | 0 | 2026-10-30 12:19 +0200 | clean, 31 files | rendered floor plan, map-frame camera, NTU extrinsics from the authors' checkerboards |

Author of all six tips is uppin. None of them has a pull request. `feat/map-render` still carries changeset files under `docs/surmap/1-WIP/` (live map, KITTI, demo controls, camera indicator, NTU, map render). A ready PR will need those wrapped.

## Map Q&A and `feat/map-render`, relative to #39

**Map Q&A.** `cursor/ask-the-map-2463` (no PR) adds `surmap.mapqa`: ask one semantic-map snapshot through the Meta Model API, cite object ids and lat/lon, and accept a WAV question. Tip `e0e2fd0`, 2026-10-28 20:57 +0000, uppin. The three commits are the tests, the feature, and a docs wrap. #39 does not contain this branch, and the two diffs share no files.

#39 already has the hook. `src/surmap/viewer/ask.py` and the mission demo call `surmap.mapqa.answer` when `SURMAP_LIVE_META=1` and the package imports. `docs/mission-demo.md` on that branch says there is no merged pull request for `surmap.mapqa` and names this branch. Merging the branch turns that hook into a real package. The trial merge into #39 is clean, so it can land before or after #39. It is 13 commits behind main; merging main into it was clean in the trial.

**`feat/map-render`.** This is Mantas's live floor plan line, ending in the corrected NTU VIRAL calibration (`5ba16b7`). It is not inside #39. Both branches contain today's main, so either one fast-forwards onto main today. Together they conflict only on `uv.lock`.

A file-level merge of `pyproject.toml` from both sides is clean and lists both `meta-sam-parser>=0.1.0` and `rosbags>=0.11.9`. The same check on `tests/test_slam_streaming_e2e.py` is clean and keeps #39's fix that looks for the `docker` binary before calling it. After merging the two branches, run `uv lock` and commit the regenerated `uv.lock`.

`feat/map-render` also overlaps #39 on `tests/test_slam_streaming_e2e.py` and `pyproject.toml`, and those two merged clean. The demo server files (`scripts/demo.py`, `src/surmap/demo/server.py`, `src/surmap/demo/page.py`) are changed on the map-render side and were not in the conflict list against #39.

## Conflicts that matter

Pairwise trials covered every branch that is not already on main: 24 branches, all with a tip commit on or after 2026-10-27 (inside the last 7 days from 2026-10-30). That is 276 pairs: 158 clean, 114 conflicts, 4 already contained (one tip already an ancestor of the other). The full conflict list is at the end. Most of those 114 are the stale moving-object snapshots, or individual #31/#32-era branches, colliding with everything else. The pairs a maintainer would actually combine are these.

| Pair | Result | Conflicting files |
|---|---|---|
| `feat/mission-demo` × `feat/map-render` | conflict | `uv.lock` |
| `feat/mission-demo` × `feat/ntu-viral-demo` | conflict | `uv.lock` (this branch is inside map-render; same `rosbags` lock) |
| `feat/mission-demo` × `cursor/ask-the-map-2463` | clean | none |
| `feat/mission-demo` × `run-full-demo-locally-43aacb7a` | conflict | `src/surmap/demo/server.py` |
| `feat/map-render` × `cursor/ask-the-map-2463` | clean | none |
| `feat/map-render` × `run-full-demo-locally-43aacb7a` | conflict | `scripts/demo.py`, `src/surmap/demo/server.py` |
| `cursor/ask-the-map-2463` × `run-full-demo-locally-43aacb7a` | clean | none |
| `feat/mission-demo` × `feat/demo-controls` | clean | none |
| `feat/mission-demo` × `feat/map-camera-indicator` | clean | none |
| `feat/mission-demo` × `feat/kitti-demo` | clean | none |
| `feat/mission-demo` × `feat/live-map-display` | clean | none |

`run-full-demo-locally-43aacb7a` (tip 2026-10-30 00:30 +0200, uppin, no PR) also conflicts with main on `src/surmap/demo/server.py`. It adds SAM 2.1 masks prompted by Coral boxes and fused onto the RTAB-Map map, plus `docs/surmap/1-WIP/` planning files. #39 edits `src/surmap/survey/sam3.py` for Meta Model API SAM 3.1; this branch edits that file for the SAM 2.1 path. The pairwise merge with #39 conflicts on the demo server, and `sam3.py` itself merged. Suggestion: treat this branch as historical unless someone still wants the SAM 2.1 Coral fusion. Cherry-pick from it only after reading `src/surmap/demo/fusion.py` and `src/surmap/survey/sam2.py`, which exist only here.

Individual branches that are already inside #39 still conflict with the map stack on `src/surmap/labelling/__init__.py` (#31 and #32) or on `uv.lock` (#33 against map-render and NTU). Those collisions are already resolved on #39: #39 × `feat/map-render` conflicts only on `uv.lock`.

## Tests

`uv run pytest -q` on Python 3.12.3. This machine has no `docker` binary. GitHub CI on main does, and that run is green.

| Branch | Tip | Result |
|---|---|---|
| `main` | `38ce16b` | **515 passed, 1 failed, 6 skipped** (7.52s) |
| `feat/mission-demo` | `047676a` | **693 passed, 10 skipped, 0 failed** (10.24s) |
| `feat/map-render` | `5ba16b7` | **579 passed, 1 failed, 6 skipped** (14.45s) |

The one failure on main and on `feat/map-render` is `tests/test_slam_streaming_e2e.py::test_streaming_backend_maps_live_over_the_fixture`. The helper runs `docker image inspect` before `shutil.which("docker")`, so a missing Docker raises `FileNotFoundError` instead of skipping. CI on `origin/main` at `38ce16b` is success, including the RTAB-Map stream job. #39 changed that helper to check for the binary first, which is why its local run skips the test and stays green. CI on #39's tip is green as well.

`feat/map-render` has no pull request, so it has no CI run. Apart from that one environment failure, its suite passed. A merge with #39 keeps #39's Docker check in that test file.

## Every other open branch, into main

This is every branch that is not already an ancestor of main, including the ones discussed above, with ahead, behind, date, and the trial merge in one place.

| Branch | Ahead | Behind | Last commit | Author | Trial merge into main | PR | Tip |
|---|---:|---:|---|---|---|---|---|
| `feat/mission-demo` | 59 | 0 | 2026-10-30 08:32 +0000 | uppin | clean, 122 files | #39 draft | drive the live map from the streaming backend |
| `feat/PX4_sitl` | 19 | 22 | 2026-10-30 00:01 +0200 | Ginas | clean, 46 files | #18 | Gazebo/PX4 SITL, includes #36 |
| `cursor/disaster-gazebo-world-6e61` | 18 | 22 | 2026-10-28 21:41 +0000 | uppin | clean, 46 files | #36 merged into PX4 | disaster block as a collapse and a flood |
| `cursor/survey-viewer-486d` | 2 | 13 | 2026-10-28 20:58 +0000 | uppin | clean, 19 files | #37 | synced viewer, delegates live map questions |
| `cursor/modal-sam-gpu-bdcd` | 6 | 13 | 2026-10-28 20:47 +0000 | uppin | conflict: `src/surmap/labelling/__init__.py` | #32 | Modal GPU SAM 3.1 |
| `cursor/baseten-muse-labels-1ad3` | 6 | 13 | 2026-10-28 20:40 +0000 | uppin | conflict: `src/surmap/labelling/__init__.py` | #31 | Baseten labels and credit ledger |
| `cursor/gps-anchored-map-snapshot-7f14` | 4 | 13 | 2026-10-28 20:35 +0000 | uppin | clean, 6 files | #35 | GPS-anchored semantic map snapshot |
| `cursor/meta-sam-model-api-d3e4` | 5 | 13 | 2026-10-28 20:34 +0000 | uppin | clean, 13 files | #33 | Meta Model API SAM 3.1 |
| `cursor/project-sam-masks-onto-cloud-6d39` | 5 | 13 | 2026-10-28 20:31 +0000 | uppin | clean, 5 files | #34 | project SAM masks onto the cloud |
| `cursor/ask-the-map-2463` | 3 | 13 | 2026-10-28 20:57 +0000 | uppin | clean, 19 files | none | Ask the map |
| `run-full-demo-locally-43aacb7a` | 2 | 9 | 2026-10-30 00:30 +0200 | uppin | conflict: `src/surmap/demo/server.py` | none | SAM 2.1 masks fused onto the RTAB-Map map |
| `cursor/baseten-muse-labels-aeb0` | 3 | 12 | 2026-10-28 20:27 +0000 | uppin | conflict: `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` | #30 closed | first Baseten attempt |

There are 34 remote branches besides main. The tables in this file cover all 34.

## Risks, in one place

- #39 is the integration PR and it is still a draft with `docs/mission/1-WIP/` present. CI is green. The branch ruleset will refuse a ready PR until that directory is gone from the diff.
- Merging #31 or #32 into main on their own conflicts today. #39 is the copy that merges clean.
- `feat/map-render` and #39 conflict only on `uv.lock`. The dependency lists combine. Someone still has to regenerate the lock and re-run the suite on the result. This audit did not commit that merge.
- `feat/map-render` has no PR and no CI, and its local suite hits the same missing-Docker failure as main (579 passed, 1 failed, 6 skipped).
- `run-full-demo-locally-43aacb7a` is a real code conflict on the demo server with both main and the two lines above.
- The moving-object branch tips conflict if someone tries to merge them again. Their stack tip adds zero files to main. Deleting them matches the squash that already landed.

## Appendix: all 114 conflicting pairs

Each row is one `git merge --no-commit --no-ff` of the second branch onto the first. Pairs with no conflicting files are omitted here; there were 158 clean merges and 4 pairs where the second branch was already contained in the first (`feat/demo-controls` contains `feat/kitti-demo` and `feat/live-map-display`, `feat/kitti-demo` contains `feat/live-map-display`, `feat/map-render` contains `feat/ntu-viral-demo`). Many other stack relationships also merged clean because one side fast-forwards onto the other.

| Onto | Merged in | Conflicting files |
|---|---|---|
| `cursor/ask-the-map-2463` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/ask-the-map-2463` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/ask-the-map-2463` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/ask-the-map-2463` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/ask-the-map-2463` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-1ad3` | `cursor/baseten-muse-labels-aeb0` | `docs/surmap/changelog/2026-10-28-baseten-muse-labels.md`, `src/surmap/labelling/__init__.py`, `src/surmap/labelling/baseten_muse.py`, `tests/test_labelling_baseten_muse.py` |
| `cursor/baseten-muse-labels-1ad3` | `cursor/modal-sam-gpu-bdcd` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-1ad3` | `feat/demo-controls` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `feat/kitti-demo` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `feat/live-map-display` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `feat/map-camera-indicator` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `feat/map-render` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `feat/ntu-viral-demo` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-1ad3` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-1ad3` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/baseten-muse-labels-1ad3` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/baseten-muse-labels-1ad3` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-aeb0` | `cursor/modal-sam-gpu-bdcd` | `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-aeb0` | `feat/demo-controls` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/kitti-demo` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/live-map-display` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/map-camera-indicator` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/map-render` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/mission-demo` | `HACKATHON.md`, `README.md`, `docs/surmap/changelog/2026-10-28-baseten-muse-labels.md`, `src/surmap/labelling/__init__.py`, `src/surmap/labelling/baseten_muse.py`, `tests/test_labelling_baseten_muse.py` |
| `cursor/baseten-muse-labels-aeb0` | `feat/ntu-viral-demo` | `HACKATHON.md`, `README.md`, `src/surmap/labelling/__init__.py` |
| `cursor/baseten-muse-labels-aeb0` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-aeb0` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/baseten-muse-labels-aeb0` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/baseten-muse-labels-aeb0` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/baseten-muse-labels-aeb0` | `run-full-demo-locally-43aacb7a` | `HACKATHON.md`, `README.md` |
| `cursor/gps-anchored-map-snapshot-7f14` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/gps-anchored-map-snapshot-7f14` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/gps-anchored-map-snapshot-7f14` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/gps-anchored-map-snapshot-7f14` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/gps-anchored-map-snapshot-7f14` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/meta-sam-model-api-d3e4` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/meta-sam-model-api-d3e4` | `feat/map-render` | `uv.lock` |
| `cursor/meta-sam-model-api-d3e4` | `feat/ntu-viral-demo` | `uv.lock` |
| `cursor/meta-sam-model-api-d3e4` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/meta-sam-model-api-d3e4` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/meta-sam-model-api-d3e4` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/meta-sam-model-api-d3e4` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/modal-sam-gpu-bdcd` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/modal-sam-gpu-bdcd` | `feat/demo-controls` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `feat/kitti-demo` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `feat/live-map-display` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `feat/map-camera-indicator` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `feat/map-render` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `feat/ntu-viral-demo` | `src/surmap/labelling/__init__.py` |
| `cursor/modal-sam-gpu-bdcd` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/modal-sam-gpu-bdcd` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/modal-sam-gpu-bdcd` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/modal-sam-gpu-bdcd` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/project-sam-masks-onto-cloud-6d39` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/project-sam-masks-onto-cloud-6d39` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/project-sam-masks-onto-cloud-6d39` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/project-sam-masks-onto-cloud-6d39` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/project-sam-masks-onto-cloud-6d39` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `cursor/survey-viewer-486d` | `docs/moving-object-design` | `docs/moving-object-detection-design.md` |
| `cursor/survey-viewer-486d` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `cursor/survey-viewer-486d` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/survey-viewer-486d` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `cursor/survey-viewer-486d` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/demo-controls` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/kitti-demo` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/live-map-display` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/map-camera-indicator` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/map-render` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/mission-demo` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `feat/ntu-viral-demo` | `docs/moving-object-detection-design.md` |
| `docs/moving-object-design` | `run-full-demo-locally-43aacb7a` | `docs/moving-object-detection-design.md` |
| `feat/demo-controls` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/demo-controls` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/demo-controls` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/demo-controls` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/demo-controls` | `run-full-demo-locally-43aacb7a` | `scripts/demo.py`, `src/surmap/demo/server.py` |
| `feat/kitti-demo` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/kitti-demo` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/kitti-demo` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/kitti-demo` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/kitti-demo` | `run-full-demo-locally-43aacb7a` | `src/surmap/demo/server.py` |
| `feat/live-map-display` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/live-map-display` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/live-map-display` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/live-map-display` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/live-map-display` | `run-full-demo-locally-43aacb7a` | `src/surmap/demo/server.py` |
| `feat/map-camera-indicator` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/map-camera-indicator` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/map-camera-indicator` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/map-camera-indicator` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/map-camera-indicator` | `run-full-demo-locally-43aacb7a` | `scripts/demo.py`, `src/surmap/demo/server.py` |
| `feat/map-render` | `feat/mission-demo` | `uv.lock` |
| `feat/map-render` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/map-render` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/map-render` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/map-render` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/map-render` | `run-full-demo-locally-43aacb7a` | `scripts/demo.py`, `src/surmap/demo/server.py` |
| `feat/mission-demo` | `feat/ntu-viral-demo` | `uv.lock` |
| `feat/mission-demo` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/mission-demo` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/mission-demo` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/mission-demo` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/mission-demo` | `run-full-demo-locally-43aacb7a` | `src/surmap/demo/server.py` |
| `feat/ntu-viral-demo` | `pr-2-moving-snippets` | `docs/moving-object-detection-design.md` |
| `feat/ntu-viral-demo` | `pr-3-moving-differencing` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/ntu-viral-demo` | `pr-4-moving-classification` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `feat/ntu-viral-demo` | `pr-5-moving-placement` | `docs/moving-object-detection-design.md` |
| `feat/ntu-viral-demo` | `run-full-demo-locally-43aacb7a` | `scripts/demo.py`, `src/surmap/demo/server.py` |
| `pr-2-moving-snippets` | `run-full-demo-locally-43aacb7a` | `docs/moving-object-detection-design.md` |
| `pr-3-moving-differencing` | `run-full-demo-locally-43aacb7a` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `pr-4-moving-classification` | `run-full-demo-locally-43aacb7a` | `docs/moving-object-detection-design.md`, `src/surmap/survey/cm5_server.py` |
| `pr-5-moving-placement` | `run-full-demo-locally-43aacb7a` | `docs/moving-object-detection-design.md` |
