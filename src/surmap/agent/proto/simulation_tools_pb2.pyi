from surmap.agent.proto import execution_pb2 as _execution_pb2
from surmap.agent.proto import simulation_contents_pb2 as _simulation_contents_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AssetKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ASSET_KIND_UNSPECIFIED: _ClassVar[AssetKind]
    ASSET_KIND_MODEL: _ClassVar[AssetKind]
    ASSET_KIND_TEXTURE: _ClassVar[AssetKind]
    ASSET_KIND_HDRI: _ClassVar[AssetKind]

class Collider(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COLLIDER_UNSPECIFIED: _ClassVar[Collider]
    COLLIDER_NONE: _ClassVar[Collider]
    COLLIDER_BOX: _ClassVar[Collider]
    COLLIDER_TRIMESH: _ClassVar[Collider]
ASSET_KIND_UNSPECIFIED: AssetKind
ASSET_KIND_MODEL: AssetKind
ASSET_KIND_TEXTURE: AssetKind
ASSET_KIND_HDRI: AssetKind
COLLIDER_UNSPECIFIED: Collider
COLLIDER_NONE: Collider
COLLIDER_BOX: Collider
COLLIDER_TRIMESH: Collider

class EnuPoint(_message.Message):
    __slots__ = ("east", "north", "up")
    EAST_FIELD_NUMBER: _ClassVar[int]
    NORTH_FIELD_NUMBER: _ClassVar[int]
    UP_FIELD_NUMBER: _ClassVar[int]
    east: float
    north: float
    up: float
    def __init__(self, east: _Optional[float] = ..., north: _Optional[float] = ..., up: _Optional[float] = ...) -> None: ...

class SearchAssetsRequest(_message.Message):
    __slots__ = ("query", "kind", "sources", "limit")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    query: str
    kind: AssetKind
    sources: _containers.RepeatedScalarFieldContainer[str]
    limit: int
    def __init__(self, query: _Optional[str] = ..., kind: _Optional[_Union[AssetKind, str]] = ..., sources: _Optional[_Iterable[str]] = ..., limit: _Optional[int] = ...) -> None: ...

class AssetHitInfo(_message.Message):
    __slots__ = ("ref", "source", "kind", "title", "author", "licence", "accepted", "licence_reason", "page_url", "preview_url")
    REF_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    LICENCE_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    LICENCE_REASON_FIELD_NUMBER: _ClassVar[int]
    PAGE_URL_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_URL_FIELD_NUMBER: _ClassVar[int]
    ref: str
    source: str
    kind: AssetKind
    title: str
    author: str
    licence: str
    accepted: bool
    licence_reason: str
    page_url: str
    preview_url: str
    def __init__(self, ref: _Optional[str] = ..., source: _Optional[str] = ..., kind: _Optional[_Union[AssetKind, str]] = ..., title: _Optional[str] = ..., author: _Optional[str] = ..., licence: _Optional[str] = ..., accepted: bool = ..., licence_reason: _Optional[str] = ..., page_url: _Optional[str] = ..., preview_url: _Optional[str] = ...) -> None: ...

class SearchAssetsResponse(_message.Message):
    __slots__ = ("hits",)
    HITS_FIELD_NUMBER: _ClassVar[int]
    hits: _containers.RepeatedCompositeFieldContainer[AssetHitInfo]
    def __init__(self, hits: _Optional[_Iterable[_Union[AssetHitInfo, _Mapping[str, _Any]]]] = ...) -> None: ...

class DownloadAssetRequest(_message.Message):
    __slots__ = ("ref",)
    REF_FIELD_NUMBER: _ClassVar[int]
    ref: str
    def __init__(self, ref: _Optional[str] = ...) -> None: ...

class StoredAssetInfo(_message.Message):
    __slots__ = ("ref", "kind", "title", "author", "licence", "entry_path", "files")
    REF_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    LICENCE_FIELD_NUMBER: _ClassVar[int]
    ENTRY_PATH_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    ref: str
    kind: AssetKind
    title: str
    author: str
    licence: str
    entry_path: str
    files: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ref: _Optional[str] = ..., kind: _Optional[_Union[AssetKind, str]] = ..., title: _Optional[str] = ..., author: _Optional[str] = ..., licence: _Optional[str] = ..., entry_path: _Optional[str] = ..., files: _Optional[_Iterable[str]] = ...) -> None: ...

