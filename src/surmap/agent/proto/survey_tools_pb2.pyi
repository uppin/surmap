from surmap.agent.proto import execution_pb2 as _execution_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Shape(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SHAPE_UNSPECIFIED: _ClassVar[Shape]
    LINEAR: _ClassVar[Shape]
    PLANAR: _ClassVar[Shape]
    VOLUMETRIC: _ClassVar[Shape]

class Relation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RELATION_UNSPECIFIED: _ClassVar[Relation]
    ABOVE: _ClassVar[Relation]
    BELOW: _ClassVar[Relation]
    NEXT_TO: _ClassVar[Relation]
    OVERLAPS: _ClassVar[Relation]

class FrameSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FRAME_SOURCE_UNSPECIFIED: _ClassVar[FrameSource]
    FULL: _ClassVar[FrameSource]
    DISPLAY: _ClassVar[FrameSource]

class DatasetModality(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MODALITY_UNSPECIFIED: _ClassVar[DatasetModality]
    GREY: _ClassVar[DatasetModality]
    COLOR: _ClassVar[DatasetModality]
SHAPE_UNSPECIFIED: Shape
LINEAR: Shape
PLANAR: Shape
VOLUMETRIC: Shape
RELATION_UNSPECIFIED: Relation
ABOVE: Relation
BELOW: Relation
NEXT_TO: Relation
OVERLAPS: Relation
FRAME_SOURCE_UNSPECIFIED: FrameSource
FULL: FrameSource
DISPLAY: FrameSource
MODALITY_UNSPECIFIED: DatasetModality
GREY: DatasetModality
COLOR: DatasetModality

class Vec3(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

class PixelBox(_message.Message):
    __slots__ = ("x0", "y0", "x1", "y1")
    X0_FIELD_NUMBER: _ClassVar[int]
    Y0_FIELD_NUMBER: _ClassVar[int]
    X1_FIELD_NUMBER: _ClassVar[int]
    Y1_FIELD_NUMBER: _ClassVar[int]
    x0: float
    y0: float
    x1: float
    y1: float
    def __init__(self, x0: _Optional[float] = ..., y0: _Optional[float] = ..., x1: _Optional[float] = ..., y1: _Optional[float] = ...) -> None: ...

class PixelPoint(_message.Message):
    __slots__ = ("x", "y")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ...) -> None: ...

class ListDemosRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DemoScene(_message.Message):
    __slots__ = ("id", "title", "default_prompt", "prepared", "cached_run_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_PROMPT_FIELD_NUMBER: _ClassVar[int]
    PREPARED_FIELD_NUMBER: _ClassVar[int]
    CACHED_RUN_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    default_prompt: str
    prepared: bool
    cached_run_id: str
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., default_prompt: _Optional[str] = ..., prepared: bool = ..., cached_run_id: _Optional[str] = ...) -> None: ...

class ListDemosResponse(_message.Message):
    __slots__ = ("scenes",)
    SCENES_FIELD_NUMBER: _ClassVar[int]
    scenes: _containers.RepeatedCompositeFieldContainer[DemoScene]
    def __init__(self, scenes: _Optional[_Iterable[_Union[DemoScene, _Mapping[str, _Any]]]] = ...) -> None: ...

class ListOnboardModelsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class OnboardModel(_message.Message):
    __slots__ = ("name", "title", "note", "available", "is_default", "classes")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    NOTE_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    IS_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    CLASSES_FIELD_NUMBER: _ClassVar[int]
    name: str
    title: str
    note: str
    available: bool
    is_default: bool
    classes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, name: _Optional[str] = ..., title: _Optional[str] = ..., note: _Optional[str] = ..., available: bool = ..., is_default: bool = ..., classes: _Optional[_Iterable[str]] = ...) -> None: ...

class ListOnboardModelsResponse(_message.Message):
    __slots__ = ("models", "default_model")
    MODELS_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_MODEL_FIELD_NUMBER: _ClassVar[int]
    models: _containers.RepeatedCompositeFieldContainer[OnboardModel]
    default_model: str
    def __init__(self, models: _Optional[_Iterable[_Union[OnboardModel, _Mapping[str, _Any]]]] = ..., default_model: _Optional[str] = ...) -> None: ...

class RunDemoRequest(_message.Message):
    __slots__ = ("dataset", "prompt", "max_frames", "fps", "onboard_model", "rebuild")
    DATASET_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAMES_FIELD_NUMBER: _ClassVar[int]
    FPS_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    REBUILD_FIELD_NUMBER: _ClassVar[int]
    dataset: str
    prompt: str
    max_frames: int
    fps: float
    onboard_model: str
    rebuild: bool
    def __init__(self, dataset: _Optional[str] = ..., prompt: _Optional[str] = ..., max_frames: _Optional[int] = ..., fps: _Optional[float] = ..., onboard_model: _Optional[str] = ..., rebuild: bool = ...) -> None: ...

class RunInfo(_message.Message):
    __slots__ = ("run_id", "dataset", "prompt", "frames", "objects", "status", "onboard_model", "cached")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATUS_UNSPECIFIED: _ClassVar[RunInfo.Status]
        RUNNING: _ClassVar[RunInfo.Status]
        FINISHED: _ClassVar[RunInfo.Status]
        CANCELLED: _ClassVar[RunInfo.Status]
        FAILED: _ClassVar[RunInfo.Status]
    STATUS_UNSPECIFIED: RunInfo.Status
    RUNNING: RunInfo.Status
    FINISHED: RunInfo.Status
    CANCELLED: RunInfo.Status
    FAILED: RunInfo.Status
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    DATASET_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    OBJECTS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    dataset: str
    prompt: str
    frames: int
    objects: int
    status: RunInfo.Status
    onboard_model: str
    cached: bool
    def __init__(self, run_id: _Optional[str] = ..., dataset: _Optional[str] = ..., prompt: _Optional[str] = ..., frames: _Optional[int] = ..., objects: _Optional[int] = ..., status: _Optional[_Union[RunInfo.Status, str]] = ..., onboard_model: _Optional[str] = ..., cached: bool = ...) -> None: ...

class RunDemoResponse(_message.Message):
    __slots__ = ("run_id", "frames", "objects", "status", "onboard_model", "onboard_recognises_prompt", "cached")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    OBJECTS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_RECOGNISES_PROMPT_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    frames: int
    objects: int
    status: RunInfo.Status
    onboard_model: str
    onboard_recognises_prompt: bool
    cached: bool
    def __init__(self, run_id: _Optional[str] = ..., frames: _Optional[int] = ..., objects: _Optional[int] = ..., status: _Optional[_Union[RunInfo.Status, str]] = ..., onboard_model: _Optional[str] = ..., onboard_recognises_prompt: bool = ..., cached: bool = ...) -> None: ...

class GetRunRequest(_message.Message):
    __slots__ = ("run_id",)
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    def __init__(self, run_id: _Optional[str] = ...) -> None: ...

class GetRunResponse(_message.Message):
    __slots__ = ("run",)
    RUN_FIELD_NUMBER: _ClassVar[int]
    run: RunInfo
    def __init__(self, run: _Optional[_Union[RunInfo, _Mapping[str, _Any]]] = ...) -> None: ...

class PromptSamRequest(_message.Message):
    __slots__ = ("run_id", "concept", "frame_ids", "max_frames")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    CONCEPT_FIELD_NUMBER: _ClassVar[int]
    FRAME_IDS_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAMES_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    concept: str
    frame_ids: _containers.RepeatedScalarFieldContainer[int]
    max_frames: int
    def __init__(self, run_id: _Optional[str] = ..., concept: _Optional[str] = ..., frame_ids: _Optional[_Iterable[int]] = ..., max_frames: _Optional[int] = ...) -> None: ...

class SamDetection(_message.Message):
    __slots__ = ("detection_id", "label", "score", "box_xyxy", "mask_polygon")
    DETECTION_ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    BOX_XYXY_FIELD_NUMBER: _ClassVar[int]
    MASK_POLYGON_FIELD_NUMBER: _ClassVar[int]
    detection_id: str
    label: str
    score: float
    box_xyxy: PixelBox
    mask_polygon: _containers.RepeatedCompositeFieldContainer[PixelPoint]
    def __init__(self, detection_id: _Optional[str] = ..., label: _Optional[str] = ..., score: _Optional[float] = ..., box_xyxy: _Optional[_Union[PixelBox, _Mapping[str, _Any]]] = ..., mask_polygon: _Optional[_Iterable[_Union[PixelPoint, _Mapping[str, _Any]]]] = ...) -> None: ...

class SamFrameDetections(_message.Message):
    __slots__ = ("frame_id", "t_ns", "detections")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    detections: _containers.RepeatedCompositeFieldContainer[SamDetection]
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., detections: _Optional[_Iterable[_Union[SamDetection, _Mapping[str, _Any]]]] = ...) -> None: ...

