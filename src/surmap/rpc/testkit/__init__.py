"""Test doubles built on the kit: recording bricks and third-party HTTP stubs."""

from surmap.rpc.testkit.recording import RecordedCall, RecordingBrick
from surmap.rpc.testkit.stubs import aio_http_stub

__all__ = ["RecordedCall", "RecordingBrick", "aio_http_stub"]
