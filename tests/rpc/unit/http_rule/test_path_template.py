"""HttpRule path templates — grammar, matching and percent-decoding, per `google.api.HttpRule`."""

from __future__ import annotations

import pytest

from surmap.rpc.http_rule.path_template import (
    PathTemplate,
    TemplateSyntaxError,
)

# --- grammar --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "variables", "verb"),
    [
        ("/v1/kitchens", [], None),
        ("/v1/kitchens/{name}", [(("name",), False)], None),
        ("/v1/kitchens/{name=*}", [(("name",), False)], None),
        ("/v1/inner/{inner.label}/kitchen", [(("inner", "label"), False)], None),
        ("/v1/{resource_name=projects/*/kitchens/*}", [(("resource_name",), True)], None),
        ("/v1/files/{name=**}", [(("name",), True)], None),
        ("/v1/kitchens/{name}:cancel", [(("name",), False)], "cancel"),
        ("/v1/kitchens:search", [], "search"),
        ("/v1/*/kitchens", [], None),
        ("/v1/{a}/{b}", [(("a",), False), (("b",), False)], None),
    ],
)
def test_a_valid_template_parses_into_its_variables_and_verb(
    template: str, variables: list[tuple[tuple[str, ...], bool]], verb: str | None
) -> None:
    parsed = PathTemplate.parse(template)
    assert [(v.field_path, v.multi_segment) for v in parsed.variables] == variables
    assert parsed.verb == verb


@pytest.mark.parametrize(
    "template",
    [
        "",
        "v1/kitchens",
        "/v1//kitchens",
        "/v1/kitchens/",
        "/v1/{name",
        "/v1/name}",
        "/v1/{a={b}}",
        "/v1/**/kitchens",
        "/v1/{a=**}/kitchens",
        "/v1/{}",
        "/v1/{1name}",
        "/v1/{a..b}",
        "/v1/{a=}",
        "/v1/kitchens:",
        "/v1/{a}/{a}",
        "/v1/{a=projects/**/x}",
    ],
)
def test_an_invalid_template_is_refused(template: str) -> None:
    with pytest.raises(TemplateSyntaxError):
        PathTemplate.parse(template)


# --- matching -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "path", "expected"),
    [
        ("/v1/kitchens", "/v1/kitchens", {}),
        ("/v1/kitchens/{name}", "/v1/kitchens/abc", {"name": "abc"}),
        ("/v1/kitchens/{name=*}", "/v1/kitchens/abc", {"name": "abc"}),
        ("/v1/inner/{inner.label}/kitchen", "/v1/inner/x/kitchen", {"inner.label": "x"}),
        ("/v1/*/kitchens", "/v1/anything/kitchens", {}),
        ("/v1/{a}/{b}", "/v1/one/two", {"a": "one", "b": "two"}),
        (
            "/v1/{resource_name=projects/*/kitchens/*}",
            "/v1/projects/p1/kitchens/k1",
            {"resource_name": "projects/p1/kitchens/k1"},
        ),
        ("/v1/files/{name=**}", "/v1/files/a/b/c.txt", {"name": "a/b/c.txt"}),
        ("/v1/files/{name=**}", "/v1/files/a", {"name": "a"}),
        ("/v1/files/{name=**}", "/v1/files", {"name": ""}),
        ("/v1/kitchens/{name}:cancel", "/v1/kitchens/k1:cancel", {"name": "k1"}),
        ("/v1/kitchens:search", "/v1/kitchens:search", {}),
    ],
)
def test_a_matching_path_binds_every_variable(
    template: str, path: str, expected: dict[str, str]
) -> None:
    assert PathTemplate.parse(template).match(path) == expected


