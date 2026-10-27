"""Selectable Coral detector model profiles.

One profile = the two pinned artifacts of one INT8 network (the
Edge-TPU-compiled file for Coral boards and its CPU twin for
CI/local proof) in a prepared model dir. Every surface that chooses
a detector model — `cm5_main --coral-model`, the demo, the deploy
scripts — picks a profile name from this registry; tooling
(`scripts/fetch_coral_model.py`) fetches all of them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    title: str
    edgetpu_file: str
    cpu_file: str
    note: str

    def file_for(self, *, use_edgetpu: bool) -> str:
        return self.edgetpu_file if use_edgetpu else self.cpu_file


MODEL_PROFILES: dict[str, ModelProfile] = {
    "efficientdet-lite0": ModelProfile(
        name="efficientdet-lite0",
        title="EfficientDet-Lite0",
        edgetpu_file="efficientdet_lite0_320_ptq_edgetpu.tflite",
        cpu_file="efficientdet_lite0_320_ptq.tflite",
        note="default; best hit rate on the EuRoC footage in local probes",
    ),
    "ssd-mobilenet-v2": ModelProfile(
        name="ssd-mobilenet-v2",
        title="SSD MobileNet V2",
        edgetpu_file="ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite",
        cpu_file="ssd_mobilenet_v2_coco_quant_postprocess.tflite",
        note="fastest of the set; weakest hit rate on the EuRoC footage",
    ),
    "ssdlite-mobiledet": ModelProfile(
        name="ssdlite-mobiledet",
        title="SSDLite MobileDet",
        edgetpu_file="ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite",
        cpu_file="ssdlite_mobiledet_coco_qat_postprocess.tflite",
        note="designed for edge accelerators; smallest Edge TPU artifact",
    ),
}

DEFAULT_PROFILE = "efficientdet-lite0"
