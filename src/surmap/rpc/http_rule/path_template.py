"""HttpRule path templates: parse, match, and decode the variables a URL path binds.

    Template = "/" Segments [ Verb ] ;
    Segments = Segment { "/" Segment } ;
    Segment  = "*" | "**" | LITERAL | Variable ;
    Variable = "{" FieldPath [ "=" Segments ] "}" ;
    FieldPath = IDENT { "." IDENT } ;
    Verb     = ":" LITERAL ;

Decoding follows the spec: a single-segment variable is fully percent-decoded; a multi-segment
variable is decoded except `%2F` / `%2f`, which stay encoded so the value's own segment boundaries
remain distinguishable from an encoded slash inside a segment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import unquote

__all__ = ["PathTemplate", "TemplateSyntaxError", "Variable"]

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LITERAL_FORBIDDEN = re.compile(r"[{}*/:]")
_ENCODED_SLASH = re.compile(r"(%2[Ff])")


class TemplateSyntaxError(ValueError):
    """The template is not valid HttpRule path-template syntax."""


class _Kind(Enum):
    LITERAL = "literal"
    SINGLE = "*"
    DOUBLE = "**"


@dataclass(frozen=True)
class _Segment:
    kind: _Kind
    literal: str = ""
    variable: int | None = None
    """Index into `PathTemplate.variables` of the variable this segment belongs to, if any."""


@dataclass(frozen=True)
class Variable:
    """A `{field.path=...}` capture."""

    field_path: tuple[str, ...]
    multi_segment: bool
    """True when the variable's pattern spans more than one segment, or is `**`."""

    @property
    def dotted(self) -> str:
        return ".".join(self.field_path)


class PathTemplate:
    """A parsed template; `match` gives each variable's decoded value by dotted field path."""

    def __init__(self, template: str, *, fully_decode_reserved_expansion: bool = False) -> None:
        self.template = template
        self._fully_decode_reserved_expansion = fully_decode_reserved_expansion
        segments, variables, verb = _parse(template)
        self._segments = segments
        self._variables = variables
        self._verb = verb

    @classmethod
    def parse(cls, template: str, *, fully_decode_reserved_expansion: bool = False) -> PathTemplate:
        return cls(template, fully_decode_reserved_expansion=fully_decode_reserved_expansion)

    @property
    def verb(self) -> str | None:
        return self._verb

    @property
    def variables(self) -> tuple[Variable, ...]:
        return self._variables

    def match(self, path: str) -> dict[str, str] | None:
        """The variables `path` binds, percent-decoded per the spec; None when it does not match."""
        if not path.startswith("/"):
            return None
        body = path[1:]
        if self._verb is not None:
            suffix = f":{self._verb}"
            if not body.endswith(suffix):
                return None
            body = body[: -len(suffix)]
        raw = body.split("/")
        if raw == [""] and self._segments and self._segments[-1].kind is _Kind.DOUBLE:
            raw = []
        captured: dict[int, list[str]] = {}
        index = 0
        for segment in self._segments:
            if segment.kind is _Kind.DOUBLE:
                rest = raw[index:]
                if any(part == "" for part in rest):
                    return None
                if segment.variable is not None:
                    captured.setdefault(segment.variable, []).extend(rest)
                index = len(raw)
                break
            if index >= len(raw) or raw[index] == "":
                return None
            part = raw[index]
            if segment.kind is _Kind.LITERAL:
                decoded = _decode(part)
                if decoded is None or decoded != segment.literal:
                    return None
            if segment.variable is not None:
                captured.setdefault(segment.variable, []).append(part)
            index += 1
        if index != len(raw):
            return None
        bindings: dict[str, str] = {}
        for position, variable in enumerate(self._variables):
            parts = captured.get(position, [])
            if variable.multi_segment:
                joined = "/".join(parts)
                value = (
                    _decode(joined)
                    if self._fully_decode_reserved_expansion
                    else _decode_keeping_slashes(joined)
                )
            else:
                value = _decode(parts[0])
            if value is None:
                return None
            bindings[variable.dotted] = value
        return bindings

    def shape(self) -> tuple[object, ...]:
        """The template with variable names erased: two rules of equal shape and verb conflict."""
        return (
            tuple(
                ("literal", segment.literal)
                if segment.kind is _Kind.LITERAL
                else segment.kind.value
                for segment in self._segments
            ),
            self._verb,
        )

    def specificity(self) -> tuple[int, ...]:
        """Orders matching templates: a verb first, then more literal segments, `**` last."""
        scores = {_Kind.LITERAL: 2, _Kind.SINGLE: 1, _Kind.DOUBLE: 0}
        return (1 if self._verb is not None else 0, *(scores[s.kind] for s in self._segments))

    def __repr__(self) -> str:
        return f"PathTemplate({self.template!r})"