@pytest.mark.parametrize(
    ("template", "path"),
    [
        ("/v1/kitchens/{name}", "/v1/kitchens"),
        ("/v1/kitchens/{name}", "/v1/kitchens/a/b"),
        ("/v1/kitchens/{name}", "/v1/kitchens/"),
        ("/v1/kitchens/{name}", "/v1/kitchens/abc/"),
        ("/v1/kitchens/{name}", "/V1/kitchens/abc"),
        ("/v1/kitchens/{name}", "v1/kitchens/abc"),
        ("/v1/kitchens", "/v1/kitchens/extra"),
        ("/v1/{resource_name=projects/*/kitchens/*}", "/v1/projects/p1/kitchens"),
        ("/v1/{resource_name=projects/*/kitchens/*}", "/v1/folders/p1/kitchens/k1"),
        ("/v1/kitchens/{name}:cancel", "/v1/kitchens/k1"),
        ("/v1/kitchens/{name}:cancel", "/v1/kitchens/k1:other"),
        ("/v1/kitchens:search", "/v1/kitchens"),
    ],
)
def test_a_path_that_does_not_fit_the_template_does_not_match(template: str, path: str) -> None:
    assert PathTemplate.parse(template).match(path) is None


def test_without_a_verb_a_colon_is_part_of_the_variable() -> None:
    assert PathTemplate.parse("/v1/kitchens/{name}").match("/v1/kitchens/a:b") == {"name": "a:b"}


# --- percent-decoding -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "decoded"),
    [
        ("a%20b", "a b"),
        ("a%2Fb", "a/b"),
        ("a%2fb", "a/b"),
        ("caf%C3%A9", "café"),
        ("a+b", "a+b"),
        ("a%3Ab", "a:b"),
    ],
)
def test_a_single_segment_variable_is_fully_decoded(raw: str, decoded: str) -> None:
    assert PathTemplate.parse("/v1/kitchens/{name}").match(f"/v1/kitchens/{raw}") == {
        "name": decoded
    }


@pytest.mark.parametrize(
    ("path", "decoded"),
    [
        ("/v1/files/a%2Fb/c", "a%2Fb/c"),
        ("/v1/files/a%2fb/c", "a%2fb/c"),
        ("/v1/files/a%20b/c", "a b/c"),
    ],
)
def test_a_multi_segment_variable_keeps_encoded_slashes(path: str, decoded: str) -> None:
    assert PathTemplate.parse("/v1/files/{name=**}").match(path) == {"name": decoded}


def test_fully_decode_reserved_expansion_decodes_slashes_in_a_multi_segment_variable() -> None:
    template = PathTemplate.parse(
        "/v1/files/{name=**}", fully_decode_reserved_expansion=True
    )
    assert template.match("/v1/files/a%2Fb/c") == {"name": "a/b/c"}


def test_a_multi_segment_pattern_variable_keeps_encoded_slashes() -> None:
    template = PathTemplate.parse("/v1/{resource_name=projects/*/kitchens/*}")
    assert template.match("/v1/projects/p%2F1/kitchens/k%201") == {
        "resource_name": "projects/p%2F1/kitchens/k 1"
    }


def test_a_literal_segment_matches_its_percent_encoded_form() -> None:
    assert PathTemplate.parse("/v1/kitchens").match("/v1/kitch%65ns") == {}


# --- shape and specificity ------------------------------------------------------------------------


def test_templates_that_differ_only_in_variable_names_share_a_shape() -> None:
    assert (
        PathTemplate.parse("/v1/kitchens/{name}").shape()
        == PathTemplate.parse("/v1/kitchens/{resource_name}").shape()
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("/v1/kitchens/{name}", "/v1/kitchens/{name}:cancel"),
        ("/v1/kitchens/{name}", "/v1/kitchens/list"),
        ("/v1/kitchens/{name}", "/v1/kitchens/{name=**}"),
        ("/v1/kitchens/{name}", "/v1/ovens/{name}"),
    ],
)
def test_templates_that_match_different_paths_have_different_shapes(left: str, right: str) -> None:
    assert PathTemplate.parse(left).shape() != PathTemplate.parse(right).shape()


def test_a_literal_segment_is_more_specific_than_a_variable() -> None:
    literal = PathTemplate.parse("/v1/kitchens/list")
    variable = PathTemplate.parse("/v1/kitchens/{name}")
    assert literal.specificity() > variable.specificity()


def test_a_double_wildcard_is_the_least_specific() -> None:
    single = PathTemplate.parse("/v1/files/{name}")
    double = PathTemplate.parse("/v1/files/{name=**}")
    assert single.specificity() > double.specificity()
