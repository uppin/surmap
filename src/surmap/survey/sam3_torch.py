"""Real SAM 3.1 segmentation: Meta's predictor behind the streamer port.

The gated `facebook/sam3.1` checkpoint (`sam3.1_multiplex.pt`) is a
PyTorch model in Meta's native format. It runs through the official
`sam3` package's multiplex video model — SAM 3.1's own continuous
mode: one state over the whole video, one concept prompt, then
propagation yields every frame's objects with SAM's persistent ids.

The session is driven at the model level (`init_state` /
`add_prompt` / `propagate_in_video`), not through the package's
`Sam3BasePredictor.handle_request`: that wrapper passes
`offload_state_to_cpu` into `init_state`, which the multiplex model
rejects.

torch and the `sam3` package are an optional install; they are
imported lazily at construction and absence fails by name
(`Sam3Unavailable`), never at module import. Vendor tensors and
dicts stay inside this adapter; the domain sees only `SamDetection`.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from surmap.detection.detector import decode_rgb
from surmap.survey.sam import RawFrame, SamDetection
from surmap.survey.sam3 import Sam3Unavailable, _mask_outline, parse_sam_device
from surmap.survey.stereo import FrameImage

DEFAULT_SAM31_MODEL = "facebook/sam3.1"
_SAM31_CHECKPOINT = "sam3.1_multiplex.pt"


class Sam31ImageProcessor(Protocol):
    """The vendor image processor's surface (faked in tests)."""

    def set_image(self, image: Any, state: Any = None) -> Any: ...
    def set_text_prompt(self, prompt: str, state: Any) -> Any: ...


def _as_numpy(value: Any) -> NDArray[Any]:
    """A vendor tensor or array as a NumPy array, without importing torch."""
    detach = getattr(value, "detach", None)
    if callable(detach):
        tensor = detach().cpu()
        if "bfloat" in str(getattr(tensor, "dtype", "")):
            tensor = tensor.float()
        return np.asarray(tensor.numpy())
    return np.asarray(value)


