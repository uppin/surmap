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

class MovingVerdict(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MOVING_VERDICT_UNKNOWN: _ClassVar[MovingVerdict]
    MOVING_VERDICT_RIGID_MOVER: _ClassVar[MovingVerdict]
    MOVING_VERDICT_OSCILLATING: _ClassVar[MovingVerdict]

class IdentitySource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    IDENTITY_SOURCE_DETECTOR: _ClassVar[IdentitySource]
    IDENTITY_SOURCE_AREA_ALLOCATED: _ClassVar[IdentitySource]

class RegionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REGION_STATUS_UNSPECIFIED: _ClassVar[RegionStatus]
    REGION_STATUS_OK: _ClassVar[RegionStatus]
    REGION_STATUS_FRAME_EXPIRED: _ClassVar[RegionStatus]
    REGION_STATUS_NO_POSE: _ClassVar[RegionStatus]
    REGION_STATUS_INVALID_QUERY: _ClassVar[RegionStatus]
FRAME_ENCODING_UNSPECIFIED: FrameEncoding
FRAME_ENCODING_MJPEG: FrameEncoding
FRAME_ENCODING_RAW_RGB: FrameEncoding
ANALYSIS_MODE_UNSPECIFIED: AnalysisMode
ANALYSIS_MODE_EVERY_FRAME: AnalysisMode
ANALYSIS_MODE_BEST_EFFORT_DROP: AnalysisMode
MOVING_VERDICT_UNKNOWN: MovingVerdict
MOVING_VERDICT_RIGID_MOVER: MovingVerdict
MOVING_VERDICT_OSCILLATING: MovingVerdict
IDENTITY_SOURCE_DETECTOR: IdentitySource
IDENTITY_SOURCE_AREA_ALLOCATED: IdentitySource
REGION_STATUS_UNSPECIFIED: RegionStatus
REGION_STATUS_OK: RegionStatus
REGION_STATUS_FRAME_EXPIRED: RegionStatus
REGION_STATUS_NO_POSE: RegionStatus
REGION_STATUS_INVALID_QUERY: RegionStatus

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
    __slots__ = ("calibration", "video_channels", "cam0_yaml", "cam1_yaml", "max_depth_m")
    CALIBRATION_FIELD_NUMBER: _ClassVar[int]
    VIDEO_CHANNELS_FIELD_NUMBER: _ClassVar[int]
    CAM0_YAML_FIELD_NUMBER: _ClassVar[int]
    CAM1_YAML_FIELD_NUMBER: _ClassVar[int]
    MAX_DEPTH_M_FIELD_NUMBER: _ClassVar[int]
    calibration: StereoCalibration
    video_channels: _containers.RepeatedScalarFieldContainer[int]
    cam0_yaml: str
    cam1_yaml: str
    max_depth_m: float
    def __init__(self, calibration: _Optional[_Union[StereoCalibration, _Mapping[str, _Any]]] = ..., video_channels: _Optional[_Iterable[int]] = ..., cam0_yaml: _Optional[str] = ..., cam1_yaml: _Optional[str] = ..., max_depth_m: _Optional[float] = ...) -> None: ...

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

class TrackedKeypoint(_message.Message):
    __slots__ = ("word_id", "u", "v", "depth")
    WORD_ID_FIELD_NUMBER: _ClassVar[int]
    U_FIELD_NUMBER: _ClassVar[int]
    V_FIELD_NUMBER: _ClassVar[int]
    DEPTH_FIELD_NUMBER: _ClassVar[int]
    word_id: int
    u: float
    v: float
    depth: float
    def __init__(self, word_id: _Optional[int] = ..., u: _Optional[float] = ..., v: _Optional[float] = ..., depth: _Optional[float] = ...) -> None: ...

class RectificationOut(_message.Message):
    __slots__ = ("rotation", "rectified", "raw", "distortion")
    ROTATION_FIELD_NUMBER: _ClassVar[int]
    RECTIFIED_FIELD_NUMBER: _ClassVar[int]
    RAW_FIELD_NUMBER: _ClassVar[int]
    DISTORTION_FIELD_NUMBER: _ClassVar[int]
    rotation: _containers.RepeatedScalarFieldContainer[float]
    rectified: _containers.RepeatedScalarFieldContainer[float]
    raw: _containers.RepeatedScalarFieldContainer[float]
    distortion: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, rotation: _Optional[_Iterable[float]] = ..., rectified: _Optional[_Iterable[float]] = ..., raw: _Optional[_Iterable[float]] = ..., distortion: _Optional[_Iterable[float]] = ...) -> None: ...

