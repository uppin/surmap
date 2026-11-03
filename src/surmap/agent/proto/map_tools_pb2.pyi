from surmap.agent.proto import execution_pb2 as _execution_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MapLayerKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MAP_LAYER_KIND_UNSPECIFIED: _ClassVar[MapLayerKind]
    RASTER: _ClassVar[MapLayerKind]
    VECTOR: _ClassVar[MapLayerKind]
MAP_LAYER_KIND_UNSPECIFIED: MapLayerKind
RASTER: MapLayerKind
VECTOR: MapLayerKind

class GeoPoint(_message.Message):
    __slots__ = ("lon", "lat", "alt_m")
    LON_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    ALT_M_FIELD_NUMBER: _ClassVar[int]
    lon: float
    lat: float
    alt_m: float
    def __init__(self, lon: _Optional[float] = ..., lat: _Optional[float] = ..., alt_m: _Optional[float] = ...) -> None: ...

class MapCamera(_message.Message):
    __slots__ = ("centre", "zoom", "pitch_deg", "bearing_deg")
    CENTRE_FIELD_NUMBER: _ClassVar[int]
    ZOOM_FIELD_NUMBER: _ClassVar[int]
    PITCH_DEG_FIELD_NUMBER: _ClassVar[int]
    BEARING_DEG_FIELD_NUMBER: _ClassVar[int]
    centre: GeoPoint
    zoom: float
    pitch_deg: float
    bearing_deg: float
    def __init__(self, centre: _Optional[_Union[GeoPoint, _Mapping[str, _Any]]] = ..., zoom: _Optional[float] = ..., pitch_deg: _Optional[float] = ..., bearing_deg: _Optional[float] = ...) -> None: ...

class MapObject(_message.Message):
    __slots__ = ("id", "label", "geometry_uri", "position", "rotation_deg", "scale")
    ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    GEOMETRY_URI_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    ROTATION_DEG_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    id: str
    label: str
    geometry_uri: str
    position: GeoPoint
    rotation_deg: float
    scale: float
    def __init__(self, id: _Optional[str] = ..., label: _Optional[str] = ..., geometry_uri: _Optional[str] = ..., position: _Optional[_Union[GeoPoint, _Mapping[str, _Any]]] = ..., rotation_deg: _Optional[float] = ..., scale: _Optional[float] = ...) -> None: ...

class MapRoute(_message.Message):
    __slots__ = ("id", "name", "waypoints", "color")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    waypoints: _containers.RepeatedCompositeFieldContainer[GeoPoint]
    color: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., waypoints: _Optional[_Iterable[_Union[GeoPoint, _Mapping[str, _Any]]]] = ..., color: _Optional[str] = ...) -> None: ...

class MapLayer(_message.Message):
    __slots__ = ("id", "name", "kind", "source_url", "source_layer", "loaded", "attribution", "is_default")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SOURCE_URL_FIELD_NUMBER: _ClassVar[int]
    SOURCE_LAYER_FIELD_NUMBER: _ClassVar[int]
    LOADED_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTION_FIELD_NUMBER: _ClassVar[int]
    IS_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    kind: MapLayerKind
    source_url: str
    source_layer: str
    loaded: bool
    attribution: str
    is_default: bool
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., kind: _Optional[_Union[MapLayerKind, str]] = ..., source_url: _Optional[str] = ..., source_layer: _Optional[str] = ..., loaded: bool = ..., attribution: _Optional[str] = ..., is_default: bool = ...) -> None: ...

class MapScene(_message.Message):
    __slots__ = ("scene_id", "objects", "camera", "routes", "revision", "layers")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECTS_FIELD_NUMBER: _ClassVar[int]
    CAMERA_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    LAYERS_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    objects: _containers.RepeatedCompositeFieldContainer[MapObject]
    camera: MapCamera
    routes: _containers.RepeatedCompositeFieldContainer[MapRoute]
    revision: int
    layers: _containers.RepeatedCompositeFieldContainer[MapLayer]
    def __init__(self, scene_id: _Optional[str] = ..., objects: _Optional[_Iterable[_Union[MapObject, _Mapping[str, _Any]]]] = ..., camera: _Optional[_Union[MapCamera, _Mapping[str, _Any]]] = ..., routes: _Optional[_Iterable[_Union[MapRoute, _Mapping[str, _Any]]]] = ..., revision: _Optional[int] = ..., layers: _Optional[_Iterable[_Union[MapLayer, _Mapping[str, _Any]]]] = ...) -> None: ...

