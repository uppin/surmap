"""The skill catalogue: discovery, listing and guarded loading of `SKILL.md` files.

A skill is a directory holding a `SKILL.md` whose front matter carries a `name` and a
one-line `description`. The catalogue lists names and descriptions only; a body reaches
the caller one skill at a time through `load_skill`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from surmap.agent.skills import (
    MAX_SKILL_BYTES,
    Skill,
    SkillCatalogue,
    SkillsUnavailableError,
    SkillValidationError,
)

MAP_SKILL_DESCRIPTION = (
    "How to use the map tools: place and move objects, navigate the camera, "
    "draw routes and load layers."
)


def a_skills_root(root: Path, *skills: tuple[str, str, str]) -> Path:
    """A skills root holding one directory per `(name, description, body)` given."""
    for name, description, body in skills:
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
            encoding="utf-8",
        )
    return root


def test_lists_every_skill_by_name_and_description_sorted_by_name(tmp_path: Path) -> None:
    # Given a builtin root with two skills written out of name order
    builtin = a_skills_root(
        tmp_path / "builtin",
        ("using-the-map", "How to use the map tools.", "Map body."),
        ("checking-a-run", "How to check a finished run.", "Run body."),
    )
    catalogue = SkillCatalogue(builtin_root=builtin)

    # When the catalogue is listed
    listed = catalogue.list_skills()

    # Then every skill appears once, sorted by name, with no body attached
    assert listed == (
        Skill(name="checking-a-run", description="How to check a finished run."),
        Skill(name="using-the-map", description="How to use the map tools."),
    )


def test_loads_one_skill_body_without_its_front_matter(tmp_path: Path) -> None:
    # Given a shipped skill
    builtin = a_skills_root(
        tmp_path / "builtin", ("using-the-map", "How to use the map tools.", "Place, then move.")
    )
    catalogue = SkillCatalogue(builtin_root=builtin)

    # When that skill is loaded by name
    body = catalogue.load_skill("using-the-map")

    # Then the body comes back in full, front matter stripped
    assert body == "Place, then move.\n"


def test_overlay_skill_wins_over_a_builtin_of_the_same_name(tmp_path: Path) -> None:
    # Given the same skill name in the builtin tree and in the overlay
    builtin = a_skills_root(
        tmp_path / "builtin", ("using-the-map", "Builtin wording.", "Builtin body.")
    )
    overlay = a_skills_root(
        tmp_path / "overlay", ("using-the-map", "Overlay wording.", "Overlay body.")
    )
    catalogue = SkillCatalogue(builtin_root=builtin, overlay_root=overlay)

    # When the skill is listed and loaded
    listed = catalogue.list_skills()
    body = catalogue.load_skill("using-the-map")

    # Then the overlay's description and body are the ones served
    assert listed == (Skill(name="using-the-map", description="Overlay wording."),)
    assert body == "Overlay body.\n"


def test_a_missing_skills_directory_lists_nothing(tmp_path: Path) -> None:
    # Given a configured root whose directory was never created
    catalogue = SkillCatalogue(builtin_root=tmp_path / "absent")

    # When the catalogue is listed
    listed = catalogue.list_skills()

    # Then it is an empty catalogue, not an error
    assert listed == ()


def test_no_configured_root_makes_skills_unavailable() -> None:
    # Given a catalogue with neither root configured
    catalogue = SkillCatalogue()

    # When it is listed or loaded from
    # Then both refuse: unavailable is not the same as an empty catalogue
    with pytest.raises(SkillsUnavailableError):
        catalogue.list_skills()
    with pytest.raises(SkillsUnavailableError):
        catalogue.load_skill("using-the-map")


def test_loading_an_unknown_skill_is_refused(tmp_path: Path) -> None:
    # Given a catalogue with one skill
    builtin = a_skills_root(
        tmp_path / "builtin", ("using-the-map", "How to use the map tools.", "Map body.")
    )
    catalogue = SkillCatalogue(builtin_root=builtin)

    # When a name no skill carries is loaded
    # Then the load is refused, naming the skill
    with pytest.raises(SkillValidationError, match="no skill called 'flying'"):
        catalogue.load_skill("flying")


def test_a_skill_name_cannot_escape_the_skills_directory(tmp_path: Path) -> None:
    # Given a catalogue over a real skills root
    builtin = a_skills_root(
        tmp_path / "builtin", ("using-the-map", "How to use the map tools.", "Map body.")
    )
    catalogue = SkillCatalogue(builtin_root=builtin)

    # When a name tries to walk out of the skills directory
    # Then the load is refused before any path is read
    with pytest.raises(SkillValidationError, match="outside the skills directory"):
        catalogue.load_skill("../secret")
    with pytest.raises(SkillValidationError, match="outside the skills directory"):
        catalogue.load_skill("/etc/passwd")


def test_a_skill_without_a_description_is_refused_at_listing(tmp_path: Path) -> None:
    # Given a skill whose front matter names it but describes nothing
    directory = tmp_path / "builtin" / "unnamed"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("---\nname: unnamed\n---\n\nBody.\n", encoding="utf-8")
    catalogue = SkillCatalogue(builtin_root=tmp_path / "builtin")

    # When the catalogue is listed
    # Then the skill is refused rather than listed with a blank description
    with pytest.raises(SkillValidationError, match="missing a description"):
        catalogue.list_skills()


def test_a_skill_body_over_the_size_cap_is_refused_not_truncated(tmp_path: Path) -> None:
    # Given a skill whose body is one byte over the cap
    builtin = a_skills_root(
        tmp_path / "builtin",
        ("using-the-map", "How to use the map tools.", "x" * (MAX_SKILL_BYTES + 1)),
    )
    catalogue = SkillCatalogue(builtin_root=builtin)

    # When the skill is loaded
    # Then it is refused whole: half a skill still reads like complete instructions
    with pytest.raises(SkillValidationError, match="exceeds the maximum size"):
        catalogue.load_skill("using-the-map")


def test_the_shipped_catalogue_offers_the_map_skill() -> None:
    # Given the catalogue the agent server builds by default
    catalogue = SkillCatalogue.shipped()

    # When it is listed
    listed = catalogue.list_skills()

    # Then the first shipped skill teaches the map tools
    assert Skill(name="using-the-map", description=MAP_SKILL_DESCRIPTION) in listed
    assert "add_map_object" in catalogue.load_skill("using-the-map")
