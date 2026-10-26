"""The route table: annotated methods only, matched by verb and specificity; bad rules refused."""

from __future__ import annotations

from functools import cache

import pytest

from surmap.rpc.http_rule.routes import HttpRuleConfigError, HttpRuleRouter
from tests.rpc.unit.http_rule.fixture import FIXTURE_RULES, Rule, build_service, fixture, rule

SERVICE = fixture()


@cache
def router() -> HttpRuleRouter:
    return HttpRuleRouter.from_services([SERVICE.service])


def routed(http_method: str, path: str) -> tuple[str, dict[str, str]]:
    match = router().match(http_method, path)
    assert match is not None, f"{http_method} {path} did not route"
    return match.binding.method.name, match.path_params


# --- exposure -------------------------------------------------------------------------------------


def test_only_annotated_methods_get_bindings() -> None:
    annotated = {spec.name for spec in FIXTURE_RULES if spec.rule is not None}
    assert {binding.method.name for binding in router().bindings} == annotated


def test_an_unannotated_method_has_no_route_under_any_path() -> None:
    names = {binding.method.name for binding in router().bindings}
    assert "Unannotated" not in names
    assert "Chat" not in names
    assert router().match("POST", f"/{SERVICE.service.full_name}/Unannotated") is None


def test_additional_bindings_route_to_the_same_method() -> None:
    assert routed("GET", "/v1/kitchens/k1/alias") == ("GetAliased", {"name": "k1"})
    assert routed("GET", "/v1/aliases/k1") == ("GetAliased", {"name": "k1"})
    assert sum(binding.method.name == "GetAliased" for binding in router().bindings) == 2


# --- matching -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("http_method", "path", "method_name", "params"),
    [
        ("GET", "/v1/kitchens/k1", "GetKitchen", {"name": "k1"}),
        ("PUT", "/v1/kitchens/k1", "PutKitchen", {"name": "k1"}),
        ("DELETE", "/v1/kitchens/k1", "DeleteKitchen", {"name": "k1"}),
        ("GET", "/v1/kitchens", "ListKitchens", {}),
        ("POST", "/v1/kitchens", "CreateKitchen", {}),
        ("SEARCH", "/v1/kitchens", "SearchKitchens", {}),
        ("GET", "/v1/inner/x/kitchen", "GetByInner", {"inner.label": "x"}),
        ("PATCH", "/v1/kitchens/k1/inner", "UpdateInner", {"name": "k1"}),
        ("GET", "/v1/kitchens/k1/inner", "GetInnerOnly", {"name": "k1"}),
        ("GET", "/v1/kitchens/k1/tags", "GetTagsOnly", {"name": "k1"}),
        ("POST", "/v1/kitchens/k1/tags", "UpdateTags", {"name": "k1"}),
        ("POST", "/v1/kitchens/k1:cancel", "CancelKitchen", {"name": "k1"}),
        ("POST", "/v1/kitchens:stream", "StreamKitchens", {}),
        (
            "GET",
            "/v1/projects/p1/kitchens/k1",
            "GetResource",
            {"resource_name": "projects/p1/kitchens/k1"},
        ),
        ("GET", "/v1/files/a/b/c.txt", "GetFile", {"name": "a/b/c.txt"}),
    ],
)
def test_a_request_routes_to_the_rule_its_verb_and_path_match(
    http_method: str, path: str, method_name: str, params: dict[str, str]
) -> None:
    assert routed(http_method, path) == (method_name, params)


def test_a_verb_route_is_preferred_over_a_variable_that_would_swallow_the_colon() -> None:
    assert routed("POST", "/v1/kitchens:stream")[0] == "StreamKitchens"


def test_an_unknown_path_does_not_route() -> None:
    assert router().match("GET", "/v2/kitchens/k1") is None
    assert router().allowed_methods("/v2/kitchens/k1") == frozenset()


