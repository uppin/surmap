from google.protobuf import wrappers_pb2 as _wrappers_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import Any as _Any, ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SocketFrame(_message.Message):
    __slots__ = ("request", "response")
    REQUEST_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FIELD_NUMBER: _ClassVar[int]
    request: SocketRequest
    response: SocketResponse
    def __init__(self, request: _Optional[_Union[SocketRequest, _Mapping[str, _Any]]] = ..., response: _Optional[_Union[SocketResponse, _Mapping[str, _Any]]] = ...) -> None: ...

class SocketRequest(_message.Message):
    __slots__ = ("stream_id", "message", "call_init", "end_of_stream", "abort")
    STREAM_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CALL_INIT_FIELD_NUMBER: _ClassVar[int]
    END_OF_STREAM_FIELD_NUMBER: _ClassVar[int]
    ABORT_FIELD_NUMBER: _ClassVar[int]
    stream_id: int
    message: _wrappers_pb2.BytesValue
    call_init: CallInit
    end_of_stream: bool
    abort: bool
    def __init__(self, stream_id: _Optional[int] = ..., message: _Optional[_Union[_wrappers_pb2.BytesValue, _Mapping[str, _Any]]] = ..., call_init: _Optional[_Union[CallInit, _Mapping[str, _Any]]] = ..., end_of_stream: bool = ..., abort: bool = ...) -> None: ...

class SocketResponse(_message.Message):
    __slots__ = ("stream_id", "message", "headers", "end_of_stream", "error", "trailers")
    STREAM_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    HEADERS_FIELD_NUMBER: _ClassVar[int]
    END_OF_STREAM_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    TRAILERS_FIELD_NUMBER: _ClassVar[int]
    stream_id: int
    message: _wrappers_pb2.BytesValue
    headers: SocketMetadata
    end_of_stream: bool
    error: SocketError
    trailers: SocketMetadata
    def __init__(self, stream_id: _Optional[int] = ..., message: _Optional[_Union[_wrappers_pb2.BytesValue, _Mapping[str, _Any]]] = ..., headers: _Optional[_Union[SocketMetadata, _Mapping[str, _Any]]] = ..., end_of_stream: bool = ..., error: _Optional[_Union[SocketError, _Mapping[str, _Any]]] = ..., trailers: _Optional[_Union[SocketMetadata, _Mapping[str, _Any]]] = ...) -> None: ...

class CallInit(_message.Message):
    __slots__ = ("service_name", "method_name", "timeout_ms", "metadata")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    METHOD_NAME_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    service_name: _wrappers_pb2.StringValue
    method_name: _wrappers_pb2.StringValue
    timeout_ms: _wrappers_pb2.Int32Value
    metadata: SocketMetadata
    def __init__(self, service_name: _Optional[_Union[_wrappers_pb2.StringValue, _Mapping[str, _Any]]] = ..., method_name: _Optional[_Union[_wrappers_pb2.StringValue, _Mapping[str, _Any]]] = ..., timeout_ms: _Optional[_Union[_wrappers_pb2.Int32Value, _Mapping[str, _Any]]] = ..., metadata: _Optional[_Union[SocketMetadata, _Mapping[str, _Any]]] = ...) -> None: ...

class SocketMetadata(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[SocketMetadataEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[SocketMetadataEntry, _Mapping[str, _Any]]]] = ...) -> None: ...

class SocketMetadataEntry(_message.Message):
    __slots__ = ("key", "values")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    key: _wrappers_pb2.StringValue
    values: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, key: _Optional[_Union[_wrappers_pb2.StringValue, _Mapping[str, _Any]]] = ..., values: _Optional[_Iterable[bytes]] = ...) -> None: ...

class SocketError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: int
    message: _wrappers_pb2.StringValue
    def __init__(self, code: _Optional[int] = ..., message: _Optional[_Union[_wrappers_pb2.StringValue, _Mapping[str, _Any]]] = ...) -> None: ...