class PromptSamResponse(_message.Message):
    __slots__ = ("frames",)
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    frames: _containers.RepeatedCompositeFieldContainer[SamFrameDetections]
    def __init__(self, frames: _Optional[_Iterable[_Union[SamFrameDetections, _Mapping[str, _Any]]]] = ...) -> None: ...

class FindObjectsRequest(_message.Message):
    __slots__ = ("run_id", "label", "near", "radius_m", "moving", "limit")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    NEAR_FIELD_NUMBER: _ClassVar[int]
    RADIUS_M_FIELD_NUMBER: _ClassVar[int]
    MOVING_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    label: str
    near: Vec3
    radius_m: float
    moving: bool
    limit: int
    def __init__(self, run_id: _Optional[str] = ..., label: _Optional[str] = ..., near: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., radius_m: _Optional[float] = ..., moving: bool = ..., limit: _Optional[int] = ...) -> None: ...

class OrientedBox(_message.Message):
    __slots__ = ("centre", "extents", "rotation")
    CENTRE_FIELD_NUMBER: _ClassVar[int]
    EXTENTS_FIELD_NUMBER: _ClassVar[int]
    ROTATION_FIELD_NUMBER: _ClassVar[int]
    centre: Vec3
    extents: Vec3
    rotation: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, centre: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., extents: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., rotation: _Optional[_Iterable[float]] = ...) -> None: ...

