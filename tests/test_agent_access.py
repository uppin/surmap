"""The agent's access gate: a shared pass code exchanged for a signed, expiring session token."""

from __future__ import annotations

from surmap.agent.server.access import SESSION_COOKIE, AccessGate, session_token
from tests.agent_station_fakes import FakeClock

CODE = "correct-horse-battery-staple"
TWELVE_HOURS_S = 12 * 3600


def a_gate(clock: FakeClock | None = None) -> AccessGate:
    return AccessGate(CODE, clock=clock or FakeClock(), ttl_s=TWELVE_HOURS_S)


def test_the_pass_code_is_exchanged_for_a_token_the_gate_allows() -> None:
    # Given the agent's gate
    gate = a_gate()

    # When the right code signs in
    token = gate.issue(CODE)

    # Then a token comes back, and the gate lets it through
    assert token is not None
    assert gate.allows(token)


def test_a_wrong_pass_code_gets_no_token() -> None:
    # Given the agent's gate
    # When a wrong code signs in
    # Then no token is issued
    assert a_gate().issue("correct-horse-battery") is None


def test_a_token_stops_working_once_it_expires() -> None:
    # Given a token issued now
    clock = FakeClock()
    gate = a_gate(clock)
    token = gate.issue(CODE)
    assert token is not None

    # When twelve hours pass
    clock.advance(TWELVE_HOURS_S)

    # Then the gate refuses it
    assert not gate.allows(token)


def test_a_token_with_a_pushed_back_expiry_is_refused() -> None:
    # Given a real token whose expiry part is edited to a later time
    gate = a_gate()
    token = gate.issue(CODE)
    assert token is not None
    expiry, signature = token.split(".")
    forged = f"{int(expiry) + 3600}.{signature}"

    # Then its signature no longer matches
    assert not gate.allows(forged)


def test_changing_the_pass_code_revokes_every_token() -> None:
    # Given a token from the old code, and the agent restarted with a new one
    clock = FakeClock()
    old = a_gate(clock).issue(CODE)
    assert old is not None
    new_gate = AccessGate("a-brand-new-code", clock=clock, ttl_s=TWELVE_HOURS_S)

    # Then the old token is refused
    assert not new_gate.allows(old)


def test_a_token_from_the_same_code_survives_an_agent_restart() -> None:
    # Given a token, and a fresh gate built from the same code (a new container)
    clock = FakeClock()
    token = a_gate(clock).issue(CODE)
    assert token is not None

    # Then the new gate still allows it
    assert a_gate(clock).allows(token)


def test_garbage_is_not_a_token() -> None:
    # Given the agent's gate
    gate = a_gate()

    # Then malformed values are refused, not raised on
    assert not gate.allows("")
    assert not gate.allows("not-a-token")
    assert not gate.allows("soon.deadbeef")


def test_the_token_is_read_from_the_authorization_header() -> None:
    # Given a request carrying a bearer token
    headers = {"authorization": "Bearer abc.123"}

    # Then that is its session token
    assert session_token(headers) == "abc.123"


def test_the_token_is_read_from_the_session_cookie_when_there_is_no_header() -> None:
    # Given an image request, which carries only cookies
    headers = {"cookie": f"theme=dark; {SESSION_COOKIE}=abc.123; other=1"}

    # Then the session cookie is its token
    assert session_token(headers) == "abc.123"


def test_a_request_with_neither_has_no_token() -> None:
    # Given a request with no credentials
    # Then it has no session token
    assert session_token({"cookie": "theme=dark"}) is None
