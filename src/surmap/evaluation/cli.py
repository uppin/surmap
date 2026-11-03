"""``scripts/eval_disaster_labelling.py``: LADI v2 per-class F1 for the Muse clients.

A model call needs the provider's live flag (``SURMAP_LIVE_META=1``,
``SURMAP_LIVE_BASETEN=1``, or ``SURMAP_LIVE_MODAL=1``) and its key or URL.
``--provider modal`` scores SAM 3.1 on Modal with one text prompt per
class (``surmap.evaluation.sam_ladi``), only on the classes it has a
prompt for. ``--limit`` may not exceed
``SURMAP_EVAL_MAX_IMAGES`` (default 20), and the usual
``SURMAP_BUDGET_<PROVIDER>_CALLS`` / ``_TOKENS`` caps apply per call.
``--download-only`` fetches and caches images without any model call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from surmap.evaluation.ladi import (
    BasetenLadiClassifier,
    LadiClassifier,
    LadiError,
    LadiSample,
    MetaLadiClassifier,
    evaluate,
    load_samples,
    render_table,
    report_json,
)
from surmap.evaluation.sam_ladi import ModalSamLadiClassifier

DEFAULT_MAX_IMAGES = 20
_LIVE_FLAGS = {
    "meta": "SURMAP_LIVE_META",
    "baseten": "SURMAP_LIVE_BASETEN",
    "modal": "SURMAP_LIVE_MODAL",
}
_KEYS = {"meta": "MODEL_API_KEY", "baseten": "BASETEN_API_KEY", "modal": "MODAL_SAM_URL"}

ClassifierFactory = Callable[[str], LadiClassifier]
SampleLoader = Callable[..., list[LadiSample]]


class EvalConfigError(RuntimeError):
    """A flag, key, or budget refuses the run before any call is sent."""


def max_images() -> int:
    raw = os.environ.get("SURMAP_EVAL_MAX_IMAGES", "").strip()
    if not raw:
        return DEFAULT_MAX_IMAGES
    try:
        value = int(raw)
    except ValueError as exc:
        raise EvalConfigError(f"SURMAP_EVAL_MAX_IMAGES must be an integer, got {raw!r}") from exc
    if value < 1:
        raise EvalConfigError("SURMAP_EVAL_MAX_IMAGES must be at least 1")
    return value


def check_live(providers: Sequence[str], limit: int) -> None:
    """Refuse before downloading when a flag, key, or the image budget is missing."""
    cap = max_images()
    if limit > cap:
        raise EvalConfigError(
            f"--limit {limit} is above SURMAP_EVAL_MAX_IMAGES={cap}; raise it deliberately"
        )
    for provider in providers:
        flag = _LIVE_FLAGS[provider]
        if os.environ.get(flag, "").strip() != "1":
            raise EvalConfigError(f"{provider} needs {flag}=1 for a live model call")
        if not os.environ.get(_KEYS[provider], "").strip():
            raise EvalConfigError(f"{provider} needs {_KEYS[provider]}")


def default_classifier(provider: str, reasoning_effort: str = "low") -> LadiClassifier:
    """Live classifier; ``medium`` and ``high`` effort get a bigger Baseten budget."""
    if provider == "meta":
        return MetaLadiClassifier(reasoning_effort=reasoning_effort)
    if provider == "baseten":
        max_tokens = 4096 if reasoning_effort == "low" else 8192
        return BasetenLadiClassifier(reasoning_effort=reasoning_effort, max_tokens=max_tokens)
    if provider == "modal":
        return ModalSamLadiClassifier()
    raise EvalConfigError(f"unknown provider {provider!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("meta", "baseten", "modal", "both"),
        default="meta",
        help="which model to score: Muse clients or SAM 3.1 on Modal (default meta)",
    )
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--limit", type=int, default=10, help="images to score (default 10)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high"),
        default="low",
        help="model reasoning effort for both providers (default low)",
    )
    parser.add_argument(
        "--download-only", action="store_true", help="fetch and cache images; no model call"
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    loader: SampleLoader = load_samples,
    classifier_factory: ClassifierFactory = default_classifier,
) -> int:
    args = build_parser().parse_args(argv)
    providers = ["meta", "baseten"] if args.provider == "both" else [args.provider]
    try:
        if not args.download_only:
            check_live(providers, args.limit)
        samples = loader(args.limit, split=args.split, offset=args.offset, cache_dir=args.cache_dir)
    except (EvalConfigError, LadiError, OSError) as exc:
        print(f"eval_disaster_labelling: {exc}", file=sys.stderr)
        return 2
    if args.download_only:
        print(f"cached {len(samples)} LADI v2 {args.split} images")
        return 0
    reports: list[dict[str, object]] = []
    for provider in providers:
        if classifier_factory is default_classifier:
            classifier = default_classifier(provider, args.reasoning_effort)
        else:
            classifier = classifier_factory(provider)

        def on_error(sample: LadiSample, exc: Exception) -> None:
            print(f"  image {sample.index}: {type(exc).__name__}: {exc}", file=sys.stderr)

        scored = samples
        classes = getattr(classifier, "classes", None)
        if isinstance(classes, frozenset):
            scored = [LadiSample(s.split, s.index, s.jpeg, s.labels & classes) for s in samples]
        scores, rows = evaluate(scored, classifier, on_error=on_error)
        print(render_table(scores, provider=provider, model=classifier.model))
        report = report_json(scores, provider=provider, model=classifier.model)
        report["split"] = args.split
        report["offset"] = args.offset
        report["reasoning_effort"] = args.reasoning_effort
        report["rows"] = rows
        reports.append(report)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"reports": reports}, indent=2) + "\n", encoding="utf-8")
    return 0
