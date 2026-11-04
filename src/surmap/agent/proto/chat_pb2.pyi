from surmap.agent.proto import execution_pb2 as _execution_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StreamTurnRequest(_message.Message):
    __slots__ = ("conversation_id", "text", "model_id")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    text: str
    model_id: str
    def __init__(self, conversation_id: _Optional[str] = ..., text: _Optional[str] = ..., model_id: _Optional[str] = ...) -> None: ...

class WatchConversationRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class SteerRequest(_message.Message):
    __slots__ = ("conversation_id", "text")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    text: str
    def __init__(self, conversation_id: _Optional[str] = ..., text: _Optional[str] = ...) -> None: ...

class SteerResponse(_message.Message):
    __slots__ = ("accepted",)
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    def __init__(self, accepted: bool = ...) -> None: ...

class CancelTurnRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class CancelTurnResponse(_message.Message):
    __slots__ = ("cancelled",)
    CANCELLED_FIELD_NUMBER: _ClassVar[int]
    cancelled: bool
    def __init__(self, cancelled: bool = ...) -> None: ...

class ListModelsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ChatModel(_message.Message):
    __slots__ = ("id", "provider", "display_name", "available", "detail")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    id: str
    provider: str
    display_name: str
    available: bool
    detail: str
    def __init__(self, id: _Optional[str] = ..., provider: _Optional[str] = ..., display_name: _Optional[str] = ..., available: bool = ..., detail: _Optional[str] = ...) -> None: ...

class ListModelsResponse(_message.Message):
    __slots__ = ("models", "default_model_id")
    MODELS_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    models: _containers.RepeatedCompositeFieldContainer[ChatModel]
    default_model_id: str
    def __init__(self, models: _Optional[_Iterable[_Union[ChatModel, _Mapping[str, _Any]]]] = ..., default_model_id: _Optional[str] = ...) -> None: ...

class GetConversationRequest(_message.Message):
    __slots__ = ("conversation_id",)
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    def __init__(self, conversation_id: _Optional[str] = ...) -> None: ...

class GetConversationResponse(_message.Message):
    __slots__ = ("conversation_id", "events")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    events: _containers.RepeatedCompositeFieldContainer[TurnEvent]
    def __init__(self, conversation_id: _Optional[str] = ..., events: _Optional[_Iterable[_Union[TurnEvent, _Mapping[str, _Any]]]] = ...) -> None: ...

