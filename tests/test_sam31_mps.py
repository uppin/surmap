"""SAM 3.1 on Apple's GPU (MPS): the vendor's CUDA-only corners, contained (no torch needed)."""

import io
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from surmap.survey.sam import RawFrame
from surmap.survey.sam3 import Sam3Unavailable, parse_sam_device
from surmap.survey.sam3_mps import OnDevice, prepare_sam3_for_mps, unfused_addmm_activation
from surmap.survey.sam3_torch import (
    Sam31TorchDetector,
    Sam31TorchVideoDetector,
    sam31_torch_detector,
)
from tests.test_sam31_torch import FakeProcessor


class FakeTorch:
    """Records the calls a vendor module makes through its `torch`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.nn = type("nn", (), {"functional": self})()

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            self.calls.append((name, args, kwargs))
            return (name, args, kwargs)

        return call


def test_metal_is_a_sam_device() -> None:
    assert parse_sam_device("mps") == ("mps", None)


def test_the_vendors_cuda_tensors_are_made_on_the_apple_gpu() -> None:
    # Given the vendor's torch, seen through the MPS redirect
    real = FakeTorch()
    vendor_torch = OnDevice(real, "mps")

    # When vendor code asks for CUDA tensors, devices and autocast
    vendor_torch.zeros((1, 2), device="cuda")
    vendor_torch.arange(4, device="cuda:0")
    vendor_torch.device("cuda")
    vendor_torch.autocast(device_type="cuda", dtype="bf16")
    vendor_torch.ones(3, device="cpu")

    # Then every CUDA request lands on MPS, and others are left alone
    assert real.calls == [
        ("zeros", ((1, 2),), {"device": "mps"}),
        ("arange", (4,), {"device": "mps"}),
        ("device", ("mps",), {}),
        ("autocast", (), {"device_type": "mps", "dtype": "bf16"}),
        ("ones", (3,), {"device": "cpu"}),
    ]


def test_the_fused_linear_activation_is_an_addmm_then_its_activation() -> None:
    # Given the unfused stand-in for aten::_addmm_activation (no MPS kernel)
    torch = FakeTorch()
    addmm_activation = unfused_addmm_activation(torch)

    # When GELU and ReLU variants run
    addmm_activation("bias", "x", "w", beta=1, alpha=1, use_gelu=True)
    addmm_activation("bias", "x", "w", beta=1, alpha=1, use_gelu=False)

    # Then each is the matmul followed by exact GELU / ReLU
    matmul = ("addmm", ("bias", "x", "w"), {"beta": 1, "alpha": 1})
    assert [call[0] for call in torch.calls] == ["addmm", "gelu", "addmm", "relu"]
    assert torch.calls[0] == matmul and torch.calls[1][1] == (matmul,)


@pytest.fixture()
def a_vendor_package(tmp_path: Path) -> Iterator[str]:
    """A tiny stand-in for Meta's sam3: one triton import, one CUDA tensor, one fused op."""
    root = tmp_path / "fakesam3"
    (root / "model").mkdir(parents=True)
    (root / "perflib").mkdir()
    (root / "__init__.py").write_text("")
    (root / "model" / "__init__.py").write_text("")
    (root / "perflib" / "__init__.py").write_text("")
    (root / "model" / "edt.py").write_text("import triton\n")
    (root / "model" / "encoding.py").write_text(
        textwrap.dedent(
            """
            from fakesam3.model.edt import edt_triton  # noqa: F401
            import torch


            def table():
                return torch.zeros((1, 1), device="cuda")
            """
        )
    )
    (root / "perflib" / "fused.py").write_text("addmm_act_op = 'fused'\n")
    sys.path.insert(0, str(tmp_path))
    try:
        yield "fakesam3"
    finally:
        sys.path.remove(str(tmp_path))
        for name in [name for name in sys.modules if name.startswith("fakesam3")]:
            del sys.modules[name]


