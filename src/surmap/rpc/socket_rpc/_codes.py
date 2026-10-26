"""Connect `Code` values on the socket error wire (gRPC numeric codes)."""

from __future__ import annotations

from connectrpc.code import Code

# Matches `socket_rpc.proto`: canceled = 1 … unauthenticated = 16.
_CODE_TO_WIRE: dict[Code, int] = {
    Code.CANCELED: 1,
    Code.UNKNOWN: 2,
    Code.INVALID_ARGUMENT: 3,
    Code.DEADLINE_EXCEEDED: 4,
    Code.NOT_FOUND: 5,
    Code.ALREADY_EXISTS: 6,
    Code.PERMISSION_DENIED: 7,
    Code.RESOURCE_EXHAUSTED: 8,
    Code.FAILED_PRECONDITION: 9,
    Code.ABORTED: 10,
    Code.OUT_OF_RANGE: 11,
    Code.UNIMPLEMENTED: 12,
    Code.INTERNAL: 13,
    Code.UNAVAILABLE: 14,
    Code.DATA_LOSS: 15,
    Code.UNAUTHENTICATED: 16,
}

_WIRE_TO_CODE: dict[int, Code] = {wire: code for code, wire in _CODE_TO_WIRE.items()}


def code_to_wire(code: Code) -> int:
    return _CODE_TO_WIRE.get(code, 2)


def code_from_wire(wire: int) -> Code:
    return _WIRE_TO_CODE.get(wire, Code.UNKNOWN)
