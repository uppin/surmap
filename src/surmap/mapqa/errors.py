"""Failures a responder can act on when asking the map."""

from __future__ import annotations


class MapQaError(RuntimeError):
    """Base for Ask the map failures."""


class ModelApiKeyMissing(MapQaError):
    """``MODEL_API_KEY`` was missing or blank. No request was sent."""


class WonderFullRefused(MapQaError):
    """The configured model names Muse Wonder Full, which Model API does not serve."""


class ModelApiError(MapQaError):
    """The Meta Model API call failed or the body was not usable."""


class EmptyModelOutput(MapQaError):
    """The model returned no text, including after the one retry."""


class InvalidMapAnswer(MapQaError):
    """The model reply was not the strict answer object, or it cited an unknown id."""


class SnapshotError(MapQaError):
    """The snapshot file is not ``surmap.semantic_map_snapshot.v1``."""
