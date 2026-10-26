---
description: Create prototypes for rapid experimentation
---

## Create Prototype

Prototype against the pipeline, not against a UI. A SurMap prototype
answers one survey question with the smallest runnable thing:

- Can stereo pairs from the candidate ELP module produce usable depth
  once the (unmeasured) baseline is known?
- Does `classify_motion` separate a walking person from a parked car on
  a recorded session?
- What does SAM 3.1 throughput look like on the RTX 5060 Ti for our
  frame size (measure — do not assume the H100 figures)?

### 1. State the question and the success signal

One sentence each. The signal must be observable in numbers or map
output: depth error against known ground truth, layer membership of a
track, frames/second and peak VRAM.

### 2. Build it outside the package, on real-shaped data

- Keep prototype code in `tmp/` or a scratch script; do not add it to
  `src/surmap/` until it graduates (see step 4).
- Feed it a recorded session or a synthetic session in the §5 format —
  indistinguishable in shape from real flight data
  (`docs/architecture.md` §2.3). Detector/SAM outputs are fixtures.
- No hardware dependence that a reviewer cannot reproduce: drive SLAM
  through `InMemorySlamBackend` or a stub binding.

### 3. Show the result in map terms

Render or dump the artefact the question is about: the static layer
with the object merged (or correctly absent), the moving track's
timestamped centroids against ground truth, the timing table. Save it
under `tmp/` and link it; do not paste large point clouds into chat.

### 4. Graduate or discard

- Graduating means: contracts first (`types.py`), a failing test in
  `tests/`, then the implementation behind the right adapter seam —
  hand off to `/plan-red` / the `tdd` skill.
- Discarding means deleting the scratch code and recording the measured
  answer (and the number that killed it) in the relevant doc or issue.
- A prototype never merges as-is, and never acquires a flight-control
  path: SurMap is passive in prototypes too.
