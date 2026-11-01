"""One chat completion against the Muse Spark Open shared endpoint.

Reads ``MODAL_MUSE_URL``, ``MODAL_PROXY_TOKEN_ID``,
``MODAL_PROXY_TOKEN_SECRET``, and optional ``MODAL_MUSE_MODEL``.
Prints the assistant text. Does not import the Modal SDK.
"""

from __future__ import annotations

import sys

from surmap.labelling.modal_muse import ModalMuseClient, ModalMuseConfigError


def main() -> int:
    """Ask for a one-word reply. Exit 2 when the endpoint is not configured."""
    try:
        text = ModalMuseClient().chat(
            [{"role": "user", "content": "Reply with the single word ready."}]
        )
    except ModalMuseConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
