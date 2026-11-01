"""Semantic labels and the scene note for a mapped area.

Hosted calls stay behind a client. Each one is optional and talks to its own API.
"""

from surmap.labelling.baseten_muse import (
    BasetenApiKeyMissing,
    BasetenMuseLabelClient,
    BasetenRequestError,
    EmptyLabelError,
    LabelClient,
    ObjectLabel,
)
from surmap.labelling.meta_muse import (
    MetaMuseLabelClient,
    MetaMuseSceneClient,
    MetaMuseSceneError,
)
from surmap.labelling.modal_muse import (
    ModalMuseClient,
    ModalMuseConfigError,
    ModalMuseRequestError,
)

__all__ = [
    "BasetenApiKeyMissing",
    "BasetenMuseLabelClient",
    "BasetenRequestError",
    "EmptyLabelError",
    "LabelClient",
    "MetaMuseLabelClient",
    "MetaMuseSceneClient",
    "MetaMuseSceneError",
    "ModalMuseClient",
    "ModalMuseConfigError",
    "ModalMuseRequestError",
    "ObjectLabel",
]
