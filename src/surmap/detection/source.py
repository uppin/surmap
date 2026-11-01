"""Detection sources: the detector+tracker behind both CM5 surfaces.

`CoralDetectionSource` is the one place detection runs: a
`CoralDetector` plus an `IouTracker`, serialized by a lock (one
accelerator, one tracker state). It feeds two independent surfaces:

- the separate `StreamDetections` wire stream — detections are
  emitted on their own cadence, keyed by `frame_id`, and are never
  attached to survey output frames;
- `CoralObjectPointSource`, the `ObjectPointSource` for
  `StreamSurvey`: tracked boxes select the stereo scene points that
  fall inside them, and those points are lifted to map-frame object
  points under the object's track designation.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from surmap.detection.detector import CoralDetector, decode_rgb
from surmap.detection.tracker import IouTracker, TrackedDetection
from surmap.geometry import centroid, to_map_frame
from surmap.survey.stereo import FrameImage, StereoRig
from surmap.types import ObjectPoints, Pose, StereoFramePair, Vec3


@runtime_checkable
class DetectionSource(Protocol):
    """Tracked detections for one frame, on the source's own cadence."""

    def detect_tracked(
        self, frame_id: int, rgb: NDArray[np.uint8]
    ) -> tuple[TrackedDetection, ...]: ...


class StereoSource(Protocol):
    """The stereo reconstructor seam the object source lifts with."""

    def reconstruct(
        self, left: FrameImage, right: FrameImage, rig: StereoRig
    ) -> tuple[Vec3, ...]: ...


class CoralDetectionSource:
    """`DetectionSource` backed by the Coral detector and IoU tracker."""

    def __init__(self, detector: CoralDetector, tracker: IouTracker | None = None) -> None:
        self._detector = detector
        self._tracker = tracker if tracker is not None else IouTracker()
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        """The detector's model artifact name (profile twin in use)."""
        return self._detector.model_id

    @property
    def provider(self) -> str:
        return "Coral"

    @property
    def device(self) -> str:
        """Where inference runs: the Edge TPU for `_edgetpu` artifacts."""
        return "edgetpu" if "_edgetpu" in self._detector.model_id else "cpu"

    def detect_tracked(self, frame_id: int, rgb: NDArray[np.uint8]) -> tuple[TrackedDetection, ...]:
        with self._lock:
            detections = self._detector.detect(rgb, frame_id)
            return self._tracker.update(frame_id, detections)


class CoralObjectPointSource:
    """`ObjectPointSource`: tracked objects' stereo points, map frame."""

    def __init__(
        self,
        source: DetectionSource,
        stereo: StereoSource,
        rig: StereoRig | None = None,
        *,
        min_points: int = 3,
    ) -> None:
        self._source = source
        self._stereo = stereo
        self._rig = rig
        self._min_points = min_points

    def points_for_pair(
        self, pair: StereoFramePair, pose: Pose | None, rig: StereoRig | None = None
    ) -> tuple[ObjectPoints, ...]:
        # The rig usually arrives with the pair: the CM5 process learns
        # it from each survey stream's config, not at startup. A rig
        # fixed at construction remains as the fallback.
        rig = rig if rig is not None else self._rig
        if pose is None or rig is None or not pair.left_data or not pair.right_data:
            return ()
        try:
            # Dimensions are taken from the decoded image itself.
            rgb = decode_rgb(FrameImage(0, 0, "mjpeg", pair.left_data))
            camera_points = self._stereo.reconstruct(
                FrameImage(rgb.shape[1], rgb.shape[0], "mjpeg", pair.left_data),
                FrameImage(rgb.shape[1], rgb.shape[0], "mjpeg", pair.right_data),
                rig,
            )
        except ValueError:
            return ()
        tracked = self._source.detect_tracked(pair.frame_id, rgb)
        if not tracked or not camera_points:
            return ()
        projected: list[tuple[float, float, Vec3]] = []
        for point in camera_points:
            if point.z <= 0.05:
                continue
            projected.append(
                (
                    rig.fx * point.x / point.z + rig.cx,
                    rig.fy * point.y / point.z + rig.cy,
                    point,
                )
            )
        observations: list[ObjectPoints] = []
        for detection in tracked:
            x_min, y_min, x_max, y_max = detection.box_xyxy
            inside = tuple(
                point for u, v, point in projected if x_min <= u <= x_max and y_min <= v <= y_max
            )
            if len(inside) < self._min_points:
                continue
            map_points = tuple(to_map_frame(point, pose) for point in inside)
            observations.append(
                ObjectPoints(
                    track_id=detection.track_id,
                    frame_id=pair.frame_id,
                    t_ns=pair.t_ns,
                    points=map_points,
                    centroid=centroid(map_points),
                )
            )
        return tuple(observations)
