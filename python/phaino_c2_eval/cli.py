"""CLI for the independent C2 paired evaluator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .artifacts import ArtifactError, load_artifacts
from .evaluate import evaluate
from .metrics import select_candidates
from .report import report_json, report_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m phaino_c2_eval",
        description=(
            "Independent paired evaluation of C2 repair candidates B0-B3 on identical "
            "trials. Artifact-only: no acoustics imports and no candidate recommendation."
        ),
    )
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        help="C2 repair artifact JSON; repeat for multiple environments",
    )
    parser.add_argument(
        "--candidates",
        help="comma-separated candidate ids from the artifact (default: all declared); must include B0",
    )
    parser.add_argument(
        "--require-paired",
        action="store_true",
        help=(
            "fail unless all environments declare identical candidates and trial identities "
            "and every trial contains every selected candidate"
        ),
    )
    parser.add_argument("--out", required=True, help="report.json path")
    parser.add_argument("--markdown", required=True, help="report.md path")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    try:
        artifacts = load_artifacts(args.artifact, require_paired=args.require_paired)
        requested = (
            tuple(part.strip() for part in args.candidates.split(",") if part.strip())
            if args.candidates
            else None
        )
        selected = select_candidates(artifacts[0], requested)
        if not any(candidate != "B0" for candidate in selected):
            raise ArtifactError("--candidates must include at least one non-B0 candidate")
        document = evaluate(artifacts, selected, require_paired=args.require_paired)
        _write(args.out, report_json(document))
        _write(args.markdown, report_markdown(document))
    except (ArtifactError, ValueError) as error:
        print(f"c2-eval error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"report error: {error}", file=sys.stderr)
        return 2

    print(f"environments: {len(artifacts)}")
    print(f"candidates: {', '.join(selected)}")
    print(f"negative_result_holds: {document['negative_result']['negative_result_holds']}")
    for candidate in selected:
        if candidate == "B0":
            continue
        delta = document["paired"][candidate]["overall"]["false_rejection"]["risk_difference"]
        detection = document["paired"][candidate]["overall"]["detection"]["risk_difference"]
        print(
            f"{candidate}: FRR delta={_fmt(delta)} detection delta={_fmt(detection)} "
            f"claim violations={document['claim_integrity'][candidate]['n_violations']}"
        )
    print(f"report: {args.out}")
    print(f"markdown: {args.markdown}")
    return 0


def _write(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
