"""The 3D contract for detected objects: summaries, `surmap-obj v1` text and GLB.

Pure numpy functions over an object's points (and, later, faces). Every output names the
coordinate `frame` and `up_axis` it is in; nothing here reads or writes RTAB-Map's map.
"""

from __future__ import annotations

from surmap.objects3d.glb import GlbHeader, read_glb_header, write_glb
from surmap.objects3d.obj_text import (
    DecodedObj,
    ObjTextLimits,
    decode_obj_text,
    encode_obj_text,
)
from surmap.objects3d.summary import (
    Neighbour,
    Obb,
    ObjectSummary,
    Relation,
    ShapeClass,
    UpAxis,
    neighbours,
    summarize,
)

__all__ = [
    "DecodedObj",
    "GlbHeader",
    "Neighbour",
    "Obb",
    "ObjTextLimits",
    "ObjectSummary",
    "Relation",
    "ShapeClass",
    "UpAxis",
    "decode_obj_text",
    "encode_obj_text",
    "neighbours",
    "read_glb_header",
    "summarize",
    "write_glb",
]
