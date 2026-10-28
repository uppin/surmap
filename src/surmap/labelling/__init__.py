"""Semantic labels for mapped objects."""

from surmap.labelling.base import LabelClient, ObjectLabel
from surmap.labelling.baseten_muse import (
    BasetenApiKeyMissing,
    BasetenLabelError,
    BasetenMuseLabelClient,
)
from surmap.labelling.memory import InMemoryLabelClient

__all__ = [
    "BasetenApiKeyMissing",
    "BasetenLabelError",
    "BasetenMuseLabelClient",
    "InMemoryLabelClient",
    "LabelClient",
    "ObjectLabel",
]