class Neighbour(_message.Message):
    __slots__ = ("id", "distance_m", "relation")
    ID_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_M_FIELD_NUMBER: _ClassVar[int]
    RELATION_FIELD_NUMBER: _ClassVar[int]
    id: str
    distance_m: float
    relation: Relation
    def __init__(self, id: _Optional[str] = ..., distance_m: _Optional[float] = ..., relation: _Optional[_Union[Relation, str]] = ...) -> None: ...

class ObjectSummary(_message.Message):
    __slots__ = ("id", "label", "confidence", "frame", "up_axis", "units", "n_points", "n_faces", "centroid", "aabb_min", "aabb_max", "obb", "height_m", "footprint_m2", "shape", "observed_frames", "t_first_ns", "t_last_ns", "neighbours", "geometry_uri", "moving")
    ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    FRAME_FIELD_NUMBER: _ClassVar[int]
    UP_AXIS_FIELD_NUMBER: _ClassVar[int]
    UNITS_FIELD_NUMBER: _ClassVar[int]
    N_POINTS_FIELD_NUMBER: _ClassVar[int]
    N_FACES_FIELD_NUMBER: _ClassVar[int]
    CENTROID_FIELD_NUMBER: _ClassVar[int]
    AABB_MIN_FIELD_NUMBER: _ClassVar[int]
    AABB_MAX_FIELD_NUMBER: _ClassVar[int]
    OBB_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_M_FIELD_NUMBER: _ClassVar[int]
    FOOTPRINT_M2_FIELD_NUMBER: _ClassVar[int]
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_FRAMES_FIELD_NUMBER: _ClassVar[int]
    T_FIRST_NS_FIELD_NUMBER: _ClassVar[int]
    T_LAST_NS_FIELD_NUMBER: _ClassVar[int]
    NEIGHBOURS_FIELD_NUMBER: _ClassVar[int]
    GEOMETRY_URI_FIELD_NUMBER: _ClassVar[int]
    MOVING_FIELD_NUMBER: _ClassVar[int]
    id: str
    label: str
    confidence: float
    frame: str
    up_axis: str
    units: str
    n_points: int
    n_faces: int
    centroid: Vec3
    aabb_min: Vec3
    aabb_max: Vec3
    obb: OrientedBox
    height_m: float
    footprint_m2: float
    shape: Shape
    observed_frames: int
    t_first_ns: int
    t_last_ns: int
    neighbours: _containers.RepeatedCompositeFieldContainer[Neighbour]
    geometry_uri: str
    moving: bool
    def __init__(self, id: _Optional[str] = ..., label: _Optional[str] = ..., confidence: _Optional[float] = ..., frame: _Optional[str] = ..., up_axis: _Optional[str] = ..., units: _Optional[str] = ..., n_points: _Optional[int] = ..., n_faces: _Optional[int] = ..., centroid: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., aabb_min: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., aabb_max: _Optional[_Union[Vec3, _Mapping[str, _Any]]] = ..., obb: _Optional[_Union[OrientedBox, _Mapping[str, _Any]]] = ..., height_m: _Optional[float] = ..., footprint_m2: _Optional[float] = ..., shape: _Optional[_Union[Shape, str]] = ..., observed_frames: _Optional[int] = ..., t_first_ns: _Optional[int] = ..., t_last_ns: _Optional[int] = ..., neighbours: _Optional[_Iterable[_Union[Neighbour, _Mapping[str, _Any]]]] = ..., geometry_uri: _Optional[str] = ..., moving: bool = ...) -> None: ...

