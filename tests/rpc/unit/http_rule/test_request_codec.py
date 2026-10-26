"""Decoding a REST request into the request message — path variables, query parameters, body.

Bindings are built straight from the fixture's rules, so these tests exercise the codec alone.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from connectrpc.code import Code
from google.api import annotations_pb2
from google.protobuf import duration_pb2, timestamp_pb2, wrappers_pb2
from google.protobuf.message import Message

from surmap.rpc.http_rule.codec import HttpRuleError, decode_request
from surmap.rpc.http_rule.path_template import PathTemplate
from surmap.rpc.http_rule.routes import HttpBinding
from tests.rpc.unit.http_rule.fixture import BuiltService, fixture

SERVICE = fixture()
Kitchen = SERVICE.message("Kitchen")
Inner = SERVICE.message("Inner")
RED, GREEN = 1, 2


def binding(method_name: str, service: BuiltService = SERVICE) -> HttpBinding:
    method = service.service.methods_by_name[method_name]
    rule = method.GetOptions().Extensions[annotations_pb2.http]
    kind = rule.WhichOneof("pattern")
    http_method, path = (
        (rule.custom.kind, rule.custom.path)
        if kind == "custom"
        else (kind.upper(), getattr(rule, kind))
    )
    return HttpBinding(
        method=method,
        http_method=http_method,
        template=PathTemplate(path),
        body=rule.body,
        response_body=rule.response_body,
    )


def decode(
    method_name: str,
    *,
    path: dict[str, str] | None = None,
    query: str = "",
    body: bytes | dict[str, Any] | list[Any] = b"",
) -> Any:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return decode_request(binding(method_name), path_params=path or {}, query=query, body=raw)


def refused(method_name: str, **kwargs: Any) -> HttpRuleError:
    with pytest.raises(HttpRuleError) as error:
        decode(method_name, **kwargs)
    assert error.value.code == Code.INVALID_ARGUMENT
    return error.value


# --- path variables -------------------------------------------------------------------------------


def test_a_path_variable_sets_its_field() -> None:
    assert decode("GetKitchen", path={"name": "k1"}) == Kitchen(name="k1")


def test_a_nested_path_variable_sets_the_nested_field() -> None:
    assert decode("GetByInner", path={"inner.label": "x"}) == Kitchen(inner=Inner(label="x"))


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"i64": "-9007199254740993"}, Kitchen(i64=-9007199254740993)),
        ({"u64": "18446744073709551615"}, Kitchen(u64=18446744073709551615)),
        ({"flag": "true"}, Kitchen(flag=True)),
        ({"color": "GREEN"}, Kitchen(color=GREEN)),
        ({"maybe_name": "w"}, Kitchen(maybe_name=wrappers_pb2.StringValue(value="w"))),
        ({"maybe_i64": "7"}, Kitchen(maybe_i64=wrappers_pb2.Int64Value(value=7))),
    ],
)
def test_a_path_variable_is_converted_to_its_field_type(
    params: dict[str, str], expected: Message
) -> None:
    assert decode("GetKitchen", path={"name": "", **params}) == expected


def test_a_path_variable_that_does_not_convert_is_refused() -> None:
    error = refused("GetKitchen", path={"name": "k", "i32": "abc"})
    assert "i32" in error.message


def test_path_and_query_win_over_the_same_fields_in_a_json_body() -> None:
    decoded = decode("PutKitchen", path={"name": "k1"}, body={"name": "other", "i32": 1})
    assert decoded.name == "k1"
    assert decoded.i32 == 1


# --- query parameters: every leaf type ------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("i32=-5", Kitchen(i32=-5)),
        ("i64=-9007199254740993", Kitchen(i64=-9007199254740993)),
        ("u32=4294967295", Kitchen(u32=4294967295)),
        ("u64=18446744073709551615", Kitchen(u64=18446744073709551615)),
        ("s32=-3", Kitchen(s32=-3)),
        ("f64=10", Kitchen(f64=10)),
        ("flag=true", Kitchen(flag=True)),
        ("flag=false", Kitchen(flag=False)),
        ("ratio=1.5", Kitchen(ratio=1.5)),
        ("ratio=-Infinity", Kitchen(ratio=-math.inf)),
        ("score=0.25", Kitchen(score=0.25)),
        ("blob=aGk%3D", Kitchen(blob=b"hi")),
        ("blob=_-8", Kitchen(blob=b"\xff\xef")),
        ("color=GREEN", Kitchen(color=GREEN)),
        ("color=1", Kitchen(color=RED)),
        ("name=", Kitchen(name="")),
        ("name=a%20b", Kitchen(name="a b")),
        ("name=a+b", Kitchen(name="a b")),
        ("name=caf%C3%A9", Kitchen(name="café")),
        ("choice_text=x", Kitchen(choice_text="x")),
    ],
)
def test_a_scalar_query_parameter_is_decoded_to_its_type(query: str, expected: Message) -> None:
    assert decode("ListKitchens", query=query) == expected


def test_a_nan_query_parameter_decodes_to_nan() -> None:
    assert math.isnan(decode("ListKitchens", query="ratio=NaN").ratio)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("maybe_name=w", Kitchen(maybe_name=wrappers_pb2.StringValue(value="w"))),
        ("maybe_name=", Kitchen(maybe_name=wrappers_pb2.StringValue(value=""))),
        ("maybe_i64=-5", Kitchen(maybe_i64=wrappers_pb2.Int64Value(value=-5))),
        ("maybe_i32=6", Kitchen(maybe_i32=wrappers_pb2.Int32Value(value=6))),
        ("maybe_flag=false", Kitchen(maybe_flag=wrappers_pb2.BoolValue(value=False))),
        ("maybe_ratio=2.5", Kitchen(maybe_ratio=wrappers_pb2.DoubleValue(value=2.5))),
        ("maybe_blob=aGk%3D", Kitchen(maybe_blob=wrappers_pb2.BytesValue(value=b"hi"))),
    ],
)
def test_a_wrapper_query_parameter_sets_the_wrapper(query: str, expected: Message) -> None:
    decoded = decode("ListKitchens", query=query)
    assert decoded == expected
    field = query.split("=")[0]
    assert decoded.HasField(field)


def test_well_known_type_query_parameters_are_parsed_from_their_json_form() -> None:
    decoded = decode("ListKitchens", query="at=2026-10-01T12:00:00Z&ttl=1.5s&mask=a,b.c")
    assert decoded.at == timestamp_pb2.Timestamp(seconds=1790856000)
    assert decoded.ttl == duration_pb2.Duration(seconds=1, nanos=500_000_000)
    assert list(decoded.mask.paths) == ["a", "b.c"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("tags=a&tags=b", Kitchen(tags=["a", "b"])),
        ("tags=solo", Kitchen(tags=["solo"])),
        ("ids=1&ids=-2", Kitchen(ids=[1, -2])),
        ("colors=RED&colors=2", Kitchen(colors=[RED, GREEN])),
    ],
)
def test_a_repeated_query_parameter_collects_every_value_in_order(
    query: str, expected: Message
) -> None:
    assert decode("ListKitchens", query=query) == expected


@pytest.mark.parametrize(
    "query",
    ["inner.label=x&inner.count=3", "inner.label=x&inner.count=3&inner.color=RED"],
)
def test_a_dotted_query_parameter_reaches_into_a_singular_message(query: str) -> None:
    decoded = decode("ListKitchens", query=query)
    assert decoded.inner.label == "x"
    assert decoded.inner.count == 3


@pytest.mark.parametrize("query", ["snake_case_field=v", "snakeCaseField=v"])
def test_a_query_parameter_may_use_the_proto_or_the_json_name(query: str) -> None:
    assert decode("ListKitchens", query=query) == Kitchen(snake_case_field="v")


def test_query_parameters_combine_with_path_variables() -> None:
    decoded = decode("GetKitchen", path={"name": "k"}, query="i32=3&tags=a")
    assert decoded == Kitchen(name="k", i32=3, tags=["a"])


# --- query parameters: refusals -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "named"),
    [
        ("nope=1", "nope"),
        ("inner.nope=1", "inner.nope"),
        ("inner=x", "inner"),
        ("inners.label=x", "inners.label"),
        ("labels=x", "labels"),
        ("labels.k=v", "labels.k"),
        ("name=a&name=b", "name"),
        ("i32=1.5", "i32"),
        ("i32=2147483648", "i32"),
        ("u32=-1", "u32"),
        ("flag=yes", "flag"),
        ("color=PURPLE", "color"),
        ("at=yesterday", "at"),
        ("ttl=forever", "ttl"),
        ("maybe_flag=maybe", "maybe_flag"),
    ],
)
def test_an_invalid_query_parameter_is_refused_by_name(query: str, named: str) -> None:
    error = refused("ListKitchens", query=query)
    assert named in error.message


def test_a_query_parameter_wins_over_the_same_path_variable() -> None:
    assert decode("GetKitchen", path={"name": "k"}, query="name=other").name == "other"


# --- JSON body (REST union with query and path) ----------------------------------------------


def test_a_json_body_decodes_the_whole_message() -> None:
    body = {
        "name": "k",
        "i64": "9007199254740993",
        "color": "GREEN",
        "inner": {"label": "x", "count": 2},
        "tags": ["a", "b"],
        "labels": {"shelf": "top"},
        "maybeName": "w",
        "at": "2026-10-01T12:00:00Z",
        "snakeCaseField": "camel",
    }
    assert decode("CreateKitchen", body=body) == Kitchen(
        name="k",
        i64=9007199254740993,
        color=GREEN,
        inner=Inner(label="x", count=2),
        tags=["a", "b"],
        labels={"shelf": "top"},
        maybe_name=wrappers_pb2.StringValue(value="w"),
        at=timestamp_pb2.Timestamp(seconds=1790856000),
        snake_case_field="camel",
    )


def test_a_json_body_accepts_proto_field_names() -> None:
    assert decode("CreateKitchen", body={"snake_case_field": "proto"}) == Kitchen(
        snake_case_field="proto"
    )


def test_a_json_body_accepts_enum_numbers() -> None:
    assert decode("CreateKitchen", body={"color": 2, "colors": [1, "GREEN"]}) == Kitchen(
        color=GREEN, colors=[RED, GREEN]
    )


def test_an_empty_json_body_is_an_empty_message() -> None:
    assert decode("CreateKitchen", body=b"") == Kitchen()


def test_a_post_route_decodes_path_and_body_together() -> None:
    assert decode("CancelKitchen", path={"name": "k"}, body={"i32": 4}) == Kitchen(name="k", i32=4)


@pytest.mark.parametrize(
    ("method_name", "body", "named"),
    [
        ("CreateKitchen", {"nope": 1}, "nope"),
        ("CreateKitchen", {"inner": {"nope": 1}}, "nope"),
        ("CreateKitchen", {"i32": "many"}, "i32"),
        ("UpdateInner", {"nope": 1}, "nope"),
    ],
)
def test_an_invalid_json_body_is_refused_naming_the_field(
    method_name: str, body: dict[str, Any], named: str
) -> None:
    path = {"name": "k"} if method_name == "UpdateInner" else None
    error = refused(method_name, path=path, body=body)
    assert named in error.message


@pytest.mark.parametrize("body", [b"{not json", b"\xff\xfe"])
def test_a_non_json_body_is_refused(body: bytes) -> None:
    refused("CreateKitchen", body=body)


def test_a_json_array_body_is_refused() -> None:
    refused("CreateKitchen", body=[1, 2])


def test_a_get_route_accepts_a_json_body_for_fields_not_in_path_or_query() -> None:
    assert decode("GetKitchen", path={"name": "k"}, body={"i32": 1}) == Kitchen(name="k", i32=1)


def test_a_whitespace_only_body_counts_as_no_body() -> None:
    assert decode("GetKitchen", path={"name": "k"}, body=b"  \n") == Kitchen(name="k")