class Sam31TorchDetector:
    """`SamDetector` over Meta's SAM 3.1 image model (PyTorch, GPU).

    One frame in, that frame's detections out: the image processor is
    prompted with the configured concept for every frame. The vendor
    processor and its tensors stay inside this adapter.
    """

    def __init__(
        self,
        processor: Sam31ImageProcessor,
        *,
        prompt: str = "object",
        device: str = "cuda:0",
        score_threshold: float = 0.5,
        autocast: Callable[[], AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._processor = processor
        self._prompt = prompt
        self._device = device
        self._score_threshold = score_threshold
        self._autocast = autocast
        self._prompt_lock = threading.Lock()

    def set_prompt(self, prompt: str) -> None:
        """Reset the concept for the next stream (see StreamAnalysis)."""
        with self._prompt_lock:
            self._prompt = prompt

    @property
    def provider(self) -> str:
        return "SAM 3.1 (PyTorch)"

    @property
    def device(self) -> str:
        return self._device

    def _segment(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        from PIL import Image

        rgb = decode_rgb(FrameImage(frame.width, frame.height, frame.encoding, frame.data))
        with self._prompt_lock:
            prompt = self._prompt
        # The checkpoint's weights are bf16: inference must run under
        # the same autocast the vendor predictor enters, or matmuls
        # fail with a BFloat16/Float dtype mismatch.
        context = self._autocast() if self._autocast is not None else nullcontext()
        with context:
            state = self._processor.set_image(Image.fromarray(rgb))
            state = self._processor.set_text_prompt(prompt, state)
        masks = _as_numpy(state["masks"])
        boxes = _as_numpy(state["boxes"])
        scores = _as_numpy(state["scores"])
        detections: list[SamDetection] = []
        for index in range(len(scores)):
            score = float(scores[index])
            if score < self._score_threshold:
                continue
            mask = np.asarray(masks[index], dtype=bool)
            if mask.ndim == 3 and mask.shape[0] == 1:
                mask = mask[0]  # the vendor's leading channel dim
            x_min, y_min, x_max, y_max = (float(value) for value in boxes[index])
            # Boxes arrive in frame pixels; mask outlines are on the
            # model's mask grid and must be scaled onto the frame.
            scale_x = frame.width / mask.shape[1] if mask.shape[1] else 1.0
            scale_y = frame.height / mask.shape[0] if mask.shape[0] else 1.0
            detections.append(
                SamDetection(
                    label=prompt,
                    score=score,
                    box_xyxy=(x_min, y_min, x_max, y_max),
                    mask_polygon=_mask_outline(mask, scale_x, scale_y),
                )
            )
        return tuple(detections)

    def segment(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        """Segment one frame, synchronously."""
        return self._segment(frame)

    async def detect(self, frame: RawFrame) -> tuple[SamDetection, ...]:
        """Segment one frame (inference runs off the event loop)."""
        return await asyncio.to_thread(self._segment, frame)


class Sam31Model(Protocol):
    """The vendor multiplex model's session surface (faked in tests)."""

    def init_state(
        self,
        resource_path: str,
        async_loading_frames: bool = False,
        offload_video_to_cpu: bool = False,
    ) -> Any: ...
    def add_prompt(
        self, inference_state: Any, frame_idx: int, text_str: str | None = None
    ) -> Any: ...
    def propagate_in_video(
        self, inference_state: Any, start_frame_idx: int = 0, reverse: bool = False
    ) -> Iterator[tuple[int, dict[str, Any]]]: ...


class Sam31VideoStreamer:
    """`VideoSamStreamer` adapter over one vendor multiplex model.

    Each `stream()` is one video, propagated in windows of
    `chunk_frames`: a session's state grows with its frames, so a
    long video on a 16 GB card must not be one session (SAM's object
    ids restart per window — they are session-local). Frames are
    linked into a scratch directory in playback order
    (`000000.jpg`, ...), a state is initialised there with the video
    offloaded to CPU, prompted once at frame 0 with the concept
    prompt, and propagated forward. Every yielded frame's `out_*`
    arrays are converted at the edge: SAM's object id is the track
    id, the (normalised, despite the `xywh` name) boxes are scaled
    to frame pixels, binary masks become outline polygons.
    Propagation runs under the given autocast context (bf16 on GPU —
    the vendor predictor enters the same context).
    """

    def __init__(
        self,
        model: Sam31Model,
        *,
        prompt: str = "object",
        device: str = "cuda:0",
        chunk_frames: int = 16,
        autocast: Callable[[], AbstractContextManager[Any]] | None = None,
        on_chunk_end: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        if chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")
        self._model = model
        self._prompt = prompt
        self._device = device
        self._chunk_frames = chunk_frames
        self._autocast = autocast
        self._on_chunk_end = on_chunk_end
        self._on_close = on_close

    @property
    def provider(self) -> str:
        return "SAM 3.1 multiplex (PyTorch)"

    @property
    def device(self) -> str:
        return self._device

    def stream(
        self, frame_paths: Sequence[Path], prompt: str | None = None
    ) -> Iterator[tuple[int, tuple[SamDetection, ...]]]:
        paths = list(frame_paths)
        concept = self._prompt if prompt is None else prompt
        for start in range(0, len(paths), self._chunk_frames):
            yield from self._stream_window(
                paths[start : start + self._chunk_frames], start, concept
            )
            if self._on_chunk_end is not None:
                self._on_chunk_end()

    def _stream_window(
        self, window: list[Path], offset: int, prompt: str
    ) -> Iterator[tuple[int, tuple[SamDetection, ...]]]:
        scratch = Path(tempfile.mkdtemp(prefix="surmap-sam31-"))
        try:
            for index, source in enumerate(window):
                link = scratch / f"{index:06d}.jpg"
                try:
                    link.symlink_to(source.resolve())
                except OSError:
                    shutil.copyfile(source, link)
            state = self._model.init_state(
                resource_path=str(scratch),
                async_loading_frames=False,
                offload_video_to_cpu=True,
            )
            # Prompting and propagation both run under autocast: the
            # model's weights are bf16, and a context entered on the
            # constructing thread (as the vendor predictor does) does
            # not reach this worker thread — without it, matmuls fail
            # with a BFloat16/Float dtype mismatch.
            context = self._autocast() if self._autocast is not None else nullcontext()
            with context:
                self._model.add_prompt(state, 0, text_str=prompt)
                for frame_index, detections in self._propagate(state, prompt):
                    yield offset + frame_index, detections
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def _propagate(self, state: Any, prompt: str) -> Iterator[tuple[int, tuple[SamDetection, ...]]]:
        for frame_index, outputs in self._model.propagate_in_video(
            state, start_frame_idx=0, reverse=False
        ):
            obj_ids = np.asarray(outputs["out_obj_ids"]).tolist()
            probs = np.asarray(outputs["out_probs"]).tolist()
            boxes = np.asarray(outputs["out_boxes_xywh"]).tolist()
            masks = np.asarray(outputs["out_binary_masks"])
            height, width = masks.shape[1], masks.shape[2]
            detections = tuple(
                SamDetection(
                    label=prompt,
                    score=float(probs[position]),
                    box_xyxy=(
                        float(box[0]) * width,
                        float(box[1]) * height,
                        float(box[2]) * width,
                        float(box[3]) * height,
                    ),
                    mask_polygon=_mask_outline(np.asarray(masks[position], dtype=bool), 1.0, 1.0),
                    track_id=int(obj_ids[position]),
                )
                for position, box in enumerate(boxes)
            )
            yield int(frame_index), detections

    def close(self) -> None:
        if self._on_close is not None:
            self._on_close()


def _resolve_checkpoint(model: str, importer: Callable[[str], Any]) -> Path:
    """A checkpoint path for an HF id, a local `.pt`, or a local directory."""
    candidate = Path(model)
    if candidate.is_file():
        return candidate
    if candidate.is_dir() and (candidate / _SAM31_CHECKPOINT).is_file():
        return candidate / _SAM31_CHECKPOINT
    try:
        hub = importer("huggingface_hub")
    except ImportError as exc:
        raise Sam3Unavailable(
            "downloading a SAM 3.1 checkpoint needs huggingface_hub "
            "(installed with transformers); or pass a local .pt path"
        ) from exc
    try:
        downloaded: object = hub.hf_hub_download(
            model, _SAM31_CHECKPOINT, token=os.environ.get("HF_TOKEN") or None
        )
    except Exception as exc:
        raise Sam3Unavailable(
            f"SAM 3.1 checkpoint {model!r} could not be downloaded ({exc}); "
            "accept the facebook/sam3.1 licence and put a valid HF_TOKEN "
            "in the project .env (loaded by surmap.env.load_env)"
        ) from exc
    return Path(str(downloaded))


def sam31_video_streamer(
    model: str = DEFAULT_SAM31_MODEL,
    *,
    device: str = "cuda:0",
    prompt: str = "object",
    _importer: Callable[[str], Any] = importlib.import_module,
) -> Sam31VideoStreamer:
    """A real SAM 3.1 `VideoSamStreamer` for a checkpoint id or local path.

    Builds Meta's multiplex predictor on the named GPU device; the
    checkpoint is downloaded with `HF_TOKEN` (from the project `.env`)
    unless a local file is given.
    """
    # Expandable segments keep the multiplex state from fragmenting
    # the 16 GB card into an OOM over a long video; must be set
    # before torch initialises CUDA.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    try:
        torch = _importer("torch")
        model_builder = _importer("sam3.model_builder")
    except ImportError as exc:
        raise Sam3Unavailable(
            "the real SAM 3.1 runtime is not installed: install torch, "
            "torchvision and Meta's sam3 package "
            '(uv pip install torch torchvision "setuptools<81" '
            "git+https://github.com/facebookresearch/sam3.git), accept the "
            "facebook/sam3.1 licence, and put HF_TOKEN in the project .env"
        ) from exc
    kind, device_id = parse_sam_device(device)
    if kind == "cuda":
        if not bool(torch.cuda.is_available()):
            raise Sam3Unavailable(
                f"torch reports no CUDA device for {device}; check the NVIDIA "
                "driver and that the installed torch build is a CUDA build"
            )
        torch.cuda.set_device(device_id or 0)
    checkpoint = _resolve_checkpoint(model, _importer)
    predictor: Any = model_builder.build_sam3_predictor(
        checkpoint_path=str(checkpoint),
        version="sam3.1",
        compile=False,
        warm_up=False,
        use_fa3=False,
        async_loading_frames=False,
    )
    autocast: Callable[[], AbstractContextManager[Any]] | None = None
    if kind == "cuda":
        autocast = lambda: torch.autocast(device_type="cuda", dtype=torch.bfloat16)  # noqa: E731
    shutdown = getattr(predictor, "shutdown", None)

    def _release() -> None:
        import gc

        gc.collect()
        if kind == "cuda":
            torch.cuda.empty_cache()

    def _close() -> None:
        if callable(shutdown):
            shutdown()
        _release()

    return Sam31VideoStreamer(
        predictor.model,
        prompt=prompt,
        device=f"cuda:{device_id}" if kind == "cuda" else "cpu",
        autocast=autocast,
        on_chunk_end=_release,
        on_close=_close,
    )


def sam31_torch_detector(
    model: str = DEFAULT_SAM31_MODEL,
    *,
    device: str = "cuda:0",
    prompt: str = "object",
    _importer: Callable[[str], Any] = importlib.import_module,
) -> Sam31TorchDetector:
    """A real SAM 3.1 `SamDetector` (PyTorch image model) for the station.

    Builds Meta's image model on the named GPU device and prompts it
    with `prompt` per frame; the checkpoint resolves exactly as the
    video streamer's (HF id, local `.pt`, or local directory).
    """
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    try:
        torch = _importer("torch")
        model_builder = _importer("sam3.model_builder")
        processor_module = _importer("sam3.model.sam3_image_processor")
    except ImportError as exc:
        raise Sam3Unavailable(
            "the real SAM 3.1 runtime is not installed: install torch, "
            "torchvision and Meta's sam3 package "
            '(uv pip install torch torchvision "setuptools<81" '
            "git+https://github.com/facebookresearch/sam3.git), accept the "
            "facebook/sam3.1 licence, and put HF_TOKEN in the project .env"
        ) from exc
    kind, device_id = parse_sam_device(device)
    if kind == "cuda" and not bool(torch.cuda.is_available()):
        raise Sam3Unavailable(
            f"torch reports no CUDA device for {device}; check the NVIDIA "
            "driver and that the installed torch build is a CUDA build"
        )
    if kind == "cuda":
        torch.cuda.set_device(device_id or 0)
    checkpoint = _resolve_checkpoint(model, _importer)
    torch_device = f"cuda:{device_id or 0}" if kind == "cuda" else "cpu"
    # The builder moves the weights only for the exact "cuda" string;
    # the index is already selected via torch.cuda.set_device above.
    builder_device = "cuda" if kind == "cuda" else "cpu"
    image_model = model_builder.build_sam3_image_model(
        checkpoint_path=str(checkpoint), device=builder_device, load_from_HF=False
    )
    processor = processor_module.Sam3Processor(image_model, device=builder_device)
    autocast: Callable[[], AbstractContextManager[Any]] | None = None
    if kind == "cuda":
        autocast = lambda: torch.autocast(device_type="cuda", dtype=torch.bfloat16)  # noqa: E731
    return Sam31TorchDetector(processor, prompt=prompt, device=torch_device, autocast=autocast)
