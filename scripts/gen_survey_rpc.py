"""Regenerate the survey protobuf bindings from `proto/`.

The generated module is checked in at
`src/surmap/survey/v1/survey_pb2.py`. Regenerate it after editing
`proto/surmap/survey/v1/survey.proto`:

    uv run --with grpcio-tools==1.73.1 python scripts/gen_survey_rpc.py

The grpcio-tools version is pinned: its protoc must not emit gencode
newer than the project's protobuf runtime (`protobuf>=6.33,<7`).
"""

from __future__ import annotations

import pathlib

import grpc_tools
from grpc_tools import protoc

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    well_known = pathlib.Path(grpc_tools.__file__).parent / "_proto"
    code: int = protoc.main(
        [
            "grpc_tools.protoc",
            f"--proto_path={ROOT / 'proto'}",
            f"--proto_path={well_known}",
            f"--python_out={ROOT / 'src'}",
            f"--pyi_out={ROOT / 'src'}",
            "surmap/survey/v1/survey.proto",
        ]
    )
    if code == 0:
        _fix_pyi()
    return code


def _fix_pyi() -> None:
    """Give the generated stub's bare `Mapping` its type arguments."""
    pyi = ROOT / "src/surmap/survey/v1/survey_pb2.pyi"
    text = pyi.read_text(encoding="utf-8")
    text = text.replace("_Mapping]", "_Mapping[str, Any]]")
    text = text.replace(
        "from typing import ClassVar as _ClassVar,",
        "from typing import Any as _Any, ClassVar as _ClassVar,",
    )
    text = text.replace("_Mapping[str, Any]]", "_Mapping[str, _Any]]")
    pyi.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