class FindObjectsResponse(_message.Message):
    __slots__ = ("objects",)
    OBJECTS_FIELD_NUMBER: _ClassVar[int]
    objects: _containers.RepeatedCompositeFieldContainer[ObjectSummary]
    def __init__(self, objects: _Optional[_Iterable[_Union[ObjectSummary, _Mapping[str, _Any]]]] = ...) -> None: ...

class GetObjectRequest(_message.Message):
    __slots__ = ("run_id", "object_id")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    object_id: str
    def __init__(self, run_id: _Optional[str] = ..., object_id: _Optional[str] = ...) -> None: ...

class GetObjectResponse(_message.Message):
    __slots__ = ("object",)
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    object: ObjectSummary
    def __init__(self, object: _Optional[_Union[ObjectSummary, _Mapping[str, _Any]]] = ...) -> None: ...

class GetObjectGeometryRequest(_message.Message):
    __slots__ = ("run_id", "object_id", "max_points", "voxel_m")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_POINTS_FIELD_NUMBER: _ClassVar[int]
    VOXEL_M_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    object_id: str
    max_points: int
    voxel_m: float
    def __init__(self, run_id: _Optional[str] = ..., object_id: _Optional[str] = ..., max_points: _Optional[int] = ..., voxel_m: _Optional[float] = ...) -> None: ...

class GetObjectGeometryResponse(_message.Message):
    __slots__ = ("obj_text", "geometry_uri", "decimated_from")
    OBJ_TEXT_FIELD_NUMBER: _ClassVar[int]
    GEOMETRY_URI_FIELD_NUMBER: _ClassVar[int]
    DECIMATED_FROM_FIELD_NUMBER: _ClassVar[int]
    obj_text: str
    geometry_uri: str
    decimated_from: int
    def __init__(self, obj_text: _Optional[str] = ..., geometry_uri: _Optional[str] = ..., decimated_from: _Optional[int] = ...) -> None: ...

class GetFrameRequest(_message.Message):
    __slots__ = ("run_id", "frame_index", "frame_id", "t_ns", "crop_box", "crop_object_id", "pad_px", "max_side")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_INDEX_FIELD_NUMBER: _ClassVar[int]
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    CROP_BOX_FIELD_NUMBER: _ClassVar[int]
    CROP_OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    PAD_PX_FIELD_NUMBER: _ClassVar[int]
    MAX_SIDE_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    frame_index: int
    frame_id: int
    t_ns: int
    crop_box: PixelBox
    crop_object_id: str
    pad_px: int
    max_side: int
    def __init__(self, run_id: _Optional[str] = ..., frame_index: _Optional[int] = ..., frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., crop_box: _Optional[_Union[PixelBox, _Mapping[str, _Any]]] = ..., crop_object_id: _Optional[str] = ..., pad_px: _Optional[int] = ..., max_side: _Optional[int] = ...) -> None: ...

