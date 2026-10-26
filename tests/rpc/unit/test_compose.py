"""`compose_service` — exact coverage, refused by name; every method kind becomes its endpoint."""

from __future__ import annotations

from typing import Any

import pytest
from connectrpc.server import ConnectASGIApplication

from surmap.rpc.compose import Brick, CompositionError, compose_service
from tests.rpc.echo_service import echo_service


async def _handler(request: Any, ctx: Any) -> Any:
    return request


def _all_methods() -> dict[str, Any]:
    return dict.fromkeys(("Unary", "ServerStream", "ClientStream", "Bidi"), _handler)


def test_bricks_covering_every_method_once_compose_into_an_application() -> None:
    service = echo_service()
    first = Brick(methods={"Unary": _handler, "ServerStream": _handler})
    second = Brick(methods={"ClientStream": _handler, "Bidi": _handler})

    app = compose_service(service, first, second)

    assert isinstance(app, ConnectASGIApplication)
    assert app.path == f"/{service.full_name}"


def test_a_method_no_brick_claims_is_refused_by_name() -> None:
    service = echo_service()
    with pytest.raises(CompositionError) as error:
        compose_service(service, Brick(methods={"Unary": _handler, "Bidi": _handler}))
    assert error.value.unimplemented == ("ClientStream", "ServerStream")
    assert "ClientStream" in str(error.value) and "ServerStream" in str(error.value)


def test_a_method_two_bricks_claim_is_refused_by_name() -> None:
    service = echo_service()
    with pytest.raises(CompositionError) as error:
        compose_service(service, Brick(methods=_all_methods()), Brick(methods={"Unary": _handler}))
    assert error.value.duplicated == ("Unary",)
    assert "Unary" in str(error.value)


def test_a_name_the_service_does_not_have_is_refused() -> None:
    service = echo_service()
    with pytest.raises(CompositionError) as error:
        compose_service(service, Brick(methods={**_all_methods(), "Typo": _handler}))
    assert error.value.unknown == ("Typo",)
    assert "Typo" in str(error.value)


def test_every_problem_is_reported_in_one_error() -> None:
    service = echo_service()
    with pytest.raises(CompositionError) as error:
        compose_service(
            service,
            Brick(methods={"Unary": _handler, "Typo": _handler}),
            Brick(methods={"Unary": _handler}),
        )
    assert error.value.unimplemented == ("Bidi", "ClientStream", "ServerStream")
    assert error.value.duplicated == ("Unary",)
    assert error.value.unknown == ("Typo",)


def test_the_error_names_the_service() -> None:
    service = echo_service("Named")
    with pytest.raises(CompositionError) as error:
        compose_service(service)
    assert error.value.service == service.full_name
    assert service.full_name in str(error.value)
