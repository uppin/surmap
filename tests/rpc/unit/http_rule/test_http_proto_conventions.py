"""HTTP rule conventions on the route table builder (fixture services)."""

from __future__ import annotations

import pytest

from surmap.rpc.http_rule.routes import HttpRuleConfigError, HttpRuleRouter
from tests.rpc.unit.http_rule.fixture import Rule, build_service, rule


@pytest.mark.parametrize(
    "body_value",
    ["*", "inner", "tags", "name"],
)
def test_the_route_table_refuses_any_http_body_option(body_value: str) -> None:
    with pytest.raises(HttpRuleConfigError) as error:
        HttpRuleRouter.from_services(
            [build_service([Rule("Bad", rule(post="/v1/kitchens", body=body_value))]).service]
        )
    assert "body" in str(error.value).lower()