class DatasetGeoPoint(_message.Message):
    __slots__ = ("lon", "lat", "alt_m")
    LON_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    ALT_M_FIELD_NUMBER: _ClassVar[int]
    lon: float
    lat: float
    alt_m: float
    def __init__(self, lon: _Optional[float] = ..., lat: _Optional[float] = ..., alt_m: _Optional[float] = ...) -> None: ...

class DatasetLicense(_message.Message):
    __slots__ = ("name", "url", "attribution")
    NAME_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTION_FIELD_NUMBER: _ClassVar[int]
    name: str
    url: str
    attribution: str
    def __init__(self, name: _Optional[str] = ..., url: _Optional[str] = ..., attribution: _Optional[str] = ...) -> None: ...

class DatasetEntry(_message.Message):
    __slots__ = ("id", "title", "description", "provider", "license", "modality", "official_url", "default_prompt", "prepared", "frame_count", "thumbnail_available", "location_label", "gps_centre", "gps_track", "credit", "runs")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    LICENSE_FIELD_NUMBER: _ClassVar[int]
    MODALITY_FIELD_NUMBER: _ClassVar[int]
    OFFICIAL_URL_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_PROMPT_FIELD_NUMBER: _ClassVar[int]
    PREPARED_FIELD_NUMBER: _ClassVar[int]
    FRAME_COUNT_FIELD_NUMBER: _ClassVar[int]
    THUMBNAIL_AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    LOCATION_LABEL_FIELD_NUMBER: _ClassVar[int]
    GPS_CENTRE_FIELD_NUMBER: _ClassVar[int]
    GPS_TRACK_FIELD_NUMBER: _ClassVar[int]
    CREDIT_FIELD_NUMBER: _ClassVar[int]
    RUNS_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    description: str
    provider: str
    license: DatasetLicense
    modality: DatasetModality
    official_url: str
    default_prompt: str
    prepared: bool
    frame_count: int
    thumbnail_available: bool
    location_label: str
    gps_centre: DatasetGeoPoint
    gps_track: _containers.RepeatedCompositeFieldContainer[DatasetGeoPoint]
    credit: str
    runs: _containers.RepeatedCompositeFieldContainer[CachedRun]
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., provider: _Optional[str] = ..., license: _Optional[_Union[DatasetLicense, _Mapping[str, _Any]]] = ..., modality: _Optional[_Union[DatasetModality, str]] = ..., official_url: _Optional[str] = ..., default_prompt: _Optional[str] = ..., prepared: bool = ..., frame_count: _Optional[int] = ..., thumbnail_available: bool = ..., location_label: _Optional[str] = ..., gps_centre: _Optional[_Union[DatasetGeoPoint, _Mapping[str, _Any]]] = ..., gps_track: _Optional[_Iterable[_Union[DatasetGeoPoint, _Mapping[str, _Any]]]] = ..., credit: _Optional[str] = ..., runs: _Optional[_Iterable[_Union[CachedRun, _Mapping[str, _Any]]]] = ...) -> None: ...

class CachedRun(_message.Message):
    __slots__ = ("cache_key", "run_id", "title", "frames", "created_at", "preview_frame_id")
    CACHE_KEY_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    cache_key: str
    run_id: str
    title: str
    frames: int
    created_at: float
    preview_frame_id: int
    def __init__(self, cache_key: _Optional[str] = ..., run_id: _Optional[str] = ..., title: _Optional[str] = ..., frames: _Optional[int] = ..., created_at: _Optional[float] = ..., preview_frame_id: _Optional[int] = ...) -> None: ...

class ListDatasetsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListDatasetsResponse(_message.Message):
    __slots__ = ("datasets",)
    DATASETS_FIELD_NUMBER: _ClassVar[int]
    datasets: _containers.RepeatedCompositeFieldContainer[DatasetEntry]
    def __init__(self, datasets: _Optional[_Iterable[_Union[DatasetEntry, _Mapping[str, _Any]]]] = ...) -> None: ...

class GetDatasetRequest(_message.Message):
    __slots__ = ("dataset_id",)
    DATASET_ID_FIELD_NUMBER: _ClassVar[int]
    dataset_id: str
    def __init__(self, dataset_id: _Optional[str] = ...) -> None: ...

