"""CLI for the independent C2-M2 predictive model check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .artifacts import ArtifactError, load_artifact
from .evaluate import evaluate
from .metrics import BOOTSTRAP_REPLICATES
from .report import report_json, report_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m phaino_c2_modelcheck",
        description=(
            "Independent predictive measurement-error model check for C2-M2. "
            "Artifact-only: no acoustics imports, no candidate/model selection."
        ),
    )
    parser.add_argument("--artifact", required=True, help="C2-M2 artifact JSON")
    parser.add_argument("--out", required=True, help="report.json path")
    parser.add_argument("--markdown", required=True, help="report.md path")
    parser.add_argument(
        "--bootstrap-replicates",
        type=int,
        default=BOOTSTRAP_REPLICATES,
        help="deterministic cluster-bootstrap replicates (default 1000)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.bootstrap_replicates < 1:
        print("error: --bootstrap-replicates must be positive", file=sys.stderr)
        return 2
    try:
        artifact = load_artifact(args.artifact)
        document = evaluate(artifact, bootstrap_replicates=args.bootstrap_replicates)
        _write(args.out, report_json(document))
        _write(args.markdown, report_markdown(document))
    except ArtifactError as error:
        print(f"c2-m2 artifact error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"report error: {error}", file=sys.stderr)
        return 2

    print(f"measurement_model_id: {artifact.measurement_model_id}")
    print(f"models: {', '.join(artifact.models)}")
    print(
        "held-out cells: {}; independent units: {}".format(
            len(artifact.heldout_cells),
            sum(cell.n_independent_units for cell in artifact.heldout_cells),
        )
    )
    print(
        "passing models: {}".format(
            ", ".join(document["generalisation"]["passing_models"]) or "none"
        )
    )
    print(f"negative_result_holds: {document['generalisation']['negative_result_holds']}")
    print(f"report: {args.out}")
    print(f"markdown: {args.markdown}")
    return 0


def _write(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
