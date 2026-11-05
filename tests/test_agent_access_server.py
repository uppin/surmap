"""The agent server behind its pass code, mounted in memory.

With `SURMAP_AGENT_ACCESS_CODE` set, `POST /auth/session` trades the code for a session token
(also set as an HttpOnly cookie), and every rpc and API route needs it; `/health` and the chat
page's own files stay open. Without a code nothing is gated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from surmap.agent.__main__ import config_from_args
from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.server.access import SESSION_COOKIE
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.rpc.hosts.in_memory import InMemoryHost
from surmap.rpc.http import HttpResponse
from tests.agent_server_fakes import CHAT_SERVICE, EmptyWorkspace, NoGlbs
from tests.fake_ollama import a_closed_ollama_url

CODE = "correct-horse-battery-staple"


def an_agent(*, access_code: str | None = CODE, web_dist: Path | None = None) -> InMemoryHost[None]:
    config = AgentServerConfig(access_code=access_code, web_dist=web_dist)
    description = build_agent_description(
        config,
        workspace=EmptyWorkspace(),
        geometry=NoGlbs(),
        registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
    )
    return InMemoryHost(description, None)


async def sign_in(agent: InMemoryHost[None], code: str) -> HttpResponse:
    return await agent.http(
        "POST",
        "/auth/session",
        body=json.dumps({"code": code}).encode(),
        headers={"content-type": "application/json"},
    )


async def a_token(agent: InMemoryHost[None]) -> str:
    response = await sign_in(agent, CODE)
    token = json.loads(response.body)["token"]
    assert isinstance(token, str)
    return token


async def list_models(agent: InMemoryHost[None], headers: dict[str, str] | None = None) -> object:
    return await agent.client(CHAT_SERVICE).unary(
        "ListModels", chat_pb2.ListModelsRequest(), headers
    )


async def test_an_rpc_without_a_session_is_refused_as_unauthenticated() -> None:
    # Given an agent behind a pass code
    agent = an_agent()

    # When the page calls it without signing in
    with pytest.raises(ConnectError) as refused:
        await list_models(agent)

    # Then the call is refused, saying how to get in
    assert refused.value.code == Code.UNAUTHENTICATED
    assert "?code=" in str(refused.value)


async def test_signing_in_with_the_pass_code_returns_a_token_and_sets_its_cookie() -> None:
    # Given an agent behind a pass code
    agent = an_agent()

    # When the page signs in with the code
    response = await sign_in(agent, CODE)

    # Then it gets a token, and the same token as a cookie only the browser can send back
    assert response.status == 200
    body = json.loads(response.body)
    assert body["token"] and body["expires_in"] == 12 * 3600
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}={body['token']};")
    assert all(flag in cookie for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"))


async def test_signing_in_with_a_wrong_code_is_refused() -> None:
    # Given an agent behind a pass code
    agent = an_agent()

    # When the page signs in with the wrong code
    response = await sign_in(agent, "guess")

    # Then it is refused with no token and no cookie
    assert response.status == 401
    assert "set-cookie" not in response.headers


async def test_an_rpc_carrying_the_session_token_is_answered() -> None:
    # Given a signed-in page
    agent = an_agent()
    token = await a_token(agent)

    # When it calls with the token in its Authorization header
    response = await list_models(agent, {"authorization": f"Bearer {token}"})

    # Then the agent answers
    assert isinstance(response, chat_pb2.ListModelsResponse)


async def test_an_api_route_without_a_session_is_refused() -> None:
    # Given an agent behind a pass code
    agent = an_agent()

    # When a frame is fetched without signing in
    response = await agent.http("GET", "/frames/run-7/1.jpg")

    # Then it is refused
    assert response.status == 401


async def test_an_image_request_carrying_the_session_cookie_gets_through() -> None:
    # Given a signed-in browser, whose <img> requests carry only the cookie
    agent = an_agent()
    token = await a_token(agent)

    # When it fetches a frame the agent does not have
    response = await agent.http(
        "GET", "/frames/run-7/1.jpg", headers={"cookie": f"{SESSION_COOKIE}={token}"}
    )

    # Then it passed the gate and reached the route, which has no such frame
    assert response.status == 404


async def test_health_answers_without_a_session() -> None:
    # Given an agent behind a pass code
    # When its health is checked
    response = await an_agent().http("GET", "/health")

    # Then it answers, so the host can tell it is up
    assert (response.status, response.body) == (200, b"ok")


async def test_the_chat_page_is_served_without_a_session(tmp_path: Path) -> None:
    # Given an agent serving a built chat page
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>SurMap agent chat</title>")
    (tmp_path / "assets" / "index.js").write_text("console.log('chat')")
    agent = an_agent(web_dist=tmp_path)

    # When the page and its script are fetched before signing in
    page = await agent.http("GET", "/")
    script = await agent.http("GET", "/assets/index.js")

    # Then both are served, so the page can ask for the code
    assert (page.status, page.headers["content-type"]) == (200, "text/html; charset=utf-8")
    assert b"SurMap agent chat" in page.body
    assert script.status == 200


async def test_the_chat_page_cannot_be_used_to_read_files_outside_it(tmp_path: Path) -> None:
    # Given an agent serving a built chat page, with a secret beside it
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("page")
    (tmp_path / "secret.txt").write_text("hunter2")
    agent = an_agent(web_dist=dist)

    # When a path climbs out of the page's directory
    response = await agent.http("GET", "/assets/../../secret.txt")

    # Then nothing is served
    assert response.status in (401, 404)
    assert b"hunter2" not in response.body


async def session_status(
    agent: InMemoryHost[None], headers: dict[str, str] | None = None
) -> object:
    response = await agent.http("GET", "/auth/session", headers=headers or {})
    assert response.status == 200
    return json.loads(response.body)


async def test_the_page_can_ask_whether_it_must_sign_in() -> None:
    # Given an agent behind a pass code
    agent = an_agent()

    # When a page that has not signed in asks for its session
    status = await session_status(agent)

    # Then it learns the agent is gated and it is not signed in
    assert status == {"gated": True, "signed_in": False}


async def test_a_signed_in_browser_learns_it_is_signed_in_from_its_cookie() -> None:
    # Given a browser that signed in earlier, in another tab
    agent = an_agent()
    token = await a_token(agent)

    # When a new tab, holding only the cookie, asks for its session
    status = await session_status(agent, {"cookie": f"{SESSION_COOKIE}={token}"})

    # Then it is signed in
    assert status == {"gated": True, "signed_in": True}


async def test_an_agent_without_a_pass_code_tells_the_page_it_need_not_sign_in() -> None:
    # Given an agent with no access code, as run locally
    agent = an_agent(access_code=None)

    # When the page asks for its session
    status = await session_status(agent)

    # Then nothing is gated
    assert status == {"gated": False, "signed_in": True}


async def test_an_agent_without_a_pass_code_gates_nothing() -> None:
    # Given an agent with no access code, as run locally
    agent = an_agent(access_code=None)

    # When the page calls it without signing in
    response = await list_models(agent)

    # Then it answers, as before
    assert isinstance(response, chat_pb2.ListModelsResponse)


def test_the_pass_code_comes_from_the_environment_and_the_page_from_a_flag() -> None:
    # Given the code in the environment and a built page on the command line
    config = config_from_args(
        ["--web-dist=/web"], environ={"SURMAP_AGENT_ACCESS_CODE": " correct-horse "}
    )

    # Then the config carries both, the code trimmed
    assert (config.access_code, config.web_dist) == ("correct-horse", Path("/web"))
