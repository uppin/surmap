"""The agent server on a real socket: `build_agent_description` over a real `DemoWorkspace`
(the tiny EuRoC scene, fake SAM, temp cache and history) on `HypercornHost` port 0, spoken to
over HTTP/1.1 — health, one streamed Connect turn with a real `list_demos`, GLB and frame routes.

The model is n4's `ScriptedChatModel`; nothing leaves loopback.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from surmap.agent.llm.registry import ChatModelRegistry
from surmap.agent.proto import chat_pb2
from surmap.agent.server.app import AgentServerConfig, build_agent_description
from surmap.objects3d import read_glb_header, write_glb
from surmap.rpc.hosts.hypercorn import HypercornHost
from tests.agent_fakes import ScriptedChatModel, answer, calling, tool_call
from tests.agent_server_fakes import STEP_TIMEOUT_S, finished_call, kinds
from tests.agent_tool_fakes import TINY_SCENE, ToolRig, a_recorded_run, a_tool_rig, image_format
from tests.fake_ollama import a_closed_ollama_url

UI_ORIGIN = "http://localhost:5173"
STREAM_TURN = "/surmap.agent.v1.ChatService/StreamTurn"


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class RunningAgent:
    address: str
    rig: ToolRig

    async def get(self, path: str) -> Reply:
        return await asyncio.to_thread(self._request, "GET", path, b"", {})

    async def stream_turn(self, text: str, *, origin: str | None = None) -> Reply:
        request = chat_pb2.StreamTurnRequest(conversation_id="conv-1", text=text)
        payload = request.SerializeToString()
        headers = {"content-type": "application/connect+proto"}
        if origin is not None:
            headers["origin"] = origin
        body = struct.pack(">BI", 0, len(payload)) + payload
        return await asyncio.to_thread(self._request, "POST", STREAM_TURN, body, headers)

    def _request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> Reply:
        connection = http.client.HTTPConnection(self.address, timeout=STEP_TIMEOUT_S)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return Reply(
                status=response.status,
                headers={name.lower(): value for name, value in response.getheaders()},
                body=response.read(),
            )
        finally:
            connection.close()


def turn_events(reply: Reply) -> list[chat_pb2.TurnEvent]:
    """The Connect stream's messages, up to its end-of-stream frame."""
    events: list[chat_pb2.TurnEvent] = []
    offset = 0
    while offset < len(reply.body):
        flag, length = struct.unpack(">BI", reply.body[offset : offset + 5])
        payload = reply.body[offset + 5 : offset + 5 + length]
        offset += 5 + length
        if flag & 0x02:
            assert json.loads(payload or b"{}") == {}, f"the stream ended with {payload!r}"
            break
        events.append(chat_pb2.TurnEvent.FromString(payload))
    return events


def a_model_listing_demos() -> ScriptedChatModel:
    return ScriptedChatModel.replying(
        calling(tool_call("list_demos", "call-1")), answer("The tiny scene is ready")
    )


@asynccontextmanager
async def a_running_agent(tmp_path: Path, model: ScriptedChatModel) -> AsyncIterator[RunningAgent]:
    """The agent over the tiny scene's workspace on an ephemeral loopback port; always
    stopped after."""
    with a_tool_rig(tmp_path) as rig:
        config = AgentServerConfig(
            port=0, model_id="ollama:scripted", model_factory=lambda _: model
        )
        description = build_agent_description(
            config,
            workspace=rig.workspace,
            geometry=rig.workspace.geometry,
            registry=ChatModelRegistry(environ={"SURMAP_OLLAMA_URL": a_closed_ollama_url()}),
        )
        host = HypercornHost(description, None, host="127.0.0.1", port=0)
        ports = await host.start()
        try:
            yield RunningAgent(address=f"127.0.0.1:{ports.public}", rig=rig)
        finally:
            await host.stop()


async def test_the_agent_answers_health_on_a_real_socket(tmp_path: Path) -> None:
    # Given the agent on a real port
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        # When a probe asks for /health
        reply = await agent.get("/health")

    # Then it is up
    assert reply.status == 200


async def test_one_turn_streams_over_http_1_1_connect(tmp_path: Path) -> None:
    # Given the agent on a real port, with a model that lists the demos
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        # When the UI posts one StreamTurn
        reply = await agent.stream_turn("what demos can you run?")

    # Then the whole turn arrives, ending with turn_finished
    assert kinds(turn_events(reply)) == [
        "user_message",
        "tool_call_started",
        "tool_call_finished",
        "text_delta",
        "turn_finished",
    ]


async def test_the_streamed_list_demos_result_names_the_station_s_scene(tmp_path: Path) -> None:
    # Given the agent over the tiny scene, with a model that lists the demos
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        # When the UI posts one StreamTurn
        reply = await agent.stream_turn("what demos can you run?")

    # Then the real list_demos result offers the tiny scene
    result = json.loads(finished_call(turn_events(reply), "call-1").result_json)
    assert TINY_SCENE in [scene["id"] for scene in result["scenes"]]


async def test_a_connect_response_allows_the_chat_ui_s_origin(tmp_path: Path) -> None:
    # Given the agent allowing the Vite dev origin
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        # When the UI's page posts a StreamTurn
        reply = await agent.stream_turn("what demos can you run?", origin=UI_ORIGIN)

    # Then the browser may read the response
    assert reply.headers.get("access-control-allow-origin") == UI_ORIGIN


async def test_a_published_glb_is_served_as_a_file_a_gltf_reader_accepts(tmp_path: Path) -> None:
    # Given an object's points published as a GLB
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        agent.rig.workspace.geometry.put(
            "run-7", "obj_1", write_glb(points, frame="map", up_axis="-y")
        )

        # When the viewer fetches it over HTTP
        reply = await agent.get("/geometry/run-7/obj_1.glb")

    # Then it parses as a glTF binary of one point primitive
    header = read_glb_header(reply.body)
    assert (header.magic, header.primitive_modes) == (b"glTF", (0,))


async def test_a_recorded_frame_is_served_as_a_jpeg(tmp_path: Path) -> None:
    # Given a recorded run of the tiny scene
    async with a_running_agent(tmp_path, a_model_listing_demos()) as agent:
        run_id = await asyncio.to_thread(a_recorded_run, agent.rig)

        # When the chat UI shows its first frame
        reply = await agent.get(f"/frames/{run_id}/1.jpg")

    # Then it is a JPEG
    assert (reply.status, image_format(reply.body)) == (200, "JPEG")