class PrepareDatasetRequest(_message.Message):
    __slots__ = ("dataset_id",)
    DATASET_ID_FIELD_NUMBER: _ClassVar[int]
    dataset_id: str
    def __init__(self, dataset_id: _Optional[str] = ...) -> None: ...

class DatasetResponse(_message.Message):
    __slots__ = ("dataset",)
    DATASET_FIELD_NUMBER: _ClassVar[int]
    dataset: DatasetEntry
    def __init__(self, dataset: _Optional[_Union[DatasetEntry, _Mapping[str, _Any]]] = ...) -> None: ...

class RunRtabmapRequest(_message.Message):
    __slots__ = ("dataset", "max_frames", "fps", "onboard_model", "rebuild")
    DATASET_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAMES_FIELD_NUMBER: _ClassVar[int]
    FPS_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    REBUILD_FIELD_NUMBER: _ClassVar[int]
    dataset: str
    max_frames: int
    fps: float
    onboard_model: str
    rebuild: bool
    def __init__(self, dataset: _Optional[str] = ..., max_frames: _Optional[int] = ..., fps: _Optional[float] = ..., onboard_model: _Optional[str] = ..., rebuild: bool = ...) -> None: ...

class RunRtabmapResponse(_message.Message):
    __slots__ = ("run",)
    RUN_FIELD_NUMBER: _ClassVar[int]
    run: RunInfo
    def __init__(self, run: _Optional[_Union[RunInfo, _Mapping[str, _Any]]] = ...) -> None: ...

class RunSamOnDatasetRequest(_message.Message):
    __slots__ = ("dataset", "concept", "max_frames")
    DATASET_FIELD_NUMBER: _ClassVar[int]
    CONCEPT_FIELD_NUMBER: _ClassVar[int]
    MAX_FRAMES_FIELD_NUMBER: _ClassVar[int]
    dataset: str
    concept: str
    max_frames: int
    def __init__(self, dataset: _Optional[str] = ..., concept: _Optional[str] = ..., max_frames: _Optional[int] = ...) -> None: ...

class RunSamOnDatasetResponse(_message.Message):
    __slots__ = ("dataset_id", "frames")
    DATASET_ID_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    dataset_id: str
    frames: _containers.RepeatedCompositeFieldContainer[SamFrameDetections]
    def __init__(self, dataset_id: _Optional[str] = ..., frames: _Optional[_Iterable[_Union[SamFrameDetections, _Mapping[str, _Any]]]] = ...) -> None: ...

class GetFrameResponse(_message.Message):
    __slots__ = ("frame_id", "t_ns", "width", "height", "source", "image", "media_type")
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    T_NS_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    MEDIA_TYPE_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    t_ns: int
    width: int
    height: int
    source: FrameSource
    image: bytes
    media_type: str
    def __init__(self, frame_id: _Optional[int] = ..., t_ns: _Optional[int] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., source: _Optional[_Union[FrameSource, str]] = ..., image: _Optional[bytes] = ..., media_type: _Optional[str] = ...) -> None: ...

class ListRunsRequest(_message.Message):
    __slots__ = ("dataset",)
    DATASET_FIELD_NUMBER: _ClassVar[int]
    dataset: str
    def __init__(self, dataset: _Optional[str] = ...) -> None: ...

class ListRunsResponse(_message.Message):
    __slots__ = ("runs",)
    RUNS_FIELD_NUMBER: _ClassVar[int]
    runs: _containers.RepeatedCompositeFieldContainer[CachedRun]
    def __init__(self, runs: _Optional[_Iterable[_Union[CachedRun, _Mapping[str, _Any]]]] = ...) -> None: ...

class RunCachedRequest(_message.Message):
    __slots__ = ("run_id",)
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    def __init__(self, run_id: _Optional[str] = ...) -> None: ...

class RunCachedResponse(_message.Message):
    __slots__ = ("run",)
    RUN_FIELD_NUMBER: _ClassVar[int]
    run: RunInfo
    def __init__(self, run: _Optional[_Union[RunInfo, _Mapping[str, _Any]]] = ...) -> None: ...
