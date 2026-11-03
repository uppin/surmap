"""Skills: reviewed instructions the agent discovers and loads one at a time.

Everything telling the agent how to behave otherwise lives in the `SYSTEM_PROMPT`
constant. Adding guidance there means editing and redeploying that text, and pushing a
whole catalogue of guidance into every turn would cost more context than the
conversations it was meant to help.

A skill is a directory holding a `SKILL.md`, whose front matter carries a `name` and a
one-line `description`. The catalogue is **offered as a list and loaded one at a time**:
`list_skills` returns names and descriptions only, and `load_skill` returns one body as
an ordinary tool result. A body therefore costs context only when the model chooses it,
and because it arrives as a tool result — never as an addition to the system prompt,
which is a module constant shared by every conversation in the process — loading a skill
is not sticky and can be re-read or ignored per conversation.

Two roots, both deployment-controlled, never caller input:

- the **builtin** root is the tree shipped in this package (`skills/<name>/SKILL.md`);
- the **overlay** root is a directory a deployment supplies (`AgentServerConfig.skills_dir`
  or `SURMAP_AGENT_SKILLS_DIR`), whose skills win on a name collision.

A skill name arrives from a model, so loading guards it the way the path code elsewhere
in this repo does: an anchored rejection of absolute or `..` names, then a
post-`resolve()` check that the skill file is still inside the skills directory. A body
over `MAX_SKILL_BYTES` is refused whole — a skill cut in half is worse than one refused,
because the half that survives still reads like complete instructions.
"""

from __future__ import annotations

import importlib.resources
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from surmap.agent.contracts import ExecutionMode, ExecutionPolicy, OnTimeout, ToolContract
from surmap.agent.runtime.jobs import JobRunner
from surmap.agent.runtime.tools import BoundTool, bind_contract_tool

__all__ = [
    "MAX_SKILL_BYTES",
    "SKILL_FILE_NAME",
    "Skill",
    "SkillCatalogue",
    "SkillError",
    "SkillValidationError",
    "SkillsUnavailableError",
    "skill_contracts",
    "skill_tools",
]

SKILL_FILE_NAME = "SKILL.md"

MAX_SKILL_BYTES = 64 * 1024
"""How much of one skill may reach a model's context; over it, the load is refused."""

_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class SkillError(ValueError):
    """A skill could not be listed or loaded."""


class SkillsUnavailableError(SkillError):
    """No skill root is configured, so skills are unavailable.

    Not the same as "this deployment has no skills", which is an empty listing.
    """


class SkillValidationError(SkillError):
    """A skill, or the name asked for, is not well-formed."""


@dataclass(frozen=True)
class Skill:
    """One skill, as the listing describes it.

    The body is deliberately absent: the listing is what a model reads to choose, and
    carrying every body through it would defeat the reason the listing exists.
    """

    name: str
    description: str


class SkillCatalogue:
    """The skills available to the agent, from a builtin root and an overlay root.

    The overlay wins on a name collision. Unavailable means **neither** root is
    configured — a configured root whose directory is missing lists nothing from that
    root rather than raising.
    """

    def __init__(
        self, *, builtin_root: Path | None = None, overlay_root: Path | None = None
    ) -> None:
        self._builtin_root = builtin_root
        self._overlay_root = overlay_root

    @classmethod
    def shipped(cls, overlay_root: Path | None = None) -> SkillCatalogue:
        """The catalogue the server serves: this package's skills, plus `overlay_root`."""
        builtin = Path(str(importlib.resources.files("surmap.agent.skills")))
        return cls(builtin_root=builtin, overlay_root=overlay_root)

    def list_skills(self) -> tuple[Skill, ...]:
        """Every well-formed skill, sorted by name, by name and description.

        A skill whose front matter lacks either is **refused**, not listed with a blank:
        a model cannot choose against an empty description, and nobody notices a skill
        that is silently useless. Raises `SkillsUnavailableError` when neither root is
        configured.
        """
        self._require_any_root()
        by_name: dict[str, Skill] = {}
        for root in (self._builtin_root, self._overlay_root):
            if root is not None and root.is_dir():
                for skill in _discover_skills(root):
                    by_name[skill.name] = skill
        return tuple(skill for _, skill in sorted(by_name.items()))

    def load_skill(self, name: str) -> str:
        """One skill's body, in full; the overlay wins when both roots define the name.

        Raises `SkillsUnavailableError` when neither root is configured, and
        `SkillValidationError` when the name escapes the skills directory, when no such
        skill exists, or when the body exceeds `MAX_SKILL_BYTES`.
        """
        self._require_any_root()
        for root in (self._overlay_root, self._builtin_root):
            if root is None:
                continue
            skill_file = _resolve_skill_file(root, name)
            if skill_file.is_file():
                return _load_skill_body(skill_file, name)
        raise SkillValidationError(f"no skill called {name!r}")

    def _require_any_root(self) -> None:
        if self._builtin_root is None and self._overlay_root is None:
            raise SkillsUnavailableError("no skill roots are configured, so skills are unavailable")