class AssetResponse(_message.Message):
    __slots__ = ("asset",)
    ASSET_FIELD_NUMBER: _ClassVar[int]
    asset: StoredAssetInfo
    def __init__(self, asset: _Optional[_Union[StoredAssetInfo, _Mapping[str, _Any]]] = ...) -> None: ...

class ListAssetsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListAssetsResponse(_message.Message):
    __slots__ = ("assets",)
    ASSETS_FIELD_NUMBER: _ClassVar[int]
    assets: _containers.RepeatedCompositeFieldContainer[StoredAssetInfo]
    def __init__(self, assets: _Optional[_Iterable[_Union[StoredAssetInfo, _Mapping[str, _Any]]]] = ...) -> None: ...

class CreateScenarioRequest(_message.Message):
    __slots__ = ("name", "preset")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PRESET_FIELD_NUMBER: _ClassVar[int]
    name: str
    preset: str
    def __init__(self, name: _Optional[str] = ..., preset: _Optional[str] = ...) -> None: ...

class AddModelRequest(_message.Message):
    __slots__ = ("scenario_id", "asset_ref", "position", "yaw_deg", "scale", "collider", "ground_truth_kind", "element_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ASSET_REF_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    SCALE_FIELD_NUMBER: _ClassVar[int]
    COLLIDER_FIELD_NUMBER: _ClassVar[int]
    GROUND_TRUTH_KIND_FIELD_NUMBER: _ClassVar[int]
    ELEMENT_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    asset_ref: str
    position: EnuPoint
    yaw_deg: float
    scale: float
    collider: Collider
    ground_truth_kind: str
    element_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., asset_ref: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., scale: _Optional[float] = ..., collider: _Optional[_Union[Collider, str]] = ..., ground_truth_kind: _Optional[str] = ..., element_id: _Optional[str] = ...) -> None: ...

class BoxElement(_message.Message):
    __slots__ = ("id", "material", "size", "position", "yaw_deg", "collider", "ground_truth_kind", "water")
    ID_FIELD_NUMBER: _ClassVar[int]
    MATERIAL_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    COLLIDER_FIELD_NUMBER: _ClassVar[int]
    GROUND_TRUTH_KIND_FIELD_NUMBER: _ClassVar[int]
    WATER_FIELD_NUMBER: _ClassVar[int]
    id: str
    material: str
    size: EnuPoint
    position: EnuPoint
    yaw_deg: float
    collider: bool
    ground_truth_kind: str
    water: bool
    def __init__(self, id: _Optional[str] = ..., material: _Optional[str] = ..., size: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., collider: bool = ..., ground_truth_kind: _Optional[str] = ..., water: bool = ...) -> None: ...

class BuildingElement(_message.Message):
    __slots__ = ("id", "material", "size", "position", "yaw_deg", "windows")
    ID_FIELD_NUMBER: _ClassVar[int]
    MATERIAL_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    WINDOWS_FIELD_NUMBER: _ClassVar[int]
    id: str
    material: str
    size: EnuPoint
    position: EnuPoint
    yaw_deg: float
    windows: bool
    def __init__(self, id: _Optional[str] = ..., material: _Optional[str] = ..., size: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., windows: bool = ...) -> None: ...

class CollapsedBuildingElement(_message.Message):
    __slots__ = ("id", "material", "footprint_east_m", "footprint_north_m", "position", "yaw_deg", "seed")
    ID_FIELD_NUMBER: _ClassVar[int]
    MATERIAL_FIELD_NUMBER: _ClassVar[int]
    FOOTPRINT_EAST_M_FIELD_NUMBER: _ClassVar[int]
    FOOTPRINT_NORTH_M_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    id: str
    material: str
    footprint_east_m: float
    footprint_north_m: float
    position: EnuPoint
    yaw_deg: float
    seed: int
    def __init__(self, id: _Optional[str] = ..., material: _Optional[str] = ..., footprint_east_m: _Optional[float] = ..., footprint_north_m: _Optional[float] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., seed: _Optional[int] = ...) -> None: ...

