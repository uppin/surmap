"""Async WebSocket smoke test: FastAPI echo on Modal, asyncio client locally.

Run: uvx --with websockets modal run ws_modal.py

The endpoint is unauthenticated while the app runs. Do not reuse this
handler for real data without proxy auth or a token check.
"""

import asyncio
import json
import time

import modal

image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")
app = modal.App("surmap-smoke-ws", image=image)

SERVER_DELAY_S = 0.2
MESSAGES_PER_CONNECTION = 3


@app.function(cpu=0.25, memory=256, timeout=120, max_containers=1)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def web():
    import os

    from fastapi import FastAPI, WebSocket, WebSocketDisconnect

    api = FastAPI()

    @api.websocket("/ws")
    async def echo(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                await asyncio.sleep(SERVER_DELAY_S)  # async work: connections overlap
                reply = {**msg, "echo": True, "task_id": os.environ.get("MODAL_TASK_ID", "?")}
                await ws.send_text(json.dumps(reply))
        except WebSocketDisconnect:
            pass

    return api


async def client(url: str, conn: int, n: int) -> tuple[list[dict[str, object]], float]:
    import websockets

    start = time.perf_counter()
    replies = []
    async with websockets.connect(url, compression=None, open_timeout=60) as ws:
        for i in range(n):
            await ws.send(json.dumps({"conn": conn, "seq": i}))
            replies.append(json.loads(await ws.recv()))
    return replies, time.perf_counter() - start


@app.local_entrypoint()
def main(connections: int = 3) -> None:
    url = web.get_web_url().replace("https://", "wss://") + "/ws"
    print(f"endpoint: {url}")

    async def run() -> bool:
        await client(url, conn=-1, n=1)  # warm-up absorbs the cold start
        start = time.perf_counter()
        results = await asyncio.gather(
            *(client(url, conn=c, n=MESSAGES_PER_CONNECTION) for c in range(connections))
        )
        wall = time.perf_counter() - start

        for replies, seconds in results:
            for r in replies:
                print(f"  conn {r['conn']} seq {r['seq']} echo={r['echo']} {r['task_id']}")
            print(f"  conn {replies[0]['conn']} took {seconds:.2f}s")

        serial = sum(seconds for _, seconds in results)
        echoed = all(r["echo"] for replies, _ in results for r in replies)
        count = sum(len(replies) for replies, _ in results)
        tasks = {r["task_id"] for replies, _ in results for r in replies}
        overlapped = wall < 0.75 * serial
        print(
            f"{count} messages over {connections} connections: wall {wall:.2f}s, "
            f"sum of connections {serial:.2f}s, containers {len(tasks)}"
        )
        ok = echoed and count == connections * MESSAGES_PER_CONNECTION and overlapped
        print("PASS: async connections overlapped" if ok else "FAIL")
        return ok

    if not asyncio.run(run()):
        raise SystemExit(1)
