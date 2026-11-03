from surmap.agent.proto import execution_pb2 as _execution_pb2
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
    __slots__ = ("id", "material", "size", "position", "yaw_deg", "collider", "ground_truth_kind")
    ID_FIELD_NUMBER: _ClassVar[int]
    MATERIAL_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    COLLIDER_FIELD_NUMBER: _ClassVar[int]
    GROUND_TRUTH_KIND_FIELD_NUMBER: _ClassVar[int]
    id: str
    material: str
    size: EnuPoint
    position: EnuPoint
    yaw_deg: float
    collider: bool
    ground_truth_kind: str
    def __init__(self, id: _Optional[str] = ..., material: _Optional[str] = ..., size: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., collider: bool = ..., ground_truth_kind: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("id", "position", "coat")
    ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    COAT_FIELD_NUMBER: _ClassVar[int]
    id: str
    position: EnuPoint
    coat: str
    def __init__(self, id: _Optional[str] = ..., position: _Optional[_Union[EnuPoint, _Mapping[str, _Any]]] = ..., coat: _Optional[str] = ...) -> None: ...

class AddElementRequest(_message.Message):
    __slots__ = ("scenario_id", "box", "building", "collapsed_building", "person")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    BOX_FIELD_NUMBER: _ClassVar[int]
    BUILDING_FIELD_NUMBER: _ClassVar[int]
    COLLAPSED_BUILDING_FIELD_NUMBER: _ClassVar[int]
    PERSON_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    box: BoxElement
    building: BuildingElement
    collapsed_building: CollapsedBuildingElement
    person: PersonElement
    def __init__(self, scenario_id: _Optional[str] = ..., box: _Optional[_Union[BoxElement, _Mapping[str, _Any]]] = ..., building: _Optional[_Union[BuildingElement, _Mapping[str, _Any]]] = ..., collapsed_building: _Optional[_Union[CollapsedBuildingElement, _Mapping[str, _Any]]] = ..., person: _Optional[_Union[PersonElement, _Mapping[str, _Any]]] = ...) -> None: ...

class RemoveElementRequest(_message.Message):
    __slots__ = ("scenario_id", "element_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ELEMENT_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    element_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., element_id: _Optional[str] = ...) -> None: ...

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