class AddMapObjectRequest(_message.Message):
    __slots__ = ("scene_id", "object_id", "label", "geometry_uri", "position", "rotation_deg", "scale")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    GEOMETRY_URI_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    ROTATION_DEG_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    object_id: str
    label: str
    geometry_uri: str
    position: GeoPoint
    rotation_deg: float
    scale: float
    def __init__(self, scene_id: _Optional[str] = ..., object_id: _Optional[str] = ..., label: _Optional[str] = ..., geometry_uri: _Optional[str] = ..., position: _Optional[_Union[GeoPoint, _Mapping[str, _Any]]] = ..., rotation_deg: _Optional[float] = ..., scale: _Optional[float] = ...) -> None: ...

class MapObjectResponse(_message.Message):
    __slots__ = ("object", "revision")
    OBJECT_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    object: MapObject
    revision: int
    def __init__(self, object: _Optional[_Union[MapObject, _Mapping[str, _Any]]] = ..., revision: _Optional[int] = ...) -> None: ...

class MoveMapObjectRequest(_message.Message):
    __slots__ = ("scene_id", "object_id", "position", "rotation_deg", "scale")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    ROTATION_DEG_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    object_id: str
    position: GeoPoint
    rotation_deg: float
    scale: float
    def __init__(self, scene_id: _Optional[str] = ..., object_id: _Optional[str] = ..., position: _Optional[_Union[GeoPoint, _Mapping[str, _Any]]] = ..., rotation_deg: _Optional[float] = ..., scale: _Optional[float] = ...) -> None: ...

class RemoveMapObjectRequest(_message.Message):
    __slots__ = ("scene_id", "object_id")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    object_id: str
    def __init__(self, scene_id: _Optional[str] = ..., object_id: _Optional[str] = ...) -> None: ...

class RemoveMapObjectResponse(_message.Message):
    __slots__ = ("object_id", "revision")
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    object_id: str
    revision: int
    def __init__(self, object_id: _Optional[str] = ..., revision: _Optional[int] = ...) -> None: ...

class ListMapObjectsRequest(_message.Message):
    __slots__ = ("scene_id",)
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    def __init__(self, scene_id: _Optional[str] = ...) -> None: ...

class ListMapObjectsResponse(_message.Message):
    __slots__ = ("objects", "revision")
    OBJECTS_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    objects: _containers.RepeatedCompositeFieldContainer[MapObject]
    revision: int
    def __init__(self, objects: _Optional[_Iterable[_Union[MapObject, _Mapping[str, _Any]]]] = ..., revision: _Optional[int] = ...) -> None: ...

class GetMapSceneRequest(_message.Message):
    __slots__ = ("scene_id",)
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    def __init__(self, scene_id: _Optional[str] = ...) -> None: ...

class GetMapSceneResponse(_message.Message):
    __slots__ = ("scene",)
    SCENE_FIELD_NUMBER: _ClassVar[int]
    scene: MapScene
    def __init__(self, scene: _Optional[_Union[MapScene, _Mapping[str, _Any]]] = ...) -> None: ...

class NavigateMapRequest(_message.Message):
    __slots__ = ("scene_id", "centre", "zoom", "pitch_deg", "bearing_deg")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    CENTRE_FIELD_NUMBER: _ClassVar[int]
    ZOOM_FIELD_NUMBER: _ClassVar[int]
    PITCH_DEG_FIELD_NUMBER: _ClassVar[int]
    BEARING_DEG_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    centre: GeoPoint
    zoom: float
    pitch_deg: float
    bearing_deg: float
    def __init__(self, scene_id: _Optional[str] = ..., centre: _Optional[_Union[GeoPoint, _Mapping[str, _Any]]] = ..., zoom: _Optional[float] = ..., pitch_deg: _Optional[float] = ..., bearing_deg: _Optional[float] = ...) -> None: ...