def test_a_known_path_with_the_wrong_verb_reports_the_allowed_verbs() -> None:
    assert router().match("POST", "/v1/kitchens/k1") is None
    assert router().allowed_methods("/v1/kitchens/k1") == frozenset({"GET", "PUT", "DELETE"})


def test_a_binding_carries_its_rule_and_message_classes() -> None:
    match = router().match("PATCH", "/v1/kitchens/k1/inner")
    assert match is not None
    assert (match.binding.http_method, match.binding.response_body) == ("PATCH", "")
    assert match.binding.request_class.DESCRIPTOR.name == "Kitchen"
    assert match.binding.response_class.DESCRIPTOR.name == "Kitchen"
    assert match.binding.server_streaming is False
    streaming = router().match("POST", "/v1/kitchens:stream")
    assert streaming is not None and streaming.binding.server_streaming is True


# --- rules a router refuses -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rules", "named"),
    [
        ([Rule("Upload", rule(post="/v1/up", body="*"), client_streaming=True)], "Upload"),
        ([Rule("Bad", rule(get="v1/no-slash"))], "Bad"),
        ([Rule("Bad", rule(get="/v1/{nope}"))], "nope"),
        ([Rule("Bad", rule(get="/v1/{tags}"))], "tags"),
        ([Rule("Bad", rule(get="/v1/{inner}"))], "inner"),
        ([Rule("Bad", rule(get="/v1/{labels}"))], "labels"),
        ([Rule("Bad", rule(get="/v1/{inners.label}"))], "inners"),
        ([Rule("Bad", rule(post="/v1/x", body="nope"))], "body"),
        ([Rule("Bad", rule(post="/v1/x", body="inner.label"))], "body"),
        ([Rule("Bad", rule(patch="/v1/{name}", body="name"))], "body"),
        ([Rule("Bad", rule(patch="/v1/kitchens/{name}/inner", body="inner"))], "body"),
        ([Rule("Bad", rule(get="/v1/x", response_body="nope"))], "nope"),
        ([Rule("Bad", rule(get="/v1/x", body="*"))], "body"),
        ([Rule("Bad", rule(body="*"))], "body"),
        (
            [
                Rule(
                    "Bad",
                    rule(
                        get="/v1/x", additional=[rule(get="/v1/y", additional=[rule(get="/v1/z")])]
                    ),
                )
            ],
            "Bad",
        ),
        (
            [
                Rule("First", rule(get="/v1/things/{name}")),
                Rule("Second", rule(get="/v1/things/{resource_name}")),
            ],
            "Second",
        ),
    ],
)
def test_a_rule_that_cannot_be_served_is_refused_naming_the_cause(
    rules: list[Rule], named: str
) -> None:
    with pytest.raises(HttpRuleConfigError) as error:
        HttpRuleRouter.from_services([build_service(rules).service])
    assert named in str(error.value)


@pytest.mark.parametrize(
    "rules",
    [
        [Rule("A", rule(get="/v1/things/{name}")), Rule("B", rule(delete="/v1/things/{name}"))],
        [Rule("A", rule(get="/v1/things/{name}")), Rule("B", rule(get="/v1/things/{name}:check"))],
        [Rule("A", rule(get="/v1/things/{name}")), Rule("B", rule(get="/v1/things/list"))],
    ],
)
def test_rules_that_differ_in_verb_or_shape_do_not_conflict(rules: list[Rule]) -> None:
    router = HttpRuleRouter.from_services([build_service(rules).service])
    assert len(router.bindings) == 2


def test_a_router_spans_several_services() -> None:
    first = build_service([Rule("A", rule(get="/v1/a"))], service_name="First")
    second = build_service([Rule("B", rule(get="/v1/b"))], service_name="Second")
    router = HttpRuleRouter.from_services([first.service, second.service])
    assert {b.method.full_name.split(".")[-2] for b in router.bindings} == {"First", "Second"}