class OdomUpdateOut(_message.Message):
    __slots__ = ("frame_id", "t_ns", "position", "orientation_xyzw", "map_position", "map_orientation_xyzw", "keypoints", "rectification")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    ORIENTATION_XYZW_FIELD_NUMBER: _ClassVar[int]
    MAP_POSITION_FIELD_NUMBER: _ClassVar[int]
    MAP_ORIENTATION_XYZW_FIELD_NUMBER: _ClassVar[int]
    KEYPOINTS_FIELD_NUMBER: _ClassVar[int]
    RECTIFICATION_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    position: Point3
    orientation_xyzw: _containers.RepeatedScalarFieldContainer[float]
    map_position: Point3
    map_orientation_xyzw: _containers.RepeatedScalarFieldContainer[float]
    keypoints: _containers.RepeatedCompositeFieldContainer[TrackedKeypoint]
    rectification: RectificationOut
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., position: _Optional[_Union[Point3, _Mapping[str, _Any]]] = ..., orientation_xyzw: _Optional[_Iterable[float]] = ..., map_position: _Optional[_Union[Point3, _Mapping[str, _Any]]] = ..., map_orientation_xyzw: _Optional[_Iterable[float]] = ..., keypoints: _Optional[_Iterable[_Union[TrackedKeypoint, _Mapping[str, _Any]]]] = ..., rectification: _Optional[_Union[RectificationOut, _Mapping[str, _Any]]] = ...) -> None: ...

class Cm5Response(_message.Message):
    __slots__ = ("points", "video", "odom")
    POINTS_FIELD_NUMBER: _ClassVar[int]
    VIDEO_FIELD_NUMBER: _ClassVar[int]
    ODOM_FIELD_NUMBER: _ClassVar[int]
    points: PointBatch
    video: VideoFrameOut
    odom: OdomUpdateOut
    def __init__(self, points: _Optional[_Union[PointBatch, _Mapping[str, _Any]]] = ..., video: _Optional[_Union[VideoFrameOut, _Mapping[str, _Any]]] = ..., odom: _Optional[_Union[OdomUpdateOut, _Mapping[str, _Any]]] = ...) -> None: ...

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

class MovingArea(_message.Message):
    __slots__ = ("frame_id", "t_ns", "polygon", "depth_min_m", "depth_max_m", "dynamic_point_count", "area_track_id", "verdict", "verdict_version")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    POLYGON_FIELD_NUMBER: _ClassVar[int]
    DEPTH_MIN_M_FIELD_NUMBER: _ClassVar[int]
    DEPTH_MAX_M_FIELD_NUMBER: _ClassVar[int]
    DYNAMIC_POINT_COUNT_FIELD_NUMBER: _ClassVar[int]
    AREA_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    VERDICT_VERSION_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    polygon: _containers.RepeatedCompositeFieldContainer[Point2]
    depth_min_m: float
    depth_max_m: float
    dynamic_point_count: int
    area_track_id: int
    verdict: MovingVerdict
    verdict_version: int
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., polygon: _Optional[_Iterable[_Union[Point2, _Mapping[str, _Any]]]] = ..., depth_min_m: _Optional[float] = ..., depth_max_m: _Optional[float] = ..., dynamic_point_count: _Optional[int] = ..., area_track_id: _Optional[int] = ..., verdict: _Optional[_Union[MovingVerdict, str]] = ..., verdict_version: _Optional[int] = ...) -> None: ...

