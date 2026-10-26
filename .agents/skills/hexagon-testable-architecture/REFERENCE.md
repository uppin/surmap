# Hexagonal Architecture — Reference (SurMap examples)

## Anatomy, from `src/surmap/slam/`

```python
# Port — slam/base.py: what the pipeline needs, nothing about RTAB-Map
class SlamBackend(Protocol):
    def process_frame(self, frame: StereoFramePair) -> FrameResult: ...
    def trajectory(self) -> list[Pose]: ...
    def close(self) -> None: ...

# Primary adapter — slam/rtabmap.py: owns the native binding and its absence
class RtabmapBackend:
    def __init__(self, database_path="surmap.db", *, module=None, module_name="rtabmap"):
        binding = _load_binding(module, module_name)  # raises RtabmapUnavailable

# Test adapter — slam/fake.py: same port, deterministic, no dependencies
class InMemorySlamBackend:
    def process_frame(self, frame): return FrameResult(frame.frame_id, frame.t_ns, self._pose, ())
```

Tests then verify the port once (`test_fake_backend_satisfies_protocol_and_records_trajectory`)
and the adapter against a stub binding — never against installed hardware.

## Applying it to the next seams

| Seam | Port (sketch) | Real adapter | Test adapter |
|---|---|---|---|
| Detection | `detect(frame) -> list[Detection]` | Coral Edge TPU `.tflite` runner on the CM5 | Recorded `Detection` fixtures per session |
| Segmentation | `segment(frame_ref, prompts) -> masks` | SAM 3.1 on the RTX 5060 Ti base station | Recorded masks for known sessions |
| Labelling | `label(object) -> str` | Newest Meta Llama via the Models API | Canned label table; records the model ID per run |
| Sessions | `load(session_id) -> frames + checkpoints` | Recorded flight sessions (§5 format) | Synthetic sessions with ground-truth geometry |

## Anti-patterns

- Importing a vendor/native module outside its adapter (`import rtabmap`
  anywhere but `slam/rtabmap.py`).
- Letting vendor types leak into contracts (a SAM mask object in
  `types.py` instead of referenced point/mask data).
- Mocking the adapter's internals in pipeline tests instead of using the
  in-memory adapter.
- Catching the unavailable-dependency error and continuing silently —
  degraded mapping must be visible, never a quietly empty map.