def _decode(part: str) -> str | None:
    try:
        return unquote(part, errors="strict")
    except UnicodeDecodeError:
        return None


def _decode_keeping_slashes(value: str) -> str | None:
    pieces = _ENCODED_SLASH.split(value)
    decoded: list[str] = []
    for piece in pieces:
        if _ENCODED_SLASH.fullmatch(piece):
            decoded.append(piece)
            continue
        text = _decode(piece)
        if text is None:
            return None
        decoded.append(text)
    return "".join(decoded)


def _split_top_level(text: str, separator: str) -> list[str]:
    """Split on `separator` outside braces; raises on unbalanced braces."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "{":
            depth += 1
            if depth > 1:
                raise TemplateSyntaxError("nested variables are not allowed")
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise TemplateSyntaxError("unbalanced '}'")
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if depth != 0:
        raise TemplateSyntaxError("unbalanced '{'")
    parts.append("".join(current))
    return parts


def _parse(template: str) -> tuple[tuple[_Segment, ...], tuple[Variable, ...], str | None]:
    if not template.startswith("/"):
        raise TemplateSyntaxError(f"{template!r}: a template starts with '/'")
    body = template[1:]
    verb: str | None = None
    colon_parts = _split_top_level(body, ":")
    if len(colon_parts) > 2:
        raise TemplateSyntaxError(f"{template!r}: more than one ':'")
    if len(colon_parts) == 2:
        body, verb = colon_parts
        if not verb or _LITERAL_FORBIDDEN.search(verb):
            raise TemplateSyntaxError(f"{template!r}: invalid verb {verb!r}")
    segments: list[_Segment] = []
    variables: list[Variable] = []
    seen: set[tuple[str, ...]] = set()
    for raw_segment in _split_top_level(body, "/"):
        if raw_segment.startswith("{"):
            if not raw_segment.endswith("}"):
                raise TemplateSyntaxError(f"{template!r}: malformed variable {raw_segment!r}")
            inner = raw_segment[1:-1]
            field, _, pattern = inner.partition("=")
            field_path = tuple(field.split("."))
            if not field or not all(_IDENT.fullmatch(part) for part in field_path):
                raise TemplateSyntaxError(f"{template!r}: invalid field path {field!r}")
            if field_path in seen:
                raise TemplateSyntaxError(f"{template!r}: {field!r} is bound twice")
            seen.add(field_path)
            if "=" in inner and not pattern:
                raise TemplateSyntaxError(f"{template!r}: empty pattern for {field!r}")
            pattern_segments = [_plain_segment(p, template) for p in (pattern or "*").split("/")]
            index = len(variables)
            variables.append(
                Variable(
                    field_path=field_path,
                    multi_segment=len(pattern_segments) > 1
                    or any(s.kind is _Kind.DOUBLE for s in pattern_segments),
                )
            )
            segments.extend(
                _Segment(kind=s.kind, literal=s.literal, variable=index) for s in pattern_segments
            )
        else:
            segments.append(_plain_segment(raw_segment, template))
    for position, segment in enumerate(segments):
        if segment.kind is _Kind.DOUBLE and position != len(segments) - 1:
            raise TemplateSyntaxError(f"{template!r}: '**' must be the last segment")
    return tuple(segments), tuple(variables), verb


def _plain_segment(text: str, template: str) -> _Segment:
    if text == "*":
        return _Segment(kind=_Kind.SINGLE)
    if text == "**":
        return _Segment(kind=_Kind.DOUBLE)
    if not text or _LITERAL_FORBIDDEN.search(text):
        raise TemplateSyntaxError(f"{template!r}: invalid segment {text!r}")
    return _Segment(kind=_Kind.LITERAL, literal=text)