class MovingObjectSnapshot(_message.Message):
    __slots__ = ("frame_id", "t_ns", "area_track_id", "object_track_id", "identity_source", "verdict", "keypoints", "centroid", "velocity")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    AREA_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_TRACK_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTITY_SOURCE_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    KEYPOINTS_FIELD_NUMBER: _ClassVar[int]
    CENTROID_FIELD_NUMBER: _ClassVar[int]
    VELOCITY_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    area_track_id: int
    object_track_id: int
    identity_source: IdentitySource
    verdict: MovingVerdict
    keypoints: _containers.RepeatedCompositeFieldContainer[Point3]
    centroid: Point3
    velocity: Point3
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., area_track_id: _Optional[int] = ..., object_track_id: _Optional[int] = ..., identity_source: _Optional[_Union[IdentitySource, str]] = ..., verdict: _Optional[_Union[MovingVerdict, str]] = ..., keypoints: _Optional[_Iterable[_Union[Point3, _Mapping[str, _Any]]]] = ..., centroid: _Optional[_Union[Point3, _Mapping[str, _Any]]] = ..., velocity: _Optional[_Union[Point3, _Mapping[str, _Any]]] = ...) -> None: ...

class MovingAreasResponse(_message.Message):
    __slots__ = ("area", "snapshot")
    AREA_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    area: MovingArea
    snapshot: MovingObjectSnapshot
    def __init__(self, area: _Optional[_Union[MovingArea, _Mapping[str, _Any]]] = ..., snapshot: _Optional[_Union[MovingObjectSnapshot, _Mapping[str, _Any]]] = ...) -> None: ...

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
    __slots__ = ("frame_id", "detections", "provider", "device")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    detections: _containers.RepeatedCompositeFieldContainer[SamDetection]
    provider: str
    device: str
    def __init__(self, frame_id: _Optional[int] = ..., detections: _Optional[_Iterable[_Union[SamDetection, _Mapping[str, _Any]]]] = ..., provider: _Optional[str] = ..., device: _Optional[str] = ...) -> None: ...

class StationResponse(_message.Message):
    __slots__ = ("detections",)
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    detections: SamFrameDetections
    def __init__(self, detections: _Optional[_Union[SamFrameDetections, _Mapping[str, _Any]]] = ...) -> None: ...

class RegionQuery(_message.Message):
    __slots__ = ("query_id", "frame_id", "channel", "width", "height", "polygon")
    QUERY_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    POLYGON_FIELD_NUMBER: _ClassVar[int]
    query_id: int
    frame_id: int
    channel: int
    width: int
    height: int
    polygon: _containers.RepeatedCompositeFieldContainer[Point2]
    def __init__(self, query_id: _Optional[int] = ..., frame_id: _Optional[int] = ..., channel: _Optional[int] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., polygon: _Optional[_Iterable[_Union[Point2, _Mapping[str, _Any]]]] = ...) -> None: ...

class RegionPoints(_message.Message):
    __slots__ = ("query_id", "frame_id", "channel", "status", "points", "final")
    QUERY_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    POINTS_FIELD_NUMBER: _ClassVar[int]
    FINAL_FIELD_NUMBER: _ClassVar[int]
    query_id: int
    frame_id: int
    channel: int
    status: RegionStatus
    points: _containers.RepeatedCompositeFieldContainer[Point3]
    final: bool
    def __init__(self, query_id: _Optional[int] = ..., frame_id: _Optional[int] = ..., channel: _Optional[int] = ..., status: _Optional[_Union[RegionStatus, str]] = ..., points: _Optional[_Iterable[_Union[Point3, _Mapping[str, _Any]]]] = ..., final: bool = ...) -> None: ...

class CapabilitiesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Capabilities(_message.Message):
    __slots__ = ("service", "detections", "object_points", "moving_areas", "region_points", "sam_analysis", "provider", "device", "slam")
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    OBJECT_POINTS_FIELD_NUMBER: _ClassVar[int]
    MOVING_AREAS_FIELD_NUMBER: _ClassVar[int]
    REGION_POINTS_FIELD_NUMBER: _ClassVar[int]
    SAM_ANALYSIS_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    SLAM_FIELD_NUMBER: _ClassVar[int]
    service: str
    detections: bool
    object_points: bool
    moving_areas: bool
    region_points: bool
    sam_analysis: bool
    provider: str
    device: str
    slam: str
    def __init__(self, service: _Optional[str] = ..., detections: bool = ..., object_points: bool = ..., moving_areas: bool = ..., region_points: bool = ..., sam_analysis: bool = ..., provider: _Optional[str] = ..., device: _Optional[str] = ..., slam: _Optional[str] = ...) -> None: ...