def test_the_vendor_package_is_prepared_for_mps_without_triton(
    a_vendor_package: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a vendor package that imports triton (not on macOS) and makes CUDA tensors
    torch = FakeTorch()
    monkeypatch.setitem(sys.modules, "torch", torch)

    # When it is prepared for MPS
    prepare_sam3_for_mps(torch, package=a_vendor_package)

    # Then it imports, its CUDA tensors land on MPS, and its fused op is unfused
    encoding = sys.modules[f"{a_vendor_package}.model.encoding"]
    encoding.table()
    assert torch.calls[-1] == ("zeros", ((1, 1),), {"device": "mps"})
    with pytest.raises(NotImplementedError, match="triton"):
        sys.modules[f"{a_vendor_package}.model.edt"].edt_triton(None)
    assert sys.modules[f"{a_vendor_package}.perflib.fused"].addmm_act_op != "fused"


class FakeMps:
    def __init__(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class FakeImageModel:
    def __init__(self) -> None:
        self.moved_to: list[str] = []

    def to(self, device: str) -> "FakeImageModel":
        self.moved_to.append(device)
        return self


def a_fake_stack(built: dict[str, Any], mps_available: bool = True) -> dict[str, Any]:
    model = FakeImageModel()
    built["model"] = model

    class FakeBuilder:
        def build_sam3_image_model(self, **kwargs: Any) -> FakeImageModel:
            built.update(kwargs)
            return model

    class FakeProcessorModule:
        class Sam3Processor:
            def __init__(self, image_model: object, device: str = "cpu") -> None:
                built["processor_device"] = device

    torch = type(
        "FakeTorch",
        (),
        {
            "backends": type("backends", (), {"mps": FakeMps(mps_available)})(),
            "bfloat16": "bf16",
            "autocast": staticmethod(lambda **kwargs: built.setdefault("autocast", kwargs)),
        },
    )()
    return {
        "torch": torch,
        "sam3.model_builder": FakeBuilder(),
        "sam3.model.sam3_image_processor": FakeProcessorModule(),
    }


def test_the_torch_detector_runs_on_the_apple_gpu(tmp_path: Path) -> None:
    # Given a local checkpoint and a fake torch/sam3 stack with MPS
    checkpoint = tmp_path / "sam3.1_multiplex.pt"
    checkpoint.write_bytes(b"fake")
    built: dict[str, Any] = {}
    prepared: list[object] = []
    modules = a_fake_stack(built)

    # When the detector is built for mps
    detector = sam31_torch_detector(
        str(checkpoint), device="mps", _importer=modules.__getitem__, _prepare_mps=prepared.append
    )

    # Then the vendor was prepared first, weights load on CPU and move to the GPU
    assert isinstance(detector, Sam31TorchDetector) and detector.device == "mps"
    assert prepared == [modules["torch"]]
    assert built["device"] == "cpu" and built["model"].moved_to == ["mps"]
    assert built["processor_device"] == "mps"


def test_the_torch_detector_names_a_mac_without_metal(tmp_path: Path) -> None:
    checkpoint = tmp_path / "sam3.1_multiplex.pt"
    checkpoint.write_bytes(b"fake")
    modules = a_fake_stack({}, mps_available=False)

    with pytest.raises(Sam3Unavailable, match="MPS"):
        sam31_torch_detector(
            str(checkpoint), device="mps", _importer=modules.__getitem__, _prepare_mps=print
        )


def a_frame(frame_id: int) -> RawFrame:
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (10, 10, 10)).save(buffer, format="JPEG")
    return RawFrame(frame_id, frame_id * 100, 0, 256, 256, "mjpeg", buffer.getvalue())


def test_the_image_model_tracks_a_video_with_persistent_ids() -> None:
    # Given SAM 3.1's image model over a video where the same box stays put
    video = Sam31TorchVideoDetector(Sam31TorchDetector(FakeProcessor(), prompt="car"))

    # When two frames are tracked
    first = video.track(a_frame(1))
    second = video.track(a_frame(2))

    # Then the object keeps one track id
    assert [d.track_id for d in first] == [1] and [d.track_id for d in second] == [1]


def test_a_new_video_restarts_ids_and_looks_for_its_own_concept() -> None:
    # Given a video detector that tracked a car
    processor = FakeProcessor()
    video = Sam31TorchVideoDetector(Sam31TorchDetector(processor, prompt="car"))
    video.track(a_frame(1))

    # When a new video starts, prompted "truck"
    video.reset("truck")
    (detection,) = video.track(a_frame(1))

    # Then SAM looks for trucks and ids start over
    assert processor.prompts[-1] == "truck"
    assert detection.label == "truck" and detection.track_id == 1


def test_the_demo_runs_sam31_on_the_apple_gpu_as_a_video_detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import surmap.survey.sam3_torch as sam3_torch
    from surmap.demo.server import _DemoHttpServer, make_demo_server
    from surmap.survey.sam import InMemoryVideoSamDetector
    from tests.test_demo import _prepared_tiny

    # Given SAM 3.1 built for mps (faked: the real one needs the Apple GPU)
    asked: list[tuple[str, str, str]] = []
    detector = InMemoryVideoSamDetector()

    def build(model: str, *, device: str, prompt: str) -> InMemoryVideoSamDetector:
        asked.append((model, device, prompt))
        return detector

    monkeypatch.setattr(sam3_torch, "sam31_torch_video_detector", build)

    # When the demo is started on mps
    server = make_demo_server(
        _prepared_tiny(tmp_path),
        host="127.0.0.1",
        port=0,
        with_rtabmap=False,
        sam_device="mps",
        sam_label="car",
    )
    server.server_close()

    # Then it runs the image model per frame, as a video detector
    assert asked == [("facebook/sam3.1", "mps", "car")]
    assert isinstance(server, _DemoHttpServer)
    assert server.player_options["sam_source"] is detector