class NavigateMapResponse(_message.Message):
    __slots__ = ("camera", "revision")
    CAMERA_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    camera: MapCamera
    revision: int
    def __init__(self, camera: _Optional[_Union[MapCamera, _Mapping[str, _Any]]] = ..., revision: _Optional[int] = ...) -> None: ...

class ShowRouteRequest(_message.Message):
    __slots__ = ("scene_id", "route_id", "name", "waypoints", "color")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    route_id: str
    name: str
    waypoints: _containers.RepeatedCompositeFieldContainer[GeoPoint]
    color: str
    def __init__(self, scene_id: _Optional[str] = ..., route_id: _Optional[str] = ..., name: _Optional[str] = ..., waypoints: _Optional[_Iterable[_Union[GeoPoint, _Mapping[str, _Any]]]] = ..., color: _Optional[str] = ...) -> None: ...

class MapRouteResponse(_message.Message):
    __slots__ = ("route", "revision")
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    route: MapRoute
    revision: int
    def __init__(self, route: _Optional[_Union[MapRoute, _Mapping[str, _Any]]] = ..., revision: _Optional[int] = ...) -> None: ...

class UpdateRouteRequest(_message.Message):
    __slots__ = ("scene_id", "route_id", "name", "waypoints", "color")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    route_id: str
    name: str
    waypoints: _containers.RepeatedCompositeFieldContainer[GeoPoint]
    color: str
    def __init__(self, scene_id: _Optional[str] = ..., route_id: _Optional[str] = ..., name: _Optional[str] = ..., waypoints: _Optional[_Iterable[_Union[GeoPoint, _Mapping[str, _Any]]]] = ..., color: _Optional[str] = ...) -> None: ...

class ListMapLayersRequest(_message.Message):
    __slots__ = ("scene_id",)
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    def __init__(self, scene_id: _Optional[str] = ...) -> None: ...

class ListMapLayersResponse(_message.Message):
    __slots__ = ("layers", "revision")
    LAYERS_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    layers: _containers.RepeatedCompositeFieldContainer[MapLayer]
    revision: int
    def __init__(self, layers: _Optional[_Iterable[_Union[MapLayer, _Mapping[str, _Any]]]] = ..., revision: _Optional[int] = ...) -> None: ...

class LoadMapLayerRequest(_message.Message):
    __slots__ = ("scene_id", "layer_id")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    LAYER_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    layer_id: str
    def __init__(self, scene_id: _Optional[str] = ..., layer_id: _Optional[str] = ...) -> None: ...

class UnloadMapLayerRequest(_message.Message):
    __slots__ = ("scene_id", "layer_id")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    LAYER_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    layer_id: str
    def __init__(self, scene_id: _Optional[str] = ..., layer_id: _Optional[str] = ...) -> None: ...

class MapLayerResponse(_message.Message):
    __slots__ = ("layer", "revision")
    LAYER_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    layer: MapLayer
    revision: int
    def __init__(self, layer: _Optional[_Union[MapLayer, _Mapping[str, _Any]]] = ..., revision: _Optional[int] = ...) -> None: ...

class ClearRouteRequest(_message.Message):
    __slots__ = ("scene_id", "route_id")
    SCENE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTE_ID_FIELD_NUMBER: _ClassVar[int]
    scene_id: str
    route_id: str
    def __init__(self, scene_id: _Optional[str] = ..., route_id: _Optional[str] = ...) -> None: ...

class ClearRouteResponse(_message.Message):
    __slots__ = ("route_id", "revision")
    ROUTE_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    route_id: str
    revision: int
    def __init__(self, route_id: _Optional[str] = ..., revision: _Optional[int] = ...) -> None: ...