class UserMessage(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class ToolCallStarted(_message.Message):
    __slots__ = ("call_id", "tool", "arguments_json", "execution")
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    TOOL_FIELD_NUMBER: _ClassVar[int]
    ARGUMENTS_JSON_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_FIELD_NUMBER: _ClassVar[int]
    call_id: str
    tool: str
    arguments_json: str
    execution: _execution_pb2.ExecutionPolicy
    def __init__(self, call_id: _Optional[str] = ..., tool: _Optional[str] = ..., arguments_json: _Optional[str] = ..., execution: _Optional[_Union[_execution_pb2.ExecutionPolicy, _Mapping[str, _Any]]] = ...) -> None: ...

class ToolCallFinished(_message.Message):
    __slots__ = ("call_id", "status", "result_json", "image", "media_type", "job")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATUS_UNSPECIFIED: _ClassVar[ToolCallFinished.Status]
        SUCCEEDED: _ClassVar[ToolCallFinished.Status]
        FAILED: _ClassVar[ToolCallFinished.Status]
        DETACHED: _ClassVar[ToolCallFinished.Status]
        CANCELLED: _ClassVar[ToolCallFinished.Status]
    STATUS_UNSPECIFIED: ToolCallFinished.Status
    SUCCEEDED: ToolCallFinished.Status
    FAILED: ToolCallFinished.Status
    DETACHED: ToolCallFinished.Status
    CANCELLED: ToolCallFinished.Status
    CALL_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    MEDIA_TYPE_FIELD_NUMBER: _ClassVar[int]
    JOB_FIELD_NUMBER: _ClassVar[int]
    call_id: str
    status: ToolCallFinished.Status
    result_json: str
    image: bytes
    media_type: str
    job: _execution_pb2.JobHandle
    def __init__(self, call_id: _Optional[str] = ..., status: _Optional[_Union[ToolCallFinished.Status, str]] = ..., result_json: _Optional[str] = ..., image: _Optional[bytes] = ..., media_type: _Optional[str] = ..., job: _Optional[_Union[_execution_pb2.JobHandle, _Mapping[str, _Any]]] = ...) -> None: ...

class SteerApplied(_message.Message):
    __slots__ = ("text", "detached_call_ids")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    DETACHED_CALL_IDS_FIELD_NUMBER: _ClassVar[int]
    text: str
    detached_call_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, text: _Optional[str] = ..., detached_call_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class SubagentMessage(_message.Message):
    __slots__ = ("subagent_id", "name", "text")
    SUBAGENT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    subagent_id: str
    name: str
    text: str
    def __init__(self, subagent_id: _Optional[str] = ..., name: _Optional[str] = ..., text: _Optional[str] = ...) -> None: ...

class SubagentStatus(_message.Message):
    __slots__ = ("subagent_id", "name", "job_id", "status", "detail")
    SUBAGENT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    subagent_id: str
    name: str
    job_id: str
    status: _execution_pb2.JobStatus
    detail: str
    def __init__(self, subagent_id: _Optional[str] = ..., name: _Optional[str] = ..., job_id: _Optional[str] = ..., status: _Optional[_Union[_execution_pb2.JobStatus, str]] = ..., detail: _Optional[str] = ...) -> None: ...

class TurnFinished(_message.Message):
    __slots__ = ("reason",)
    class Reason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        REASON_UNSPECIFIED: _ClassVar[TurnFinished.Reason]
        STOP: _ClassVar[TurnFinished.Reason]
        LENGTH: _ClassVar[TurnFinished.Reason]
        CANCELLED: _ClassVar[TurnFinished.Reason]
        ERROR: _ClassVar[TurnFinished.Reason]
    REASON_UNSPECIFIED: TurnFinished.Reason
    STOP: TurnFinished.Reason
    LENGTH: TurnFinished.Reason
    CANCELLED: TurnFinished.Reason
    ERROR: TurnFinished.Reason
    REASON_FIELD_NUMBER: _ClassVar[int]
    reason: TurnFinished.Reason
    def __init__(self, reason: _Optional[_Union[TurnFinished.Reason, str]] = ...) -> None: ...

class TurnError(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class TurnEvent(_message.Message):
    __slots__ = ("conversation_id", "turn_id", "seq", "text_delta", "tool_call_started", "tool_call_finished", "job_update", "steer_applied", "turn_finished", "error", "user_message", "subagent_message", "subagent_status")
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    TURN_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    TEXT_DELTA_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALL_STARTED_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALL_FINISHED_FIELD_NUMBER: _ClassVar[int]
    JOB_UPDATE_FIELD_NUMBER: _ClassVar[int]
    STEER_APPLIED_FIELD_NUMBER: _ClassVar[int]
    TURN_FINISHED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    USER_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SUBAGENT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SUBAGENT_STATUS_FIELD_NUMBER: _ClassVar[int]
    conversation_id: str
    turn_id: str
    seq: int
    text_delta: str
    tool_call_started: ToolCallStarted
    tool_call_finished: ToolCallFinished
    job_update: _execution_pb2.JobHandle
    steer_applied: SteerApplied
    turn_finished: TurnFinished
    error: TurnError
    user_message: UserMessage
    subagent_message: SubagentMessage
    subagent_status: SubagentStatus
    def __init__(self, conversation_id: _Optional[str] = ..., turn_id: _Optional[str] = ..., seq: _Optional[int] = ..., text_delta: _Optional[str] = ..., tool_call_started: _Optional[_Union[ToolCallStarted, _Mapping[str, _Any]]] = ..., tool_call_finished: _Optional[_Union[ToolCallFinished, _Mapping[str, _Any]]] = ..., job_update: _Optional[_Union[_execution_pb2.JobHandle, _Mapping[str, _Any]]] = ..., steer_applied: _Optional[_Union[SteerApplied, _Mapping[str, _Any]]] = ..., turn_finished: _Optional[_Union[TurnFinished, _Mapping[str, _Any]]] = ..., error: _Optional[_Union[TurnError, _Mapping[str, _Any]]] = ..., user_message: _Optional[_Union[UserMessage, _Mapping[str, _Any]]] = ..., subagent_message: _Optional[_Union[SubagentMessage, _Mapping[str, _Any]]] = ..., subagent_status: _Optional[_Union[SubagentStatus, _Mapping[str, _Any]]] = ...) -> None: ...
