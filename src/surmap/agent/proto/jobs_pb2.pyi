from surmap.agent.proto import execution_pb2 as _execution_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class WaitMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WAIT_MODE_UNSPECIFIED: _ClassVar[WaitMode]
    ALL: _ClassVar[WaitMode]
    ANY: _ClassVar[WaitMode]
WAIT_MODE_UNSPECIFIED: WaitMode
ALL: WaitMode
ANY: WaitMode

class JobResult(_message.Message):
    __slots__ = ("job", "result_json", "image", "media_type")
    JOB_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    MEDIA_TYPE_FIELD_NUMBER: _ClassVar[int]
    job: _execution_pb2.JobHandle
    result_json: str
    image: bytes
    media_type: str
    def __init__(self, job: _Optional[_Union[_execution_pb2.JobHandle, _Mapping[str, _Any]]] = ..., result_json: _Optional[str] = ..., image: _Optional[bytes] = ..., media_type: _Optional[str] = ...) -> None: ...

class WaitForJobsRequest(_message.Message):
    __slots__ = ("job_ids", "mode", "timeout_s")
    JOB_IDS_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    job_ids: _containers.RepeatedScalarFieldContainer[str]
    mode: WaitMode
    timeout_s: int
    def __init__(self, job_ids: _Optional[_Iterable[str]] = ..., mode: _Optional[_Union[WaitMode, str]] = ..., timeout_s: _Optional[int] = ...) -> None: ...

class WaitForJobsResponse(_message.Message):
    __slots__ = ("jobs", "timed_out")
    JOBS_FIELD_NUMBER: _ClassVar[int]
    TIMED_OUT_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[JobResult]
    timed_out: bool
    def __init__(self, jobs: _Optional[_Iterable[_Union[JobResult, _Mapping[str, _Any]]]] = ..., timed_out: bool = ...) -> None: ...

class GetJobRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetJobResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: JobResult
    def __init__(self, job: _Optional[_Union[JobResult, _Mapping[str, _Any]]] = ...) -> None: ...

class CancelJobRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class CancelJobResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: _execution_pb2.JobHandle
    def __init__(self, job: _Optional[_Union[_execution_pb2.JobHandle, _Mapping[str, _Any]]] = ...) -> None: ...

class ListJobsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListJobsResponse(_message.Message):
    __slots__ = ("jobs",)
    JOBS_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[_execution_pb2.JobHandle]
    def __init__(self, jobs: _Optional[_Iterable[_Union[_execution_pb2.JobHandle, _Mapping[str, _Any]]]] = ...) -> None: ...
