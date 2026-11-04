"""The agent's access gate: a shared pass code traded for a signed, expiring session token.

With `SURMAP_AGENT_ACCESS_CODE` set (`AgentServerConfig.access_code`), `POST /auth/session`
with `{"code": …}` answers `{"token", "expires_in"}` and sets the same token as an HttpOnly
cookie; every Connect rpc and API route then needs it, as `Authorization: Bearer <token>` or
the `surmap_session` cookie (which `<img>` and the GLB loader send without help). `/health`,
`/auth/session` and the chat page's own files stay open.

A token is `<expiry>.<hmac-sha256(key, expiry)>` with the key derived from the code: it needs no
server state, survives a restart, and changing the code revokes every token.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable, Mapping
from http.cookies import CookieError, SimpleCookie

SESSION_COOKIE = "surmap_session"
SESSION_PATH = "/auth/session"
DEFAULT_TTL_S = 12 * 3600
UNAUTHENTICATED_HINT = "sign in: open this page with ?code=<the agent's access code>"


class AccessGate:
    def __init__(
        self,
        code: str,
        *,
        clock: Callable[[], float] = time.time,
        ttl_s: int = DEFAULT_TTL_S,
    ) -> None:
        self._code = code.encode()
        self._key = hashlib.sha256(b"surmap-agent-session:" + self._code).digest()
        self._clock = clock
        self.ttl_s = ttl_s

    def issue(self, code: str) -> str | None:
        """A fresh token when `code` is the pass code, else None."""
        if not hmac.compare_digest(code.encode(), self._code):
            return None
        expiry = str(int(self._clock()) + self.ttl_s)
        return f"{expiry}.{self._sign(expiry)}"

    def allows(self, token: str) -> bool:
        """Whether `token` was issued by this code and has not expired."""
        expiry, _, signature = token.partition(".")
        if not expiry.isdigit() or not hmac.compare_digest(signature, self._sign(expiry)):
            return False
        return int(expiry) > self._clock()

    def _sign(self, expiry: str) -> str:
        return hmac.new(self._key, expiry.encode(), hashlib.sha256).hexdigest()


def session_token(headers: Mapping[str, str]) -> str | None:
    """The request's token: `Authorization: Bearer …`, else the session cookie."""
    authorization = headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get("cookie", ""))
    except CookieError:
        return None
    morsel = cookies.get(SESSION_COOKIE)
    return morsel.value if morsel is not None and morsel.value else None


def session_cookie(token: str, ttl_s: int) -> str:
    """The `Set-Cookie` value carrying `token` back on every same-origin request."""
    return f"{SESSION_COOKIE}={token}; Max-Age={ttl_s}; Path=/; HttpOnly; Secure; SameSite=Strict"
