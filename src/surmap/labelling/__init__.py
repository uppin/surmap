"""Semantic labels for mapped objects. Hosted calls stay behind a client."""

from surmap.labelling.baseten_muse import (
    BasetenApiKeyMissing,
    BasetenMuseLabelClient,
    BasetenRequestError,
    EmptyLabelError,
    LabelClient,
    ObjectLabel,
)

__all__ = [
    "BasetenApiKeyMissing",
    "BasetenMuseLabelClient",
    "BasetenRequestError",
    "EmptyLabelError",
    "LabelClient",
    "ObjectLabel",
]
