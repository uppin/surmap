"""Camera calibration: checkerboard target, session guidance, RPC.

Hexagon: `port.CheckerboardVision` is the seam; adapters are the
OpenCV sidecar (`opencv_sidecar.OpenCvSidecarVision`); tests script
their own. The simulated
board (`simulated.SimulatedCheckerboard`) renders known-truth views.
"""

from surmap.calibration.baseline import rescale_baseline
from surmap.calibration.board import CheckerboardSpec
from surmap.calibration.plan import Tilt, Viewpoint, capture_plan
from surmap.calibration.port import (
    CalibrationUnavailable,
    CalibrationView,
    CheckerboardVision,
    EncodedFrame,
    LensModel,
    StereoEstimate,
    UnreadableFrame,
)
from surmap.calibration.session import CalibrationSession, MoveSuggestion, ViewFeedback, ViewStatus
from surmap.calibration.simulated import BoardPose, RenderedPair, SimulatedCheckerboard, StereoRig

__all__ = [
    "BoardPose",
    "CalibrationSession",
    "CalibrationUnavailable",
    "CalibrationView",
    "CheckerboardSpec",
    "CheckerboardVision",
    "EncodedFrame",
    "LensModel",
    "MoveSuggestion",
    "RenderedPair",
    "SimulatedCheckerboard",
    "StereoEstimate",
    "StereoRig",
    "Tilt",
    "UnreadableFrame",
    "ViewFeedback",
    "ViewStatus",
    "Viewpoint",
    "capture_plan",
    "rescale_baseline",
]
