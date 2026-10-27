from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FrameEncoding(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FRAME_ENCODING_UNSPECIFIED: _ClassVar[FrameEncoding]
    FRAME_ENCODING_MJPEG: _ClassVar[FrameEncoding]
    FRAME_ENCODING_RAW_RGB: _ClassVar[FrameEncoding]

class AnalysisMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ANALYSIS_MODE_UNSPECIFIED: _ClassVar[AnalysisMode]
    ANALYSIS_MODE_EVERY_FRAME: _ClassVar[AnalysisMode]
    ANALYSIS_MODE_BEST_EFFORT_DROP: _ClassVar[AnalysisMode]
FRAME_ENCODING_UNSPECIFIED: FrameEncoding
FRAME_ENCODING_MJPEG: FrameEncoding
FRAME_ENCODING_RAW_RGB: FrameEncoding
ANALYSIS_MODE_UNSPECIFIED: AnalysisMode
ANALYSIS_MODE_EVERY_FRAME: AnalysisMode
ANALYSIS_MODE_BEST_EFFORT_DROP: AnalysisMode

class Point3(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

class Point2(_message.Message):
    __slots__ = ("x", "y")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...

class Box(_message.Message):
    __slots__ = ("x_min", "y_min", "x_max", "y_max")
    X_MIN_FIELD_NUMBER: _ClassVar[int]
    Y_MIN_FIELD_NUMBER: _ClassVar[int]
    X_MAX_FIELD_NUMBER: _ClassVar[int]
    Y_MAX_FIELD_NUMBER: _ClassVar[int]
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    def __init__(self, x_min: _Optional[float] = ..., y_min: _Optional[float] = ..., x_max: _Optional[float] = ..., y_max: _Optional[float] = ...) -> None: ...

class StereoCalibration(_message.Message):
    __slots__ = ("calibration_id", "focal_length_px", "baseline_m", "cx", "cy", "width", "height")
    CALIBRATION_ID_FIELD_NUMBER: _ClassVar[int]
    FOCAL_LENGTH_PX_FIELD_NUMBER: _ClassVar[int]
    BASELINE_M_FIELD_NUMBER: _ClassVar[int]
    CX_FIELD_NUMBER: _ClassVar[int]
    CY_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    calibration_id: str
    focal_length_px: float
    baseline_m: float
    cx: float
    cy: float
    width: int
    height: int
    def __init__(self, calibration_id: _Optional[str] = ..., focal_length_px: _Optional[float] = ..., baseline_m: _Optional[float] = ..., cx: _Optional[float] = ..., cy: _Optional[float] = ..., width: _Optional[int] = ..., height: _Optional[int] = ...) -> None: ...

class RawVideoFrame(_message.Message):
    __slots__ = ("frame_id", "t_ns", "channel", "width", "height", "encoding", "data")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    ENCODING_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    channel: int
    width: int
    height: int
    encoding: FrameEncoding
    data: bytes
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., channel: _Optional[int] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., encoding: _Optional[_Union[FrameEncoding, str]] = ..., data: _Optional[bytes] = ...) -> None: ...

class Cm5StreamConfig(_message.Message):
    __slots__ = ("calibration", "video_channels")
    CALIBRATION_FIELD_NUMBER: _ClassVar[int]
    VIDEO_CHANNELS_FIELD_NUMBER: _ClassVar[int]
    calibration: StereoCalibration
    video_channels: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, calibration: _Optional[_Union[StereoCalibration, _Mapping[str, _Any]]] = ..., video_channels: _Optional[_Iterable[int]] = ...) -> None: ...

class Cm5Request(_message.Message):
    __slots__ = ("config", "frame")
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    FRAME_FIELD_NUMBER: _ClassVar[int]
    config: Cm5StreamConfig
    frame: RawVideoFrame
    def __init__(self, config: _Optional[_Union[Cm5StreamConfig, _Mapping[str, _Any]]] = ..., frame: _Optional[_Union[RawVideoFrame, _Mapping[str, _Any]]] = ...) -> None: ...

class PointBatch(_message.Message):
    __slots__ = ("designation", "frame_id", "t_ns", "points")
    DESIGNATION_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    POINTS_FIELD_NUMBER: _ClassVar[int]
    designation: int
    frame_id: int
    t_ns: int
    points: _containers.RepeatedCompositeFieldContainer[Point3]
    def __init__(self, designation: _Optional[int] = ..., frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., points: _Optional[_Iterable[_Union[Point3, _Mapping[str, _Any]]]] = ...) -> None: ...

