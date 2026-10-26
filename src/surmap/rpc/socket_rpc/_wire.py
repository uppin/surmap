"""Encode and decode `SocketFrame` protobuf messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from google.protobuf import wrappers_pb2

from surmap.transport.v1 import socket_rpc_pb2

if TYPE_CHECKING:
    from connectrpc.code import Code

from surmap.rpc.socket_rpc._codes import code_from_wire, code_to_wire

__all__ = [
    "decode_frame",
    "encode_frame",
    "headers_from_metadata",
    "metadata_from_headers",
    "socket_error",
]


def encode_frame(frame: socket_rpc_pb2.SocketFrame) -> bytes:
    return frame.SerializeToString()


def decode_frame(data: bytes) -> socket_rpc_pb2.SocketFrame:
    from google.protobuf.message import DecodeError

    frame = socket_rpc_pb2.SocketFrame()
    try:
        frame.ParseFromString(data)
    except DecodeError as error:
        msg = "malformed socket frame"
        raise ValueError(msg) from error
    return frame


def metadata_from_headers(headers: Mapping[str, str]) -> socket_rpc_pb2.SocketMetadata:
    meta = socket_rpc_pb2.SocketMetadata()
    for key, value in headers.items():
        entry = socket_rpc_pb2.SocketMetadataEntry(key=wrappers_pb2.StringValue(value=key.lower()))
        entry.values.append(value.encode("utf-8"))
        meta.entries.append(entry)
    return meta


def headers_from_metadata(meta: socket_rpc_pb2.SocketMetadata | None) -> dict[str, str]:
    if meta is None:
        return {}
    headers: dict[str, str] = {}
    for entry in meta.entries:
        if not entry.key.value:
            continue
        key = entry.key.value.lower()
        if not entry.values:
            continue
        if key.endswith("-bin"):
            headers[key] = b",".join(entry.values).decode("latin-1")
        elif len(entry.values) == 1:
            headers[key] = entry.values[0].decode("utf-8", errors="surrogateescape")
        else:
            headers[key] = ",".join(
                value.decode("utf-8", errors="surrogateescape") for value in entry.values
            )
    return headers


def socket_error(code: Code, message: str) -> socket_rpc_pb2.SocketError:
    return socket_rpc_pb2.SocketError(
        code=code_to_wire(code),
        message=wrappers_pb2.StringValue(value=message),
    )


def error_from_socket(err: socket_rpc_pb2.SocketError) -> tuple[Code, str]:

    code = code_from_wire(err.code)
    message = err.message.value if err.message else ""
    return code, message


def bytes_field(data: bytes) -> wrappers_pb2.BytesValue:
    return wrappers_pb2.BytesValue(value=data)


def message_bytes(field: wrappers_pb2.BytesValue | None) -> bytes:
    if field is None or not field.value:
        return b""
    return field.value
