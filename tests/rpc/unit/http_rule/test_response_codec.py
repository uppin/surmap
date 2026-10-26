"""Encoding responses, NDJSON stream lines and errors — exact bytes, no server."""

from __future__ import annotations

import json

import pytest
from connectrpc.code import Code
from google.protobuf import timestamp_pb2, wrappers_pb2
from google.protobuf.message import Message

from surmap.rpc.http_rule.codec import (
    NDJSON_CONTENT_TYPE,
    encode_error,
    encode_response,
    encode_stream_error,
    encode_stream_result,
    grpc_code_number,
    http_status_for,
)
from tests.rpc.unit.http_rule.fixture import fixture
from tests.rpc.unit.http_rule.test_request_codec import binding

SERVICE = fixture()
Kitchen = SERVICE.message("Kitchen")
Inner = SERVICE.message("Inner")
GREEN = 2


def encoded(method_name: str, message: Message) -> object:
    return json.loads(encode_response(binding(method_name), message))


# --- whole-message responses ----------------------------------------------------------------------


def test_a_response_is_compact_proto3_json() -> None:
    assert encode_response(binding("GetKitchen"), Kitchen(name="k")) == b'{"name":"k"}'


def test_an_empty_response_is_an_empty_object() -> None:
    assert encode_response(binding("GetKitchen"), Kitchen()) == b"{}"


def test_a_response_uses_lower_camel_case_names_and_omits_defaults() -> None:
    assert encoded("GetKitchen", Kitchen(snake_case_field="v", i32=0, flag=False)) == {
        "snakeCaseField": "v"
    }


def test_a_response_encodes_every_field_kind_in_its_json_form() -> None:
    message = Kitchen(
        i64=-5,
        u64=18446744073709551615,
        flag=True,
        ratio=float("nan"),
        blob=b"hi",
        color=GREEN,
        inner=Inner(label="x"),
        tags=["a", "b"],
        colors=[1, 2],
        labels={"shelf": "top"},
        maybe_flag=wrappers_pb2.BoolValue(value=False),
        maybe_name=wrappers_pb2.StringValue(value=""),
        at=timestamp_pb2.Timestamp(seconds=1790856000),
        choice_number=0,
    )
    assert encoded("GetKitchen", message) == {
        "i64": "-5",
        "u64": "18446744073709551615",
        "flag": True,
        "ratio": "NaN",
        "blob": "aGk=",
        "color": "GREEN",
        "inner": {"label": "x"},
        "tags": ["a", "b"],
        "colors": ["RED", "GREEN"],
        "labels": {"shelf": "top"},
        "maybeFlag": False,
        "maybeName": "",
        "at": "2026-10-01T12:00:00Z",
        "choiceNumber": 0,
    }


def test_a_response_keeps_non_ascii_text_as_utf8() -> None:
    assert (
        encode_response(binding("GetKitchen"), Kitchen(name="café")) == '{"name":"café"}'.encode()
    )


# --- response_body --------------------------------------------------------------------------------


def test_response_body_sends_only_the_named_message_field() -> None:
    message = Kitchen(name="k", inner=Inner(label="x"))
    assert encode_response(binding("GetInnerOnly"), message) == b'{"label":"x"}'


def test_response_body_of_an_unset_message_field_is_an_empty_object() -> None:
    assert encode_response(binding("GetInnerOnly"), Kitchen(name="k")) == b"{}"


def test_response_body_of_a_repeated_field_is_an_array() -> None:
    assert encode_response(binding("GetTagsOnly"), Kitchen(tags=["a", "b"])) == b'["a","b"]'


def test_response_body_of_an_empty_repeated_field_is_an_empty_array() -> None:
    assert encode_response(binding("GetTagsOnly"), Kitchen()) == b"[]"


# --- NDJSON streams -------------------------------------------------------------------------------


def test_the_stream_content_type_is_ndjson() -> None:
    assert NDJSON_CONTENT_TYPE == "application/x-ndjson"


def test_a_stream_message_is_one_result_line() -> None:
    line = encode_stream_result(binding("StreamKitchens"), Kitchen(name="k"))
    assert line == b'{"result":{"name":"k"}}\n'


def test_a_stream_message_honours_response_body() -> None:
    line = encode_stream_result(binding("StreamInners"), Kitchen(inner=Inner(label="x")))
    assert line == b'{"result":{"label":"x"}}\n'


def test_a_stream_message_with_a_newline_in_a_value_stays_on_one_line() -> None:
    line = encode_stream_result(binding("StreamKitchens"), Kitchen(name="a\nb"))
    assert line.count(b"\n") == 1
    assert json.loads(line) == {"result": {"name": "a\nb"}}


def test_a_failed_stream_ends_with_an_error_line() -> None:
    assert encode_stream_error(Code.NOT_FOUND, "gone") == (
        b'{"error":{"code":5,"message":"gone","details":[]}}\n'
    )


# --- errors ---------------------------------------------------------------------------------------

STATUS_TABLE = [
    (Code.CANCELED, 1, 499),
    (Code.UNKNOWN, 2, 500),
    (Code.INVALID_ARGUMENT, 3, 400),
    (Code.DEADLINE_EXCEEDED, 4, 504),
    (Code.NOT_FOUND, 5, 404),
    (Code.ALREADY_EXISTS, 6, 409),
    (Code.PERMISSION_DENIED, 7, 403),
    (Code.RESOURCE_EXHAUSTED, 8, 429),
    (Code.FAILED_PRECONDITION, 9, 400),
    (Code.ABORTED, 10, 409),
    (Code.OUT_OF_RANGE, 11, 400),
    (Code.UNIMPLEMENTED, 12, 501),
    (Code.INTERNAL, 13, 500),
    (Code.UNAVAILABLE, 14, 503),
    (Code.DATA_LOSS, 15, 500),
    (Code.UNAUTHENTICATED, 16, 401),
]


@pytest.mark.parametrize(("code", "number", "status"), STATUS_TABLE)
def test_every_code_has_its_grpc_number_and_http_status(
    code: Code, number: int, status: int
) -> None:
    assert grpc_code_number(code) == number
    assert http_status_for(code) == status


def test_the_status_table_covers_every_code() -> None:
    assert {code for code, _, _ in STATUS_TABLE} == set(Code)


@pytest.mark.parametrize(("code", "number", "status"), STATUS_TABLE)
def test_an_error_is_a_google_rpc_status_body(code: Code, number: int, status: int) -> None:
    http_status, body = encode_error(code, "why")
    assert http_status == status
    assert json.loads(body) == {"code": number, "message": "why", "details": []}
