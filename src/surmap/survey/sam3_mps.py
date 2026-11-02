"""Meta's `sam3` on Apple's GPU (MPS): the vendor's CUDA-only corners, contained.

The `sam3` package is written for NVIDIA GPUs. Its image model runs on
MPS once three things are taken care of, all inside the vendor package
and only when the demo asks for `mps`:

- `sam3.model.edt` imports `triton`, which does not exist on macOS. Its
  `edt_triton` only samples corrective clicks for interactive
  refinement, which a concept prompt never asks for; a stand-in that
  fails by name replaces it, so the package imports.
- Vendor modules create tensors, devices and autocast contexts with an
  explicit `"cuda"`. Each vendor module's `torch` is swapped for
  `OnDevice`, which reads `"cuda"` as the target device; torch itself
  and every other module are untouched.
- `sam3.perflib.fused` calls `aten::_addmm_activation`, which has no MPS
  kernel. It is replaced by the same matmul followed by exact GELU
  (or ReLU) — on CPU the fused op and this agree exactly.

Inference then runs under bf16 autocast on MPS, as it does on CUDA. The
multiplex video model is not covered: it queries CUDA as it imports.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
import types
from collections.abc import Callable
from typing import Any

# Vendor subpackages the image model never loads (training, agents,
# evaluation, CUDA-only kernels); some import optional extras.
_SKIPPED = (".train", ".agent", ".eval", ".perflib.triton", ".perflib.fa3")


def _is_cuda(device: object) -> bool:
    text = str(device)
    return text == "cuda" or text.startswith("cuda:")


class OnDevice:
    """A vendor module's view of torch in which explicit `"cuda"` means `target`."""

    def __init__(self, torch: Any, target: str) -> None:
        self._torch = torch
        self._target = target

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._torch, name)
        target = self._target
        if name == "device":

            def device(*args: Any, **kwargs: Any) -> Any:
                if args and _is_cuda(args[0]):
                    return attribute(target, *args[1:], **kwargs)
                return attribute(*args, **kwargs)

            return device
        if name == "autocast":

            def autocast(*args: Any, **kwargs: Any) -> Any:
                if kwargs.get("device_type") == "cuda":
                    kwargs["device_type"] = target
                return attribute(*args, **kwargs)

            return autocast
        if callable(attribute) and not isinstance(attribute, type):

            def call(*args: Any, **kwargs: Any) -> Any:
                if _is_cuda(kwargs.get("device")):
                    kwargs["device"] = target
                return attribute(*args, **kwargs)

            return call
        return attribute


def unfused_addmm_activation(torch: Any) -> Callable[..., Any]:
    """`aten::_addmm_activation` as an addmm followed by exact GELU or ReLU."""

    def addmm_activation(
        bias: Any, mat1: Any, mat2: Any, beta: float = 1, alpha: float = 1, use_gelu: bool = False
    ) -> Any:
        out = torch.addmm(bias, mat1, mat2, beta=beta, alpha=alpha)
        return torch.nn.functional.gelu(out) if use_gelu else torch.relu(out)

    return addmm_activation


def _edt_unavailable(data: object) -> object:
    raise NotImplementedError(
        "edt_triton needs CUDA triton; on MPS only concept prompts are supported "
        "(it samples corrective clicks for interactive refinement)"
    )


def prepare_sam3_for_mps(torch: Any, *, package: str = "sam3") -> None:
    """Make the vendor `package` import and run on MPS (see module docs)."""
    if importlib.util.find_spec("triton") is None:
        edt = types.ModuleType(f"{package}.model.edt")
        edt.__dict__["edt_triton"] = _edt_unavailable
        sys.modules.setdefault(f"{package}.model.edt", edt)
    root = importlib.import_module(package)
    for info in pkgutil.walk_packages(root.__path__, f"{package}."):
        if any(skipped in info.name for skipped in _SKIPPED):
            continue
        try:
            module = importlib.import_module(info.name)
        except Exception:
            continue  # optional extras and CUDA-only modules stay unloaded
        if getattr(module, "torch", None) is torch:
            module.__dict__["torch"] = OnDevice(torch, "mps")
    fused = sys.modules.get(f"{package}.perflib.fused")
    if fused is not None:
        fused.__dict__["addmm_act_op"] = unfused_addmm_activation(torch)
