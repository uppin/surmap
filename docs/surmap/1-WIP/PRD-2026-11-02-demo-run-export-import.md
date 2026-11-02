# Demo run export and import - PRD

**Date**: 2026-11-02
**PRD Type**: Enhancement

## Affected Features

- **Primary Feature**: Dev console run history (README § Dev console): export a run to one
  file, import it into another console

## Summary

A recorded run (frames, map, SAM masks, surfaces, journal and dense buffer) can be exported
to a single `.surmaprun` file and imported into any console, where it replays and rewinds
like a run recorded there.

## Background

Recording a run with SAM 3.1 takes about 25 minutes on a Mac and needs the SAM runtime. A
good recording (the KITTI 0009 rebuild `acdcc6aa`) should be shareable without re-recording.

## Proposed Changes

### What's Changing

1. **Export** on the page (next to Load run / Replay run) downloads the selected run, plus
   its replay source chain, as a `.surmaprun` file (gzipped SQLite in the history schema).
2. **Import** on the page uploads a `.surmaprun` file. Its runs join the history under
   their own ids, and a run already present is skipped.
3. **CLI:** `python -m surmap.demo.run_archive export RUN_ID FILE` and `import FILE`, with
   `--history-db` to name the store.
4. A run still running cannot be exported.

### What's Staying the Same

- The history database and its schema.
- How runs replay and rewind.

## Acceptance Criteria

1. An exported then imported run has the same frames, journal, map updates, surfaces,
   rig and dense buffer, in the same order, and replays.
2. Exporting a replay brings its source run; importing it replays from that source.
3. Importing a run already present skips it and changes nothing.
4. A file that is not a run export is refused with a clear error.
5. A running run cannot be exported.
6. The page has Export and Import; the endpoints round-trip a run.
7. `acdcc6aa` exports and re-imports into a fresh store.
