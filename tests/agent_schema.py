"""A small JSON Schema checker for tool-contract tests.

It covers the subset tool contracts use — `type` (object, string, integer, number, boolean,
array), `enum`, `properties`, `required`, `additionalProperties: false` and `items` — so a test
can say whether a schema admits a set of model arguments without a validator dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

__all__ = ["admits", "property_names", "property_of", "required_of"]

_SCALARS: Mapping[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def property_of(schema: Mapping[str, object], name: str) -> Mapping[str, object]:
    """The sub-schema of one property of an object schema."""
    properties = cast("Mapping[str, Mapping[str, object]]", schema["properties"])
    return properties[name]


def property_names(schema: Mapping[str, object]) -> list[str]:
    """The property names of an object schema, in schema order."""
    return list(cast("Mapping[str, object]", schema.get("properties", {})))


def required_of(schema: Mapping[str, object]) -> list[str]:
    """The required property names of an object schema; empty when it lists none."""
    return list(cast("Sequence[str]", schema.get("required", ())))


def admits(schema: Mapping[str, object], value: object) -> bool:
    """Whether `value` satisfies `schema`."""
    if "enum" in schema and value not in cast("Sequence[object]", schema["enum"]):
        return False
    kind = schema.get("type")
    if kind == "object":
        return _admits_object(schema, value)
    if kind == "array":
        return _admits_array(schema, value)
    if isinstance(kind, str) and kind in _SCALARS:
        is_bool = isinstance(value, bool)
        return isinstance(value, _SCALARS[kind]) and (kind == "boolean" or not is_bool)
    return True


def _admits_object(schema: Mapping[str, object], value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    fields = cast("Mapping[str, object]", value)
    properties = cast("Mapping[str, Mapping[str, object]]", schema.get("properties", {}))
    required = cast("Sequence[str]", schema.get("required", ()))
    if any(name not in fields for name in required):
        return False
    if schema.get("additionalProperties") is False and any(n not in properties for n in fields):
        return False
    return all(admits(properties[n], v) for n, v in fields.items() if n in properties)


def _admits_array(schema: Mapping[str, object], value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast("Mapping[str, object]", schema.get("items", {}))
    return all(admits(items, item) for item in cast("list[object]", value))