class PersonElement(_message.Message):
    __slots__ = ("id", "position", "coat", "skin", "pose", "height_m", "yaw_deg")
    ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    COAT_FIELD_NUMBER: _ClassVar[int]
    SKIN_FIELD_NUMBER: _ClassVar[int]
    POSE_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_M_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    id: str
    position: EnuPoint
    coat: str
    skin: str
    pose: str
    height_m: float
    yaw_deg: float
    def __init__(self, id: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., coat: _Optional[str] = ..., skin: _Optional[str] = ..., pose: _Optional[str] = ..., height_m: _Optional[float] = ..., yaw_deg: _Optional[float] = ...) -> None: ...

class VegetationElement(_message.Message):
    __slots__ = ("id", "species", "position", "size_east_m", "size_north_m", "density_per_100m2", "seed")
    ID_FIELD_NUMBER: _ClassVar[int]
    SPECIES_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    SIZE_EAST_M_FIELD_NUMBER: _ClassVar[int]
    SIZE_NORTH_M_FIELD_NUMBER: _ClassVar[int]
    DENSITY_PER_100M2_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    id: str
    species: str
    position: EnuPoint
    size_east_m: float
    size_north_m: float
    density_per_100m2: float
    seed: int
    def __init__(self, id: _Optional[str] = ..., species: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., size_east_m: _Optional[float] = ..., size_north_m: _Optional[float] = ..., density_per_100m2: _Optional[float] = ..., seed: _Optional[int] = ...) -> None: ...

class VehicleElement(_message.Message):
    __slots__ = ("id", "vehicle_class", "position", "yaw_deg", "cars", "behaviour_json")
    ID_FIELD_NUMBER: _ClassVar[int]
    VEHICLE_CLASS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    CARS_FIELD_NUMBER: _ClassVar[int]
    BEHAVIOUR_JSON_FIELD_NUMBER: _ClassVar[int]
    id: str
    vehicle_class: str
    position: EnuPoint
    yaw_deg: float
    cars: int
    behaviour_json: str
    def __init__(self, id: _Optional[str] = ..., vehicle_class: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., cars: _Optional[int] = ..., behaviour_json: _Optional[str] = ...) -> None: ...

class DroneNestElement(_message.Message):
    __slots__ = ("id", "position", "yaw_deg", "drones")
    ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    DRONES_FIELD_NUMBER: _ClassVar[int]
    id: str
    position: EnuPoint
    yaw_deg: float
    drones: int
    def __init__(self, id: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., drones: _Optional[int] = ...) -> None: ...

class AddElementRequest(_message.Message):
    __slots__ = ("scenario_id", "box", "building", "collapsed_building", "person", "vegetation", "vehicle", "drone_nest")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    BOX_FIELD_NUMBER: _ClassVar[int]
    BUILDING_FIELD_NUMBER: _ClassVar[int]
    COLLAPSED_BUILDING_FIELD_NUMBER: _ClassVar[int]
    PERSON_FIELD_NUMBER: _ClassVar[int]
    VEGETATION_FIELD_NUMBER: _ClassVar[int]
    VEHICLE_FIELD_NUMBER: _ClassVar[int]
    DRONE_NEST_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    box: BoxElement
    building: BuildingElement
    collapsed_building: CollapsedBuildingElement
    person: PersonElement
    vegetation: VegetationElement
    vehicle: VehicleElement
    drone_nest: DroneNestElement
    def __init__(self, scenario_id: _Optional[str] = ..., box: _Optional[_Union[BoxElement, _Mapping[str, _Any]]] = ..., building: _Optional[_Union[BuildingElement, _Mapping[str, _Any]]] = ..., collapsed_building: _Optional[_Union[CollapsedBuildingElement, _Mapping[str, _Any]]] = ..., person: _Optional[_Union[PersonElement, _Mapping[str, _Any]]] = ..., vegetation: _Optional[_Union[VegetationElement, _Mapping[str, _Any]]] = ..., vehicle: _Optional[_Union[VehicleElement, _Mapping[str, _Any]]] = ..., drone_nest: _Optional[_Union[DroneNestElement, _Mapping[str, _Any]]] = ...) -> None: ...