def skill_contracts() -> tuple[ToolContract, ToolContract]:
    """The `list_skills` and `load_skill` contracts, in the order the model sees them."""
    return (
        ToolContract(
            name="list_skills",
            service="surmap.agent.skills",
            method="ListSkills",
            description=(
                "Lists the skills available to you: reviewed instructions for kinds of "
                "work, each with a one-line description. Bodies are not included; call "
                "load_skill with a name to read one before doing the work it describes."
            ),
            input_schema=_schema({}),
            default_execution=_DEFAULT_EXECUTION,
        ),
        ToolContract(
            name="load_skill",
            service="surmap.agent.skills",
            method="LoadSkill",
            description=(
                "Reads one skill's full instructions by the name list_skills reported. "
                "Load the skill that fits the task before starting it; the body returns "
                "as this call's result."
            ),
            input_schema=_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "The skill to read, exactly as list_skills reported it.",
                    }
                },
                required=("name",),
            ),
            default_execution=_DEFAULT_EXECUTION,
        ),
    )


_DEFAULT_EXECUTION = ExecutionPolicy(
    mode=ExecutionMode.SYNC, timeout_s=10, on_timeout=OnTimeout.FAIL
)


def skill_tools(catalogue: SkillCatalogue, runner: JobRunner) -> tuple[BoundTool, ...]:
    """`list_skills` and `load_skill` as bound tools over `catalogue`, run by `runner`."""

    async def list_skills(arguments: Mapping[str, object]) -> Mapping[str, object]:
        listed = catalogue.list_skills()
        return {
            "skills": [{"name": skill.name, "description": skill.description} for skill in listed]
        }

    async def load_skill(arguments: Mapping[str, object]) -> Mapping[str, object]:
        name = arguments.get("name")
        if not isinstance(name, str):
            raise ValueError("name must be a string")
        return {"name": name, "body": catalogue.load_skill(name)}

    contracts = {contract.name: contract for contract in skill_contracts()}
    return (
        bind_contract_tool(contracts["list_skills"], list_skills, runner),
        bind_contract_tool(contracts["load_skill"], load_skill, runner),
    )


def _schema(
    properties: Mapping[str, object], *, required: tuple[str, ...] = ()
) -> dict[str, object]:
    """A tool argument schema: `properties` plus the optional `execution` argument every
    tool carries (see `surmap.agent.contracts`)."""
    all_properties: dict[str, object] = dict(properties)
    all_properties["execution"] = {
        "type": "object",
        "description": (
            "How this call runs, when it should differ from the tool's default: give any "
            "of mode, timeout_s and on_timeout, and the others keep their default."
        ),
        "properties": {
            "mode": {"type": "string", "enum": ["SYNC", "ASYNC"]},
            "timeout_s": {"type": "integer"},
            "on_timeout": {"type": "string", "enum": ["FAIL", "DETACH"]},
        },
        "additionalProperties": False,
    }
    schema: dict[str, object] = {
        "$schema": _JSON_SCHEMA_DIALECT,
        "type": "object",
        "properties": all_properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _discover_skills(skills_root: Path) -> tuple[Skill, ...]:
    """Every well-formed skill under one directory of skill subdirectories."""
    discovered: list[Skill] = []
    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / SKILL_FILE_NAME
        if skill_file.is_file():
            discovered.append(_skill_from_file(skill_file))
    return tuple(discovered)


def _resolve_skill_file(skills_root: Path, name: str) -> Path:
    """The `SKILL.md` of `name` under `skills_root`, proven to stay inside the root."""
    candidate_name = Path(name)
    if candidate_name.is_absolute() or ".." in candidate_name.parts:
        raise SkillValidationError(f"skill name {name!r} resolves outside the skills directory")
    root = skills_root.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise SkillValidationError(f"skill name {name!r} resolves outside the skills directory")
    return candidate / SKILL_FILE_NAME


def _load_skill_body(skill_file: Path, name: str) -> str:
    _front_matter, body = _parse_skill_document(skill_file.read_text(encoding="utf-8"))
    if len(body.encode("utf-8")) > MAX_SKILL_BYTES:
        raise SkillValidationError(
            f"skill {name!r} exceeds the maximum size of {MAX_SKILL_BYTES} bytes"
        )
    return body


def _skill_from_file(path: Path) -> Skill:
    front_matter, _body = _parse_skill_document(path.read_text(encoding="utf-8"))
    name = front_matter.get("name", "")
    description = front_matter.get("description", "")
    if not name:
        raise SkillValidationError("skill is missing a name")
    if not description:
        raise SkillValidationError("skill is missing a description")
    return Skill(name=name, description=description)


def _parse_skill_document(content: str) -> tuple[dict[str, str], str]:
    """One `SKILL.md` split into its front matter (scalar `key: value` lines) and body."""
    if not content.startswith("---"):
        raise SkillValidationError("skill has no front matter")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise SkillValidationError("skill has no front matter")
    front_matter: dict[str, str] = {}
    for line in parts[1].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            front_matter[key.strip()] = value.strip().strip("\"'")
    return front_matter, parts[2].lstrip("\n")
