"""The licence gate for simulation assets.

Only CC0 and CC BY (3.0/4.0) assets enter a scenario: they are free to use, adapt and show
with attribution, and nothing in them binds the scenario built from them. Everything else is
refused with the clause that rules it out — the agent relays the reason, so the developer sees
why an asset was skipped. Labels come as each source writes them (Sketchfab slugs and labels,
SPDX ids).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LicenceVerdict:
    accepted: bool
    spdx: str | None
    reason: str


_ACCEPTED = {
    "cc0": "CC0-1.0",
    "cc0-1.0": "CC0-1.0",
    "cc0 public domain": "CC0-1.0",
    "by": "CC-BY-4.0",
    "cc attribution": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-3.0": "CC-BY-3.0",
}

# (marker in a lower-cased label, the clause it brings)
_CLAUSES = (
    ("nc", "non-commercial: the scenario could not be used freely"),
    ("noncommercial", "non-commercial: the scenario could not be used freely"),
    ("nd", "no derivatives: the asset could not be placed or altered in a scene"),
    ("noderivs", "no derivatives: the asset could not be placed or altered in a scene"),
    ("sa", "share-alike: the licence would bind the whole scenario"),
    ("sharealike", "share-alike: the licence would bind the whole scenario"),
)


def check_licence(raw: str) -> LicenceVerdict:
    label = raw.strip().lower()
    spdx = _ACCEPTED.get(label)
    if spdx is not None:
        return LicenceVerdict(accepted=True, spdx=spdx, reason="")
    words = set(label.replace("-", " ").replace("_", " ").split())
    for marker, clause in _CLAUSES:
        if marker in words:
            return LicenceVerdict(accepted=False, spdx=None, reason=f"{raw}: {clause}")
    return LicenceVerdict(
        accepted=False, spdx=None, reason=f"{raw}: not an open licence (only CC0 and CC BY)"
    )
