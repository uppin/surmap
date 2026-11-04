from surmap.agent.proto import execution_pb2 as _execution_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StationState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATION_STATE_UNSPECIFIED: _ClassVar[StationState]
    STATION_STATE_OFF: _ClassVar[StationState]
    STATION_STATE_QUEUED: _ClassVar[StationState]
    STATION_STATE_STARTING: _ClassVar[StationState]
    STATION_STATE_READY: _ClassVar[StationState]
    STATION_STATE_STOPPING: _ClassVar[StationState]
    STATION_STATE_ERROR: _ClassVar[StationState]
STATION_STATE_UNSPECIFIED: StationState
STATION_STATE_OFF: StationState
STATION_STATE_QUEUED: StationState
STATION_STATE_STARTING: StationState
STATION_STATE_READY: StationState
STATION_STATE_STOPPING: StationState
STATION_STATE_ERROR: StationState

class GetStationStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartStationRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StopStationRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StationStatusResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: StationStatus
    def __init__(self, status: _Optional[_Union[StationStatus, _Mapping[str, _Any]]] = ...) -> None: ...

class StationStatus(_message.Message):
    __slots__ = ("state", "detail", "containers", "idle_timeout_s", "idle_for_s", "backend")
    STATE_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    CONTAINERS_FIELD_NUMBER: _ClassVar[int]
    IDLE_TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    IDLE_FOR_S_FIELD_NUMBER: _ClassVar[int]
    BACKEND_FIELD_NUMBER: _ClassVar[int]
    state: StationState
    detail: str
    containers: int
    idle_timeout_s: int
    idle_for_s: int
    backend: str
    def __init__(self, state: _Optional[_Union[StationState, str]] = ..., detail: _Optional[str] = ..., containers: _Optional[int] = ..., idle_timeout_s: _Optional[int] = ..., idle_for_s: _Optional[int] = ..., backend: _Optional[str] = ...) -> None: ...
