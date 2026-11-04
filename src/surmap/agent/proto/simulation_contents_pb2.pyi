from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DescribeScenarioRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class SceneItem(_message.Message):
    __slots__ = ("id", "kind", "detail", "position_enu", "has_behaviour")
    ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    POSITION_ENU_FIELD_NUMBER: _ClassVar[int]
    HAS_BEHAVIOUR_FIELD_NUMBER: _ClassVar[int]
    id: str
    kind: str
    detail: str
    position_enu: _containers.RepeatedScalarFieldContainer[float]
    has_behaviour: bool
    def __init__(self, id: _Optional[str] = ..., kind: _Optional[str] = ..., detail: _Optional[str] = ..., position_enu: _Optional[_Iterable[float]] = ..., has_behaviour: bool = ...) -> None: ...

class DescribeScenarioResponse(_message.Message):
    __slots__ = ("id", "name", "version", "url", "weather", "items", "credits")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    WEATHER_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    CREDITS_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    version: int
    url: str
    weather: str
    items: _containers.RepeatedCompositeFieldContainer[SceneItem]
    credits: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., version: _Optional[int] = ..., url: _Optional[str] = ..., weather: _Optional[str] = ..., items: _Optional[_Iterable[_Union[SceneItem, _Mapping[str, _Any]]]] = ..., credits: _Optional[_Iterable[str]] = ...) -> None: ...
