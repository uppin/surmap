"""Request decoding and response encoding for HTTP rules — pure functions, no server.

Request decoding merges the JSON body, query parameters and path parameters:

- JSON body, path variables and query parameters union into one message (`fromJSON`).
- Overlay order (later wins on the same key): body, then path, then query,
  then GET `.r` base64url JSON.
- Path vs query inside the overlay: query wins over path.
- Proto `google.api.http` `body` is unsupported; bindings never declare it.

Unknown JSON / query keys are refused, as on the Connect binding.

Encoding is proto3 JSON (lowerCamelCase names, defaults omitted), compact and UTF-8.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qsl

from connectrpc.code import Code
from connectrpc.errors import ErrorDetail
from google.protobuf import json_format
from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import Message

if TYPE_CHECKING:
    from surmap.rpc.http_rule.routes import HttpBinding

__all__ = [
    "NDJSON_CONTENT_TYPE",
    "HttpRuleError",
    "decode_request",
    "encode_error",
    "encode_response",
    "encode_stream_error",
    "encode_stream_result",
    "grpc_code_number",
    "http_status_for",
]

NDJSON_CONTENT_TYPE = "application/x-ndjson"
_DOT_R_QUERY_PARAM = ".r"
_BODYLESS_METHODS = frozenset({"GET", "HEAD"})

_GRPC_NUMBER: Mapping[Code, int] = {
    Code.CANCELED: 1,
    Code.UNKNOWN: 2,
    Code.INVALID_ARGUMENT: 3,
    Code.DEADLINE_EXCEEDED: 4,
    Code.NOT_FOUND: 5,
    Code.ALREADY_EXISTS: 6,
    Code.PERMISSION_DENIED: 7,
    Code.RESOURCE_EXHAUSTED: 8,
    Code.FAILED_PRECONDITION: 9,
    Code.ABORTED: 10,
    Code.OUT_OF_RANGE: 11,
    Code.UNIMPLEMENTED: 12,
    Code.INTERNAL: 13,
    Code.UNAVAILABLE: 14,
    Code.DATA_LOSS: 15,
    Code.UNAUTHENTICATED: 16,
}

# The google.rpc code → HTTP status mapping (google/rpc/code.proto, as grpc-gateway applies it).
_HTTP_STATUS: Mapping[Code, int] = {
    Code.CANCELED: 499,
    Code.UNKNOWN: 500,
    Code.INVALID_ARGUMENT: 400,
    Code.DEADLINE_EXCEEDED: 504,
    Code.NOT_FOUND: 404,
    Code.ALREADY_EXISTS: 409,
    Code.PERMISSION_DENIED: 403,
    Code.RESOURCE_EXHAUSTED: 429,
    Code.FAILED_PRECONDITION: 400,
    Code.ABORTED: 409,
    Code.OUT_OF_RANGE: 400,
    Code.UNIMPLEMENTED: 501,
    Code.INTERNAL: 500,
    Code.UNAVAILABLE: 503,
    Code.DATA_LOSS: 500,
    Code.UNAUTHENTICATED: 401,
}

_INTEGER = re.compile(r"-?\d+")
_INT_RANGES: Mapping[int, tuple[int, int]] = {
    FieldDescriptor.TYPE_INT32: (-(2**31), 2**31 - 1),
    FieldDescriptor.TYPE_SINT32: (-(2**31), 2**31 - 1),
    FieldDescriptor.TYPE_SFIXED32: (-(2**31), 2**31 - 1),
    FieldDescriptor.TYPE_UINT32: (0, 2**32 - 1),
    FieldDescriptor.TYPE_FIXED32: (0, 2**32 - 1),
    FieldDescriptor.TYPE_INT64: (-(2**63), 2**63 - 1),
    FieldDescriptor.TYPE_SINT64: (-(2**63), 2**63 - 1),
    FieldDescriptor.TYPE_SFIXED64: (-(2**63), 2**63 - 1),
    FieldDescriptor.TYPE_UINT64: (0, 2**64 - 1),
    FieldDescriptor.TYPE_FIXED64: (0, 2**64 - 1),
}
_FLOATS = frozenset({FieldDescriptor.TYPE_DOUBLE, FieldDescriptor.TYPE_FLOAT})
_FLOAT_WORDS: Mapping[str, float] = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}
_JSON_STRING_TYPES = frozenset(
    {"google.protobuf.Timestamp", "google.protobuf.Duration", "google.protobuf.FieldMask"}
)
# Query and path values may carry bytes in either base64 alphabet; decode both.
_URLSAFE_TO_STANDARD = str.maketrans("-_", "+/")
_WRAPPER_TYPES = frozenset(
    f"google.protobuf.{name}"
    for name in (
        "DoubleValue",
        "FloatValue",
        "Int64Value",
        "UInt64Value",
        "Int32Value",
        "UInt32Value",
        "BoolValue",
        "StringValue",
        "BytesValue",
    )
)


class HttpRuleError(Exception):
    """A request the binding refuses, with the gRPC code it is refused with."""

    def __init__(self, code: Code, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def grpc_code_number(code: Code) -> int:
    return _GRPC_NUMBER[code]


def http_status_for(code: Code) -> int:
    return _HTTP_STATUS[code]


# --- decoding -------------------------------------------------------------------------------------


def decode_request(
    binding: HttpBinding,
    *,
    path_params: Mapping[str, str],
    query: str,
    body: bytes,
) -> Message:
    """The request message a REST request describes. Raises `HttpRuleError(INVALID_ARGUMENT)`."""
    request = binding.request_class()
    has_body = bool(body.strip())
    params = _query_params(query)
    dot_r_values = params.pop(_DOT_R_QUERY_PARAM, None)
    dot_r = _decode_dot_r_query(binding.http_method, dot_r_values)

    if has_body:
        _parse_json_into(request, _load_json(body, require_object=True), what="body")

    for name, raw in path_params.items():
        _set_leaf(request, tuple(name.split(".")), [raw], label=f'path variable "{name}"')

    for key, values in params.items():
        _apply_query_param(request, key, values)

    if dot_r:
        _parse_json_into(request, dot_r, what=f'query parameter "{_DOT_R_QUERY_PARAM}"')
    return request


def _decode_dot_r_query(http_method: str, values: list[str] | None) -> dict[str, Any]:
    if not values:
        return {}
    if http_method not in _BODYLESS_METHODS:
        raise _invalid(
            f'query parameter "{_DOT_R_QUERY_PARAM}" is allowed only on GET HTTP methods'
        )
    raw = values[-1]
    try:
        payload = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        decoded = json.loads(payload.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid(
            f'query parameter "{_DOT_R_QUERY_PARAM}" is not valid base64url JSON: {error}'
        ) from error
    if not isinstance(decoded, dict):
        raise _invalid(f'query parameter "{_DOT_R_QUERY_PARAM}" must decode to a JSON object')
    return decoded


def _invalid(message: str) -> HttpRuleError:
    return HttpRuleError(Code.INVALID_ARGUMENT, message)


def _query_params(query: str) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    try:
        pairs = parse_qsl(query, keep_blank_values=True, errors="strict")
    except (UnicodeDecodeError, ValueError) as error:
        raise _invalid(f"query string is not valid UTF-8: {error}") from error
    for key, value in pairs:
        params.setdefault(key, []).append(value)
    return params


def _load_json(body: bytes, *, require_object: bool) -> Any:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid(f"body is not valid JSON: {error}") from error
    if require_object and not isinstance(value, dict):
        raise _invalid("body must be a JSON object")
    return value


def _parse_json_into(message: Message, value: dict[str, Any], *, what: str) -> None:
    try:
        json_format.ParseDict(value, message, ignore_unknown_fields=False)
    except json_format.ParseError as error:
        raise _invalid(f"invalid {what}: {error}") from error


def _apply_query_param(request: Message, key: str, values: list[str]) -> None:
    names = _field_path(cast(Descriptor, request.DESCRIPTOR), key)
    _set_leaf(request, names, values, label=f'query parameter "{key}"')


def _field_path(descriptor: Descriptor, key: str) -> tuple[str, ...]:
    """Proto names along `key`, which may spell each part by its proto or its JSON name."""
    names: list[str] = []
    current: Descriptor | None = descriptor
    parts = key.split(".")
    for position, part in enumerate(parts):
        if current is None:
            raise _invalid(f'unknown query parameter "{key}"')
        field = current.fields_by_name.get(part) or _by_json_name(current, part)
        if field is None:
            raise _invalid(f'unknown query parameter "{key}"')
        names.append(field.name)
        last = position == len(parts) - 1
        if not last:
            if (
                field.type != FieldDescriptor.TYPE_MESSAGE
                or field.is_repeated
                or _is_wrapper(field)
                or field.message_type is None
                or field.message_type.full_name in _JSON_STRING_TYPES
            ):
                raise _invalid(
                    f'query parameter "{key}" passes through "{part}", '
                    "which is not a singular message"
                )
            if field.message_type is None:
                raise _invalid(f'query parameter "{key}" passes through "{part}"')
            current = field.message_type
    return tuple(names)


def _by_json_name(descriptor: Descriptor, name: str) -> FieldDescriptor | None:
    for field in descriptor.fields:
        if field.json_name == name:
            return field
    return None


def _is_wrapper(field: FieldDescriptor) -> bool:
    if field.type != FieldDescriptor.TYPE_MESSAGE:
        return False
    return field.message_type is not None and field.message_type.full_name in _WRAPPER_TYPES


def _set_leaf(request: Message, names: tuple[str, ...], values: list[str], *, label: str) -> None:
    target = request
    descriptor = request.DESCRIPTOR
    for name in names[:-1]:
        target = getattr(target, name)
        next_descriptor = descriptor.fields_by_name[name].message_type
        if next_descriptor is None:
            raise _invalid(f"{label}: {name!r} is not a message field")
        descriptor = cast(Descriptor, next_descriptor)
    field = cast(FieldDescriptor | None, descriptor.fields_by_name.get(names[-1]))
    if field is None:
        raise _invalid(f"{label}: {descriptor.full_name} has no field {names[-1]!r}")

    if field.type == FieldDescriptor.TYPE_MESSAGE:
        if field.is_repeated or (field.message_type and field.message_type.GetOptions().map_entry):
            raise _invalid(f"{label} cannot set a repeated message or map field")
        if not (
            _is_wrapper(field)
            or (field.message_type and field.message_type.full_name in _JSON_STRING_TYPES)
        ):
            raise _invalid(f"{label} names a message; name one of its fields instead")
        if len(values) > 1:
            raise _invalid(f"{label} is not repeated but was given {len(values)} values")
        child = getattr(target, field.name)
        if _is_wrapper(field):
            message_type = field.message_type
            if message_type is None:
                raise _invalid(f"{label} names a message; name one of its fields instead")
            inner = message_type.fields_by_name["value"]
            converted = _convert_scalar(inner, values[0], label=label)
            child.SetInParent()
            child.value = converted
        else:
            try:
                json_format.Parse(json.dumps(values[0]), child)
            except json_format.ParseError as error:
                raise _invalid(f"{label}: {error}") from error
        return

    converted_values = [_convert_scalar(field, value, label=label) for value in values]
    if field.is_repeated:
        getattr(target, field.name).extend(converted_values)
        return
    if len(converted_values) > 1:
        raise _invalid(f"{label} is not repeated but was given {len(converted_values)} values")
    setattr(target, field.name, converted_values[0])


def _convert_scalar(field: FieldDescriptor, raw: str, *, label: str) -> object:
    kind = field.type
    if kind == FieldDescriptor.TYPE_STRING:
        return raw
    if kind == FieldDescriptor.TYPE_BOOL:
        if raw not in ("true", "false"):
            raise _invalid(f'{label}: "{raw}" is not true or false')
        return raw == "true"
    if kind in _INT_RANGES:
        low, high = _INT_RANGES[kind]
        if not _INTEGER.fullmatch(raw) or not low <= int(raw) <= high:
            raise _invalid(f'{label}: "{raw}" is not an integer in [{low}, {high}]')
        return int(raw)
    if kind in _FLOATS:
        if raw in _FLOAT_WORDS:
            return _FLOAT_WORDS[raw]
        try:
            value = float(raw)
        except ValueError as error:
            raise _invalid(f'{label}: "{raw}" is not a number') from error
        if not math.isfinite(value):
            raise _invalid(f'{label}: "{raw}" — write NaN, Infinity or -Infinity')
        return value
    if kind == FieldDescriptor.TYPE_BYTES:
        return _decode_base64(raw, label=label)
    if kind == FieldDescriptor.TYPE_ENUM:
        enum_type = field.enum_type
        if enum_type is None:
            raise _invalid(f'{label}: "{raw}" is not an enum value')
        named = enum_type.values_by_name.get(raw)
        if named is not None:
            return named.number
        if _INTEGER.fullmatch(raw) and -(2**31) <= int(raw) <= 2**31 - 1:
            return int(raw)
        raise _invalid(f'{label}: "{raw}" is not a value of {enum_type.full_name}')
    raise _invalid(f"{label}: unsupported field type")


def _decode_base64(raw: str, *, label: str) -> bytes:
    standard = raw.translate(_URLSAFE_TO_STANDARD)
    padded = standard + "=" * (-len(standard) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise _invalid(f'{label}: "{raw}" is not base64') from error


# --- encoding -------------------------------------------------------------------------------------


def _dumps(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _response_value(binding: HttpBinding, message: Message) -> object:
    as_dict = json_format.MessageToDict(message)
    if not binding.response_body:
        return as_dict
    field = message.DESCRIPTOR.fields_by_name[binding.response_body]
    if field.json_name in as_dict:
        return as_dict[field.json_name]
    if field.is_repeated:
        return (
            {}
            if field.message_type is not None and field.message_type.GetOptions().map_entry
            else []
        )
    if field.type == FieldDescriptor.TYPE_MESSAGE:
        return json_format.MessageToDict(getattr(message, field.name))
    return json_format.MessageToDict(message, always_print_fields_with_no_presence=True).get(
        field.json_name
    )


def encode_response(binding: HttpBinding, message: Message) -> bytes:
    return _dumps(_response_value(binding, message))


def encode_stream_result(binding: HttpBinding, message: Message) -> bytes:
    """One NDJSON line: `{"result": ...}`."""
    return _dumps({"result": _response_value(binding, message)}) + b"\n"


def _status(
    code: Code, message: str, details: Iterable[object] = ()
) -> dict[str, object]:
    return {
        "code": grpc_code_number(code),
        "message": message,
        "details": _encode_status_details(details),
    }


def _encode_status_details(details: Iterable[object]) -> list[object]:
    encoded: list[object] = []
    for item in details:
        message = cast(Message, item.value() if isinstance(item, ErrorDetail) else item)
        encoded.append(
            json_format.MessageToDict(
                message,
                preserving_proto_field_name=False,
                use_integers_for_enums=False,
            )
        )
    return encoded


def encode_stream_error(
    code: Code, message: str, details: Iterable[object] = ()
) -> bytes:
    """The final NDJSON line of a failed stream: `{"error": <status>}`."""
    return _dumps({"error": _status(code, message, details)}) + b"\n"


def encode_error(
    code: Code, message: str, details: Iterable[object] = ()
) -> tuple[int, bytes]:
    """`(HTTP status, google.rpc.Status JSON body)`."""
    return http_status_for(code), _dumps(_status(code, message, details))
