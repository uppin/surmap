"""Regenerate the survey agent's protobuf bindings and descriptor set from `proto/`.

The protos live in `proto/surmap/agent/v1/` (package `surmap.agent.v1`); the
generated modules and the descriptor set are checked in at
`src/surmap/agent/proto/`. Regenerate them after editing any of the protos:

    uv run --with grpcio-tools==1.73.1 python scripts/gen_agent_rpc.py

The descriptor set is compiled with source info, because the rpc and field
comments are the tool and argument descriptions the model reads
(`surmap.agent.contracts`).

The grpcio-tools version is pinned: its protoc must not emit gencode
newer than the project's protobuf runtime (`protobuf>=6.33,<7`).
"""

from __future__ import annotations

import pathlib
import re
import shutil
import tempfile

import grpc_tools
from grpc_tools import protoc

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROTOS = ("execution", "survey_tools", "jobs", "chat")
PROTO_PACKAGE_DIR = "surmap/agent/v1"
OUT = ROOT / "src/surmap/agent/proto"
DESCRIPTOR_SET = OUT / "agent_descriptor_set.binpb"
_MODULE_LEVEL_CLASSVAR = re.compile(r"^([A-Z0-9_]+_FIELD_NUMBER): _ClassVar\[int\]$", re.MULTILINE)


def main() -> int:
    well_known = pathlib.Path(grpc_tools.__file__).parent / "_proto"
    sources = [f"{PROTO_PACKAGE_DIR}/{name}.proto" for name in PROTOS]
    with tempfile.TemporaryDirectory() as scratch:
        code: int = protoc.main(
            [
                "grpc_tools.protoc",
                f"--proto_path={ROOT / 'proto'}",
                f"--proto_path={well_known}",
                f"--python_out={scratch}",
                f"--pyi_out={scratch}",
                f"--descriptor_set_out={DESCRIPTOR_SET}",
                "--include_source_info",
                "--include_imports",
                *sources,
            ]
        )
        if code != 0:
            return code
        generated = pathlib.Path(scratch) / PROTO_PACKAGE_DIR
        for name in PROTOS:
            for suffix in ("_pb2.py", "_pb2.pyi"):
                target = OUT / f"{name}{suffix}"
                shutil.copyfile(generated / f"{name}{suffix}", target)
                _relocate(target)
            _fix_pyi(OUT / f"{name}_pb2.pyi")
    return 0


def _relocate(path: pathlib.Path) -> None:
    """Point the generated imports at `surmap.agent.proto`, where the modules are checked in.

    Only import statements and module names are rewritten: the serialized descriptors keep the
    proto package `surmap.agent.v1`.
    """
    text = path.read_text(encoding="utf-8")
    text = text.replace("from surmap.agent.v1 import ", "from surmap.agent.proto import ")
    text = text.replace("'surmap.agent.v1.", "'surmap.agent.proto.")
    path.write_text(text, encoding="utf-8")


def _fix_pyi(pyi: pathlib.Path) -> None:
    """Make the generated stub pass mypy strict.

    Bare `Mapping` gets its type arguments, and a top-level extension's field number (which
    protoc annotates `ClassVar` outside any class) becomes a plain `int`.
    """
    text = pyi.read_text(encoding="utf-8")
    text = _MODULE_LEVEL_CLASSVAR.sub(r"\1: int", text)
    if "_Mapping]" in text:
        text = text.replace("_Mapping]", "_Mapping[str, _Any]]")
        text = text.replace(
            "from typing import ClassVar as _ClassVar,",
            "from typing import Any as _Any, ClassVar as _ClassVar,",
        )
    pyi.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
