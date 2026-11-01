"""``python -m surmap.mapqa ask|report|ask-voice|serve``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from surmap.mapqa.answers import MapAnswer
from surmap.mapqa.client import HttpTransport
from surmap.mapqa.errors import MapQaError
from surmap.mapqa.qa import MapQa
from surmap.mapqa.server import serve_mapqa

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main(
    argv: list[str] | None = None,
    *,
    transport: HttpTransport | None = None,
    api_key: str | None = None,
) -> int:
    """Run one subcommand. Returns a process status code."""
    parser = argparse.ArgumentParser(prog="surmap.mapqa")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="ask a question and print the JSON answer")
    ask.add_argument("--snapshot", required=True, type=Path)
    ask.add_argument("--question", required=True)

    report = sub.add_parser("report", help="print a Markdown situation report")
    report.add_argument("--snapshot", required=True, type=Path)

    voice = sub.add_parser("ask-voice", help="transcribe a WAV file, then ask")
    voice.add_argument("--snapshot", required=True, type=Path)
    voice.add_argument("--audio", required=True, type=Path)

    serve = sub.add_parser("serve", help="serve POST /ask for the local web viewer")
    serve.add_argument("--snapshot", required=True, type=Path)
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args(argv)
    try:
        qa = MapQa(args.snapshot, api_key=api_key, transport=transport)
        if args.command == "ask":
            _print_answer(qa.ask(args.question))
        elif args.command == "report":
            _print_report(qa.report())
        elif args.command == "ask-voice":
            _print_answer(qa.ask_voice(args.audio))
        elif args.command == "serve":
            serve_mapqa(qa, host=args.host, port=args.port)
        else:
            parser.error(f"unknown command {args.command}")
    except MapQaError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _print_answer(answer: MapAnswer) -> None:
    sys.stdout.write(json.dumps(answer.as_dict(), indent=2, ensure_ascii=False) + "\n")


def _print_report(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
