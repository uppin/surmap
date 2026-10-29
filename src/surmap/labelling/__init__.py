<<<<<<< HEAD
"""Semantic labels and the scene note for a mapped area.

Hosted calls stay behind a client. Each client talks to its own API.
"""

from surmap.labelling.baseten_muse import (
    BasetenApiKeyMissing,
    BasetenMuseLabelClient,
    BasetenRequestError,
    EmptyLabelError,
    LabelClient,
    ObjectLabel,
)
from surmap.labelling.meta_muse import MetaMuseSceneClient, MetaMuseSceneError

__all__ = [
    "BasetenApiKeyMissing",
    "BasetenMuseLabelClient",
    "BasetenRequestError",
    "EmptyLabelError",
    "LabelClient",
    "MetaMuseSceneClient",
    "MetaMuseSceneError",
    "ObjectLabel",
]
=======
"""Hosted labelling clients. Each one is optional and talks to its own API."""
>>>>>>> origin/cursor/modal-sam-gpu-bdcd
