"""The licence gate for simulation assets: CC0 and CC BY in, everything else out with a reason."""

import pytest
from surmap.simulation.licences import check_licence


@pytest.mark.parametrize(
    ("raw", "spdx"),
    [
        ("cc0", "CC0-1.0"),
        ("CC0-1.0", "CC0-1.0"),
        ("CC0 Public Domain", "CC0-1.0"),
        ("by", "CC-BY-4.0"),
        ("CC Attribution", "CC-BY-4.0"),
        ("CC-BY-4.0", "CC-BY-4.0"),
        ("CC-BY-3.0", "CC-BY-3.0"),
    ],
)
def test_public_domain_and_attribution_licences_are_accepted(raw: str, spdx: str) -> None:
    # When a source's licence label is checked
    verdict = check_licence(raw)

    # Then it is accepted under its SPDX id
    assert (verdict.accepted, verdict.spdx) == (True, spdx)


@pytest.mark.parametrize(
    ("raw", "clause"),
    [
        ("by-nc", "non-commercial"),
        ("CC Attribution-NonCommercial", "non-commercial"),
        ("by-nd", "no derivatives"),
        ("by-sa", "share-alike"),
        ("CC Attribution-ShareAlike", "share-alike"),
        ("free-st", "not an open licence"),
        ("st", "not an open licence"),
        ("ed", "not an open licence"),
        ("All rights reserved", "not an open licence"),
    ],
)
def test_restricted_licences_are_refused_naming_the_clause(raw: str, clause: str) -> None:
    # When a restricted licence is checked
    verdict = check_licence(raw)

    # Then it is refused, and the reason says which clause rules it out
    assert verdict.accepted is False
    assert clause in verdict.reason
