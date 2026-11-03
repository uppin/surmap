"""Where the survey servers serve Connect over WebSocket, and the token that guards them."""

from __future__ import annotations

import os
from collections.abc import Mapping

# Both survey servers serve every Connect service over one WebSocket at this path.
CONNECT_PATH = "/connect"

# The bearer token servers require and clients send, when the flag does not name one.
TOKEN_ENV = "SURMAP_SURVEY_TOKEN"


def survey_token(explicit: str | None, environ: Mapping[str, str] | None = None) -> str | None:
    """`explicit`, else `$SURMAP_SURVEY_TOKEN`; blank means no token."""
    env = os.environ if environ is None else environ
    raw = explicit if explicit is not None else env.get(TOKEN_ENV, "")
    token = raw.strip()
    return token or None
