"""Minimal Modal smoke test: build a tiny image and run one function in it."""

import modal

image = modal.Image.debian_slim(python_version="3.12")
app = modal.App("surmap-smoke-hello", image=image)


@app.function(cpu=0.25, memory=256, timeout=60)
def hello(name: str) -> dict[str, str]:
    import os
    import platform
    import socket

    return {
        "greeting": f"hello, {name}, from Modal",
        "python": platform.python_version(),
        "kernel": platform.release(),
        "host": socket.gethostname(),
        "task_id": os.environ.get("MODAL_TASK_ID", "?"),
    }


@app.local_entrypoint()
def main(name: str = "surmap") -> None:
    for key, value in hello.remote(name).items():
        print(f"{key:>8}: {value}")
