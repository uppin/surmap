from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExecutionMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXECUTION_MODE_UNSPECIFIED: _ClassVar[ExecutionMode]
    SYNC: _ClassVar[ExecutionMode]
    ASYNC: _ClassVar[ExecutionMode]

class OnTimeout(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ON_TIMEOUT_UNSPECIFIED: _ClassVar[OnTimeout]
    FAIL: _ClassVar[OnTimeout]
    DETACH: _ClassVar[OnTimeout]

class JobStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    JOB_STATUS_UNSPECIFIED: _ClassVar[JobStatus]
    RUNNING: _ClassVar[JobStatus]
    SUCCEEDED: _ClassVar[JobStatus]
    FAILED: _ClassVar[JobStatus]
    CANCELLED: _ClassVar[JobStatus]
EXECUTION_MODE_UNSPECIFIED: ExecutionMode
SYNC: ExecutionMode
ASYNC: ExecutionMode
ON_TIMEOUT_UNSPECIFIED: OnTimeout
FAIL: OnTimeout
DETACH: OnTimeout
JOB_STATUS_UNSPECIFIED: JobStatus
RUNNING: JobStatus
SUCCEEDED: JobStatus
FAILED: JobStatus
CANCELLED: JobStatus
DEFAULT_EXECUTION_FIELD_NUMBER: int
default_execution: _descriptor.FieldDescriptor

class ExecutionPolicy(_message.Message):
    __slots__ = ("mode", "timeout_s", "on_timeout")
    MODE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    ON_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    mode: ExecutionMode
    timeout_s: int
    on_timeout: OnTimeout
    def __init__(self, mode: _Optional[_Union[ExecutionMode, str]] = ..., timeout_s: _Optional[int] = ..., on_timeout: _Optional[_Union[OnTimeout, str]] = ...) -> None: ...

class JobHandle(_message.Message):
    __slots__ = ("job_id", "tool", "status", "detail")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    TOOL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    tool: str
    status: JobStatus
    detail: str
    def __init__(self, job_id: _Optional[str] = ..., tool: _Optional[str] = ..., status: _Optional[_Union[JobStatus, str]] = ..., detail: _Optional[str] = ...) -> None: ...