class RemoveElementRequest(_message.Message):
    __slots__ = ("scenario_id", "element_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ELEMENT_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    element_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., element_id: _Optional[str] = ...) -> None: ...

class SetWeatherRequest(_message.Message):
    __slots__ = ("scenario_id", "rain_mm_h", "fog_visibility_m", "wind_from_deg", "wind_speed_m_s", "wind_gust_m_s")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    RAIN_MM_H_FIELD_NUMBER: _ClassVar[int]
    FOG_VISIBILITY_M_FIELD_NUMBER: _ClassVar[int]
    WIND_FROM_DEG_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_M_S_FIELD_NUMBER: _ClassVar[int]
    WIND_GUST_M_S_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    rain_mm_h: float
    fog_visibility_m: float
    wind_from_deg: float
    wind_speed_m_s: float
    wind_gust_m_s: float
    def __init__(self, scenario_id: _Optional[str] = ..., rain_mm_h: _Optional[float] = ..., fog_visibility_m: _Optional[float] = ..., wind_from_deg: _Optional[float] = ..., wind_speed_m_s: _Optional[float] = ..., wind_gust_m_s: _Optional[float] = ...) -> None: ...

class AddFireRequest(_message.Message):
    __slots__ = ("scenario_id", "id", "ignition", "start_s", "spread_m_s", "max_radius_m", "smoke")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    IGNITION_FIELD_NUMBER: _ClassVar[int]
    START_S_FIELD_NUMBER: _ClassVar[int]
    SPREAD_M_S_FIELD_NUMBER: _ClassVar[int]
    MAX_RADIUS_M_FIELD_NUMBER: _ClassVar[int]
    SMOKE_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    id: str
    ignition: EnuPoint
    start_s: float
    spread_m_s: float
    max_radius_m: float
    smoke: bool
    def __init__(self, scenario_id: _Optional[str] = ..., id: _Optional[str] = ..., ignition: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., start_s: _Optional[float] = ..., spread_m_s: _Optional[float] = ..., max_radius_m: _Optional[float] = ..., smoke: bool = ...) -> None: ...

class RemoveFireRequest(_message.Message):
    __slots__ = ("scenario_id", "fire_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    fire_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., fire_id: _Optional[str] = ...) -> None: ...

class SetBehaviourRequest(_message.Message):
    __slots__ = ("scenario_id", "target_id", "tree_json")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    TREE_JSON_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    target_id: str
    tree_json: str
    def __init__(self, scenario_id: _Optional[str] = ..., target_id: _Optional[str] = ..., tree_json: _Optional[str] = ...) -> None: ...

class UpdateBehaviourNodeRequest(_message.Message):
    __slots__ = ("scenario_id", "target_id", "node_id", "node_json")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_JSON_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    target_id: str
    node_id: str
    node_json: str
    def __init__(self, scenario_id: _Optional[str] = ..., target_id: _Optional[str] = ..., node_id: _Optional[str] = ..., node_json: _Optional[str] = ...) -> None: ...

class GetBehaviourRequest(_message.Message):
    __slots__ = ("scenario_id", "target_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    target_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., target_id: _Optional[str] = ...) -> None: ...

class BehaviourResponse(_message.Message):
    __slots__ = ("target_id", "tree_json", "version")
    TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    TREE_JSON_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    target_id: str
    tree_json: str
    version: int
    def __init__(self, target_id: _Optional[str] = ..., tree_json: _Optional[str] = ..., version: _Optional[int] = ...) -> None: ...

class ListBuildingPresetsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BuildingPresetsResponse(_message.Message):
    __slots__ = ("facades", "roofs", "districts")
    FACADES_FIELD_NUMBER: _ClassVar[int]
    ROOFS_FIELD_NUMBER: _ClassVar[int]
    DISTRICTS_FIELD_NUMBER: _ClassVar[int]
    facades: _containers.RepeatedScalarFieldContainer[str]
    roofs: _containers.RepeatedScalarFieldContainer[str]
    districts: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, facades: _Optional[_Iterable[str]] = ..., roofs: _Optional[_Iterable[str]] = ..., districts: _Optional[_Iterable[str]] = ...) -> None: ...

class Rgb(_message.Message):
    __slots__ = ("r", "g", "b")
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    r: float
    g: float
    b: float
    def __init__(self, r: _Optional[float] = ..., g: _Optional[float] = ..., b: _Optional[float] = ...) -> None: ...

class SetDistrictRequest(_message.Message):
    __slots__ = ("scenario_id", "id", "preset", "centre", "size_east_m", "size_north_m", "seed")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    PRESET_FIELD_NUMBER: _ClassVar[int]
    CENTRE_FIELD_NUMBER: _ClassVar[int]
    SIZE_EAST_M_FIELD_NUMBER: _ClassVar[int]
    SIZE_NORTH_M_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    id: str
    preset: str
    centre: EnuPoint
    size_east_m: float
    size_north_m: float
    seed: int
    def __init__(self, scenario_id: _Optional[str] = ..., id: _Optional[str] = ..., preset: _Optional[str] = ..., centre: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., size_east_m: _Optional[float] = ..., size_north_m: _Optional[float] = ..., seed: _Optional[int] = ...) -> None: ...

class RemoveDistrictRequest(_message.Message):
    __slots__ = ("scenario_id", "district_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DISTRICT_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    district_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., district_id: _Optional[str] = ...) -> None: ...

class StyleBuildingRequest(_message.Message):
    __slots__ = ("scenario_id", "building_id", "facade", "roof", "roof_shape", "facade_colour", "roof_colour", "floors", "glazing", "window_ratio")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    BUILDING_ID_FIELD_NUMBER: _ClassVar[int]
    FACADE_FIELD_NUMBER: _ClassVar[int]
    ROOF_FIELD_NUMBER: _ClassVar[int]
    ROOF_SHAPE_FIELD_NUMBER: _ClassVar[int]
    FACADE_COLOUR_FIELD_NUMBER: _ClassVar[int]
    ROOF_COLOUR_FIELD_NUMBER: _ClassVar[int]
    FLOORS_FIELD_NUMBER: _ClassVar[int]
    GLAZING_FIELD_NUMBER: _ClassVar[int]
    WINDOW_RATIO_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    building_id: str
    facade: str
    roof: str
    roof_shape: str
    facade_colour: Rgb
    roof_colour: Rgb
    floors: int
    glazing: str
    window_ratio: float
    def __init__(self, scenario_id: _Optional[str] = ..., building_id: _Optional[str] = ..., facade: _Optional[str] = ..., roof: _Optional[str] = ..., roof_shape: _Optional[str] = ..., facade_colour: _Optional[_Union[Rgb, _Mapping[str, _Any]]] = ..., roof_colour: _Optional[_Union[Rgb, _Mapping[str, _Any]]] = ..., floors: _Optional[int] = ..., glazing: _Optional[str] = ..., window_ratio: _Optional[float] = ...) -> None: ...

class AddBuildingFireRequest(_message.Message):
    __slots__ = ("scenario_id", "id", "building_id", "floor", "start_s")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    BUILDING_ID_FIELD_NUMBER: _ClassVar[int]
    FLOOR_FIELD_NUMBER: _ClassVar[int]
    START_S_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    id: str
    building_id: str
    floor: int
    start_s: float
    def __init__(self, scenario_id: _Optional[str] = ..., id: _Optional[str] = ..., building_id: _Optional[str] = ..., floor: _Optional[int] = ..., start_s: _Optional[float] = ...) -> None: ...

class RemoveBuildingFireRequest(_message.Message):
    __slots__ = ("scenario_id", "fire_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    fire_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., fire_id: _Optional[str] = ...) -> None: ...

class SetMapFloorRequest(_message.Message):
    __slots__ = ("scenario_id", "sw_lat", "sw_lon", "ne_lat", "ne_lon")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    SW_LAT_FIELD_NUMBER: _ClassVar[int]
    SW_LON_FIELD_NUMBER: _ClassVar[int]
    NE_LAT_FIELD_NUMBER: _ClassVar[int]
    NE_LON_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    sw_lat: float
    sw_lon: float
    ne_lat: float
    ne_lon: float
    def __init__(self, scenario_id: _Optional[str] = ..., sw_lat: _Optional[float] = ..., sw_lon: _Optional[float] = ..., ne_lat: _Optional[float] = ..., ne_lon: _Optional[float] = ...) -> None: ...

class MapFloorResponse(_message.Message):
    __slots__ = ("scenario", "centre_lat", "centre_lon", "size_east_m", "size_north_m", "zoom", "texture", "warnings")
    SCENARIO_FIELD_NUMBER: _ClassVar[int]
    CENTRE_LAT_FIELD_NUMBER: _ClassVar[int]
    CENTRE_LON_FIELD_NUMBER: _ClassVar[int]
    SIZE_EAST_M_FIELD_NUMBER: _ClassVar[int]
    SIZE_NORTH_M_FIELD_NUMBER: _ClassVar[int]
    ZOOM_FIELD_NUMBER: _ClassVar[int]
    TEXTURE_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    scenario: ScenarioInfo
    centre_lat: float
    centre_lon: float
    size_east_m: float
    size_north_m: float
    zoom: int
    texture: str
    warnings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, scenario: _Optional[_Union[ScenarioInfo, _Mapping[str, _Any]]] = ..., centre_lat: _Optional[float] = ..., centre_lon: _Optional[float] = ..., size_east_m: _Optional[float] = ..., size_north_m: _Optional[float] = ..., zoom: _Optional[int] = ..., texture: _Optional[str] = ..., warnings: _Optional[_Iterable[str]] = ...) -> None: ...

class ClearMapFloorRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class GeoToEnuRequest(_message.Message):
    __slots__ = ("scenario_id", "lat", "lon")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    lat: float
    lon: float
    def __init__(self, scenario_id: _Optional[str] = ..., lat: _Optional[float] = ..., lon: _Optional[float] = ...) -> None: ...

class GeoToEnuResponse(_message.Message):
    __slots__ = ("position", "inside_floor")
    POSITION_FIELD_NUMBER: _ClassVar[int]
    INSIDE_FLOOR_FIELD_NUMBER: _ClassVar[int]
    position: EnuPoint
    inside_floor: bool
    def __init__(self, position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., inside_floor: bool = ...) -> None: ...

class EnuToGeoRequest(_message.Message):
    __slots__ = ("scenario_id", "position")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    position: EnuPoint
    def __init__(self, scenario_id: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ...) -> None: ...

class EnuToGeoResponse(_message.Message):
    __slots__ = ("lat", "lon")
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    lat: float
    lon: float
    def __init__(self, lat: _Optional[float] = ..., lon: _Optional[float] = ...) -> None: ...

class GetScenarioRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class ScenarioInfo(_message.Message):
    __slots__ = ("id", "name", "version", "manifest_json", "credits", "url", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    MANIFEST_JSON_FIELD_NUMBER: _ClassVar[int]
    CREDITS_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    version: int
    manifest_json: str
    credits: _containers.RepeatedScalarFieldContainer[str]
    url: str
    updated_at: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., version: _Optional[int] = ..., manifest_json: _Optional[str] = ..., credits: _Optional[_Iterable[str]] = ..., url: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class ScenarioResponse(_message.Message):
    __slots__ = ("scenario",)
    SCENARIO_FIELD_NUMBER: _ClassVar[int]
    scenario: ScenarioInfo
    def __init__(self, scenario: _Optional[_Union[ScenarioInfo, _Mapping[str, _Any]]] = ...) -> None: ...

class ListScenariosRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListScenariosResponse(_message.Message):
    __slots__ = ("scenarios",)
    SCENARIOS_FIELD_NUMBER: _ClassVar[int]
    scenarios: _containers.RepeatedCompositeFieldContainer[ScenarioInfo]
    def __init__(self, scenarios: _Optional[_Iterable[_Union[ScenarioInfo, _Mapping[str, _Any]]]] = ...) -> None: ...
