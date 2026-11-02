"""The demo's SAM prompt: which concept a run looks for, and its form.

A run's prompt is the page's, else the launcher's `--sam-label`, else
the scene's own default (`DatasetSpec.sam_prompt`). An ONNX export's
concept was fixed when it was exported, so it overrides all of them
and the page shows it read-only.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

# A SAM concept is a short noun phrase; longer page input is cut here.
MAX_SAM_PROMPT_CHARS = 100


@dataclass(frozen=True)
class SamPromptPolicy:
    """The server-wide part of a run's prompt: the launcher's choices."""

    override: str | None = None  # the launcher's --sam-label
    fixed: str | None = None  # an ONNX export's concept

    def resolve(self, requested: str | None, scene_default: str) -> str:
        """The concept this run looks for."""
        if self.fixed is not None:
            return self.fixed
        asked = (requested or "").strip()[:MAX_SAM_PROMPT_CHARS]
        return asked or self.override or scene_default


def sam_pane(
    dataset_id: str,
    prompt: str | None,
    *,
    fixed: bool,
    size: tuple[int, int],
    execution: str = "",
) -> str:
    """The SAM pane: the prompt form (read-only when fixed) and its view."""
    if prompt is None:
        return ""
    width, height = size
    status = (
        f"SAM ({execution}): waiting for the first result…"
        if execution
        else "SAM: waiting for the first result…"
    )
    editable = (
        'readonly title="fixed by the ONNX export">'
        if fixed
        else '><button type="submit">Apply</button>'
    )
    return (
        '<div class="sam-pane"><h2>SAM 3.1 (video) — own rate</h2>'
        '<form class="controls" method="get" action="/">'
        f'<input type="hidden" name="dataset" value="{html.escape(dataset_id)}">'
        '<label for="sam-prompt">SAM prompt</label>'
        f'<input id="sam-prompt" name="prompt" maxlength="{MAX_SAM_PROMPT_CHARS}" '
        f'value="{html.escape(prompt)}" {editable}</form>'
        f'<canvas id="sam-view" width="{width}" height="{height}"></canvas>'
        f'<p class="legend" id="sam-status">{html.escape(status)}</p></div>'
    )
