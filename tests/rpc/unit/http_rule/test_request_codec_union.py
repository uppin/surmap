"""REST request union: JSON body, query, path, and GET `.r` base64url, in that precedence."""

from __future__ import annotations

import base64
import json
from typing import Any

from google.protobuf import wrappers_pb2

from tests.rpc.unit.http_rule.test_request_codec import Inner, Kitchen, decode, refused


def _dot_r(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# --- merge: body + query + path ---------------------------------------------------------------


def test_a_json_body_carries_fields_that_are_not_in_path_or_query() -> None:
    body = {
        "name": "k",
        "inner": {"label": "x", "count": 2},
        "tags": ["a", "b"],
    }
    assert decode("CreateKitchen", body=body) == Kitchen(
        name="k", inner=Inner(label="x", count=2), tags=["a", "b"]
    )


def test_a_json_body_combines_with_query_parameters() -> None:
    assert decode("CreateKitchen", query="i32=3&color=GREEN", body={"name": "k"}) == Kitchen(
        name="k", i32=3, color=2
    )


def test_a_json_body_combines_with_path_variables() -> None:
    assert decode("PutKitchen", path={"name": "k1"}, body={"i32": 4}) == Kitchen(name="k1", i32=4)


def test_path_and_query_win_over_the_same_field_in_a_json_body() -> None:
    decoded = decode(
        "PutKitchen",
        path={"name": "from-path"},
        query="i32=9",
        body={"name": "from-body", "i32": 1},
    )
    assert decoded == Kitchen(name="from-path", i32=9)


def test_a_query_parameter_wins_over_the_same_field_in_the_path() -> None:
    decoded = decode("GetKitchen", path={"name": "from-path"}, query="name=from-query")
    assert decoded.name == "from-query"


def test_a_query_parameter_wins_over_the_same_field_in_a_json_body_on_get() -> None:
    decoded = decode("GetKitchen", path={"name": "k"}, query="i32=5", body={"i32": 1})
    assert decoded == Kitchen(name="k", i32=5)


def test_a_repeated_message_field_may_ride_the_json_body() -> None:
    assert decode(
        "UpdateTags",
        path={"name": "k"},
        body={"tags": ["a", "b"]},
    ) == Kitchen(name="k", tags=["a", "b"])


def test_a_nested_field_may_come_from_body_while_siblings_come_from_query() -> None:
    decoded = decode(
        "UpdateInner",
        path={"name": "k"},
        query="tags=a",
        body={"inner": {"label": "x", "count": 2}},
    )
    assert decoded == Kitchen(name="k", inner=Inner(label="x", count=2), tags=["a"])


def test_query_and_body_may_set_dotted_paths_into_a_nested_message() -> None:
    decoded = decode(
        "ListKitchens",
        query="inner.label=x",
        body={"inner": {"count": 2}},
    )
    assert decoded.inner.label == "x"
    assert decoded.inner.count == 2


# --- GET `.r` (base64url JSON) ------------------------------------------------------------------


def test_get_dot_r_merges_json_over_query_and_path() -> None:
    dot_r = _dot_r({"i32": 7, "maybeName": "w"})
    decoded = decode("ListKitchens", query=f"i32=1&.r={dot_r}")
    assert decoded.i32 == 7
    assert decoded.maybe_name == wrappers_pb2.StringValue(value="w")


def test_dot_r_on_a_non_get_route_is_refused() -> None:
    dot_r = _dot_r({"i32": 1})
    refused("CreateKitchen", query=f".r={dot_r}", body={"name": "k"})