class VideoFrameOut(_message.Message):
    __slots__ = ("designation", "frame")
    DESIGNATION_FIELD_NUMBER: _ClassVar[int]
    FRAME_FIELD_NUMBER: _ClassVar[int]
    designation: int
    frame: RawVideoFrame
    def __init__(self, designation: _Optional[int] = ..., frame: _Optional[_Union[RawVideoFrame, _Mapping[str, _Any]]] = ...) -> None: ...

class Cm5Response(_message.Message):
    __slots__ = ("points", "video")
    POINTS_FIELD_NUMBER: _ClassVar[int]
    VIDEO_FIELD_NUMBER: _ClassVar[int]
    points: PointBatch
    video: VideoFrameOut
    def __init__(self, points: _Optional[_Union[PointBatch, _Mapping[str, _Any]]] = ..., video: _Optional[_Union[VideoFrameOut, _Mapping[str, _Any]]] = ...) -> None: ...

class ObjectDetection(_message.Message):
    __slots__ = ("label", "score", "box", "track_id")
    LABEL_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    BOX_FIELD_NUMBER: _ClassVar[int]
    TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    label: str
    score: float
    box: Box
    track_id: int
    def __init__(self, label: _Optional[str] = ..., score: _Optional[float] = ..., box: _Optional[_Union[Box, _Mapping[str, _Any]]] = ..., track_id: _Optional[int] = ...) -> None: ...

class FrameDetections(_message.Message):
    __slots__ = ("frame_id", "t_ns", "detections")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    detections: _containers.RepeatedCompositeFieldContainer[ObjectDetection]
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., detections: _Optional[_Iterable[_Union[ObjectDetection, _Mapping[str, _Any]]]] = ...) -> None: ...

class DetectionResponse(_message.Message):
    __slots__ = ("detections",)
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    detections: FrameDetections
    def __init__(self, detections: _Optional[_Union[FrameDetections, _Mapping[str, _Any]]] = ...) -> None: ...

class StationStreamConfig(_message.Message):
    __slots__ = ("calibration", "analysis_mode", "concept_prompts")
    CALIBRATION_FIELD_NUMBER: _ClassVar[int]
    ANALYSIS_MODE_FIELD_NUMBER: _ClassVar[int]
    CONCEPT_PROMPTS_FIELD_NUMBER: _ClassVar[int]
    calibration: StereoCalibration
    analysis_mode: AnalysisMode
    concept_prompts: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, calibration: _Optional[_Union[StereoCalibration, _Mapping[str, _Any]]] = ..., analysis_mode: _Optional[_Union[AnalysisMode, str]] = ..., concept_prompts: _Optional[_Iterable[str]] = ...) -> None: ...

class StationRequest(_message.Message):
    __slots__ = ("config", "frame")
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    FRAME_FIELD_NUMBER: _ClassVar[int]
    config: StationStreamConfig
    frame: RawVideoFrame
    def __init__(self, config: _Optional[_Union[StationStreamConfig, _Mapping[str, _Any]]] = ..., frame: _Optional[_Union[RawVideoFrame, _Mapping[str, _Any]]] = ...) -> None: ...

class SamDetection(_message.Message):
    __slots__ = ("label", "score", "box", "mask_polygon", "track_id")
    LABEL_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    BOX_FIELD_NUMBER: _ClassVar[int]
    MASK_POLYGON_FIELD_NUMBER: _ClassVar[int]
    TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    label: str
    score: float
    box: Box
    mask_polygon: _containers.RepeatedCompositeFieldContainer[Point2]
    track_id: int
    def __init__(self, label: _Optional[str] = ..., score: _Optional[float] = ..., box: _Optional[_Union[Box, _Mapping[str, _Any]]] = ..., mask_polygon: _Optional[_Iterable[_Union[Point2, _Mapping[str, _Any]]]] = ..., track_id: _Optional[int] = ...) -> None: ...

class SamFrameDetections(_message.Message):
    __slots__ = ("frame_id", "detections")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    detections: _containers.RepeatedCompositeFieldContainer[SamDetection]
    def __init__(self, frame_id: _Optional[int] = ..., detections: _Optional[_Iterable[_Union[SamDetection, _Mapping[str, _Any]]]] = ...) -> None: ...

class StationResponse(_message.Message):
    __slots__ = ("detections",)
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    detections: SamFrameDetections
    def __init__(self, detections: _Optional[_Union[SamFrameDetections, _Mapping[str, _Any]]] = ...) -> None: ...
