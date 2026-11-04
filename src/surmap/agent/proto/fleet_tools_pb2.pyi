from surmap.agent.proto import execution_pb2 as _execution_pb2
from surmap.agent.proto import simulation_tools_pb2 as _simulation_tools_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DronePhase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DRONE_PHASE_UNSPECIFIED: _ClassVar[DronePhase]
    DRONE_PHASE_DOCKED: _ClassVar[DronePhase]
    DRONE_PHASE_CLIMBING: _ClassVar[DronePhase]
    DRONE_PHASE_CRUISING: _ClassVar[DronePhase]
    DRONE_PHASE_DETOURING: _ClassVar[DronePhase]
    DRONE_PHASE_HOVERING: _ClassVar[DronePhase]
    DRONE_PHASE_RETURNING: _ClassVar[DronePhase]
    DRONE_PHASE_LANDING: _ClassVar[DronePhase]

class RouteEnd(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ROUTE_END_UNSPECIFIED: _ClassVar[RouteEnd]
    ROUTE_END_RETURN: _ClassVar[RouteEnd]
    ROUTE_END_HOVER: _ClassVar[RouteEnd]
DRONE_PHASE_UNSPECIFIED: DronePhase
DRONE_PHASE_DOCKED: DronePhase
DRONE_PHASE_CLIMBING: DronePhase
DRONE_PHASE_CRUISING: DronePhase
DRONE_PHASE_DETOURING: DronePhase
DRONE_PHASE_HOVERING: DronePhase
DRONE_PHASE_RETURNING: DronePhase
DRONE_PHASE_LANDING: DronePhase
ROUTE_END_UNSPECIFIED: RouteEnd
ROUTE_END_RETURN: RouteEnd
ROUTE_END_HOVER: RouteEnd

class FleetNest(_message.Message):
    __slots__ = ("id", "position", "yaw_deg", "drone_ids")
    ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    DRONE_IDS_FIELD_NUMBER: _ClassVar[int]
    id: str
    position: _simulation_tools_pb2.EnuPoint
    yaw_deg: float
    drone_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., position: _Optional[_Union[_simulation_tools_pb2.EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., drone_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class DroneStatus(_message.Message):
    __slots__ = ("id", "nest", "phase", "position", "yaw_deg", "speed_m_s", "targets_left")
    ID_FIELD_NUMBER: _ClassVar[int]
    NEST_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    YAW_DEG_FIELD_NUMBER: _ClassVar[int]
    SPEED_M_S_FIELD_NUMBER: _ClassVar[int]
    TARGETS_LEFT_FIELD_NUMBER: _ClassVar[int]
    id: str
    nest: str
    phase: DronePhase
    position: _simulation_tools_pb2.EnuPoint
    yaw_deg: float
    speed_m_s: float
    targets_left: int
    def __init__(self, id: _Optional[str] = ..., nest: _Optional[str] = ..., phase: _Optional[_Union[DronePhase, str]] = ..., position: _Optional[_Union[_simulation_tools_pb2.EnuPoint, _Mapping[str, _Any]]] = ..., yaw_deg: _Optional[float] = ..., speed_m_s: _Optional[float] = ..., targets_left: _Optional[int] = ...) -> None: ...

class FlightRoute(_message.Message):
    __slots__ = ("waypoints", "speed_m_s", "on_complete")
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    SPEED_M_S_FIELD_NUMBER: _ClassVar[int]
    ON_COMPLETE_FIELD_NUMBER: _ClassVar[int]
    waypoints: _containers.RepeatedCompositeFieldContainer[_simulation_tools_pb2.EnuPoint]
    speed_m_s: float
    on_complete: RouteEnd
    def __init__(self, waypoints: _Optional[_Iterable[_Union[_simulation_tools_pb2.EnuPoint, _Mapping[str, _Any]]]] = ..., speed_m_s: _Optional[float] = ..., on_complete: _Optional[_Union[RouteEnd, str]] = ...) -> None: ...

class FleetCommandResult(_message.Message):
    __slots__ = ("seq", "at_s")
    SEQ_FIELD_NUMBER: _ClassVar[int]
    AT_S_FIELD_NUMBER: _ClassVar[int]
    seq: int
    at_s: float
    def __init__(self, seq: _Optional[int] = ..., at_s: _Optional[float] = ...) -> None: ...

class ListNestsRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class ListNestsResponse(_message.Message):
    __slots__ = ("nests",)
    NESTS_FIELD_NUMBER: _ClassVar[int]
    nests: _containers.RepeatedCompositeFieldContainer[FleetNest]
    def __init__(self, nests: _Optional[_Iterable[_Union[FleetNest, _Mapping[str, _Any]]]] = ...) -> None: ...

class ListDronesRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class ListDronesResponse(_message.Message):
    __slots__ = ("linked", "active", "drones", "sim_t_s")
    LINKED_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    DRONES_FIELD_NUMBER: _ClassVar[int]
    SIM_T_S_FIELD_NUMBER: _ClassVar[int]
    linked: bool
    active: str
    drones: _containers.RepeatedCompositeFieldContainer[DroneStatus]
    sim_t_s: float
    def __init__(self, linked: bool = ..., active: _Optional[str] = ..., drones: _Optional[_Iterable[_Union[DroneStatus, _Mapping[str, _Any]]]] = ..., sim_t_s: _Optional[float] = ...) -> None: ...

class LaunchDroneRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id", "route")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    route: FlightRoute
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ..., route: _Optional[_Union[FlightRoute, _Mapping[str, _Any]]] = ...) -> None: ...

class SetRouteRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id", "route")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    route: FlightRoute
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ..., route: _Optional[_Union[FlightRoute, _Mapping[str, _Any]]] = ...) -> None: ...

class AddDetourRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id", "waypoints")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    waypoints: _containers.RepeatedCompositeFieldContainer[_simulation_tools_pb2.EnuPoint]
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ..., waypoints: _Optional[_Iterable[_Union[_simulation_tools_pb2.EnuPoint, _Mapping[str, _Any]]]] = ...) -> None: ...

class RecallDroneRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ...) -> None: ...

class SetActiveDroneRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ...) -> None: ...

class GetFleetLogRequest(_message.Message):
    __slots__ = ("scenario_id", "session_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    session_id: int
    def __init__(self, scenario_id: _Optional[str] = ..., session_id: _Optional[int] = ...) -> None: ...

class GetFleetLogResponse(_message.Message):
    __slots__ = ("session_id", "fleet_log_jsonl")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    FLEET_LOG_JSONL_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    fleet_log_jsonl: str
    def __init__(self, session_id: _Optional[int] = ..., fleet_log_jsonl: _Optional[str] = ...) -> None: ...

class DroneMapStatusRequest(_message.Message):
    __slots__ = ("scenario_id", "drone_id")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    drone_id: str
    def __init__(self, scenario_id: _Optional[str] = ..., drone_id: _Optional[str] = ...) -> None: ...

class DroneMapCounts(_message.Message):
    __slots__ = ("drone_id", "frames", "posed", "lost", "keyframes", "segmented_frames", "detections", "processing", "last_t_ns", "error")
    DRONE_ID_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    POSED_FIELD_NUMBER: _ClassVar[int]
    LOST_FIELD_NUMBER: _ClassVar[int]
    KEYFRAMES_FIELD_NUMBER: _ClassVar[int]
    SEGMENTED_FRAMES_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_FIELD_NUMBER: _ClassVar[int]
    LAST_T_NS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    drone_id: str
    frames: int
    posed: int
    lost: int
    keyframes: int
    segmented_frames: int
    detections: int
    processing: bool
    last_t_ns: int
    error: str
    def __init__(self, drone_id: _Optional[str] = ..., frames: _Optional[int] = ..., posed: _Optional[int] = ..., lost: _Optional[int] = ..., keyframes: _Optional[int] = ..., segmented_frames: _Optional[int] = ..., detections: _Optional[int] = ..., processing: bool = ..., last_t_ns: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class DroneMapStatusResponse(_message.Message):
    __slots__ = ("drones",)
    DRONES_FIELD_NUMBER: _ClassVar[int]
    drones: _containers.RepeatedCompositeFieldContainer[DroneMapCounts]
    def __init__(self, drones: _Optional[_Iterable[_Union[DroneMapCounts, _Mapping[str, _Any]]]] = ...) -> None: ...

class SetOnboardModelRequest(_message.Message):
    __slots__ = ("scenario_id", "onboard_model")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    onboard_model: str
    def __init__(self, scenario_id: _Optional[str] = ..., onboard_model: _Optional[str] = ...) -> None: ...

class SetOnboardModelResponse(_message.Message):
    __slots__ = ("onboard_model", "streaming")
    ONBOARD_MODEL_FIELD_NUMBER: _ClassVar[int]
    STREAMING_FIELD_NUMBER: _ClassVar[int]
    onboard_model: str
    streaming: bool
    def __init__(self, onboard_model: _Optional[str] = ..., streaming: bool = ...) -> None: ...
