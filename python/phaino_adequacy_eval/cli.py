"""CLI for the independent adequacy evaluation harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .artifacts import (
    AdequacyArtifactError,
    embedded_old_decisions,
    load_adequacy_artifact,
    load_old_decisions,
)
from .report import build_report_document, report_json, report_markdown


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns 0 on success, 2 on usage/artifact/IO failure."""
    parser = argparse.ArgumentParser(
        prog="python -m phaino_adequacy_eval",
        description=(
            "Independent artifact-only evaluation of the model-adequacy layer: "
            "truth-based risk, valid-retention, abstention, and matched-retention "
            "comparison against the hardened decision rule."
        ),
    )
    parser.add_argument("--new", required=True, help="adequacy artifact JSON")
    parser.add_argument(
        "--new-rule",
        choices=("epistemic", "conditional"),
        default="epistemic",
        help=(
            "new decision rule: 'epistemic' uses epistemic_decision == supported; "
            "'conditional' uses adequacy.tests.degeneracy.conditional_claim_supported"
        ),
    )
    parser.add_argument(
        "--hardened",
        help="hardened artifact with old-rule decisions (optional; embedded decisions are used otherwise)",
    )
    parser.add_argument(
        "--old-artifact",
        help="alternative artifact carrying old-rule decisions (mutually exclusive with --hardened)",
    )
    parser.add_argument("--out", required=True, help="deterministic JSON report path")
    parser.add_argument("--markdown", required=True, help="markdown report path")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.hardened and args.old_artifact:
        print("error: --hardened and --old-artifact are mutually exclusive", file=sys.stderr)
        return 2

    try:
        artifact = load_adequacy_artifact(args.new)
        if args.hardened:
            old_decisions, field = load_old_decisions(args.hardened)
            source = args.hardened
        elif args.old_artifact:
            old_decisions, field = load_old_decisions(args.old_artifact)
            source = args.old_artifact
        else:
            old_decisions, field = embedded_old_decisions(artifact)
            source = "embedded in --new artifact"
        required_keys = {(trial["condition"], trial["trial"]) for trial in artifact.trials}
        missing = sorted(required_keys - set(old_decisions))
        extra = sorted(set(old_decisions) - required_keys)
        if missing or extra:
            raise AdequacyArtifactError(
                "old-rule decisions do not cover the adequacy trials: "
                f"missing={len(missing)} extra={len(extra)}"
            )
        report = build_report_document(
            artifact, old_decisions, field, source, new_rule=args.new_rule
        )
        _write(args.out, report_json(report))
        _write(args.markdown, report_markdown(report))
    except AdequacyArtifactError as error:
        print(f"artifact error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"report error: {error}", file=sys.stderr)
        return 2
    print(f"trials: {len(artifact.trials)}")
    print(f"new rule: {args.new_rule}")
    print(f"report: {args.out}")
    print(f"markdown: {args.markdown}")
    return 0


def _write(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
