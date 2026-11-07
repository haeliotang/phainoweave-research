import argparse
import json
from pathlib import Path

from .curve import bootstrap_matched_difference, build_curve, matched_risk


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="C3 risk-coverage over a C2-C artifact (analysis only)")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--candidates", default="B0,B1,B2,B3")
    parser.add_argument("--mechanism", default="correct_cv")
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args(argv)
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    trials = artifact["trials"]
    candidates = [c.strip() for c in args.candidates.split(",") if c.strip()]
    curves = {c: build_curve(trials, c, args.mechanism) for c in candidates}
    matched = matched_risk(curves, baseline="B0" if "B0" in curves else None)
    boot = None
    if "B1" in curves and "B0" in curves:
        boot = bootstrap_matched_difference(trials, "B1", "B0", args.mechanism)
    report = {
        "artifact": str(args.artifact),
        "mechanism": args.mechanism,
        "candidates": candidates,
        "curves": curves,
        "matched_risk": matched,
        "bootstrap_B1_minus_B0": boot,
        "note": "post-hoc selective-prediction analysis of existing adequacy statistics; not the frozen decision rule",
    }
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n")
    if args.markdown:
        lines = ["# C3 risk–coverage", "", f"Mechanism: `{args.mechanism}`", "", "| Candidate | n | wrong | matched risk @25/50/75/90% |", "|---|---:|---:|---|"]
        for c in candidates:
            vals = matched["risk"][c]
            lines.append(f"| {c} | {curves[c]['n']} | {curves[c]['n_wrong']} | " + " / ".join("n/a" if v is None else f"{v:.3f}" for v in vals) + " |")
        if boot:
            lines += ["", "## B1 − B0 matched-risk difference (bootstrap over trials)", "", "| Coverage | Δrisk | 95% CI |", "|---:|---:|---|"]
            for cov, row in boot["difference"].items():
                if row is None:
                    lines.append(f"| {cov} | n/a | n/a |")
                else:
                    lines.append(f"| {cov} | {row['mean']:+.4f} | [{row['ci95'][0]:+.4f}, {row['ci95'][1]:+.4f}] |")
        lines += ["", "This is a post-hoc analysis of existing adequacy statistics; it does not change the frozen B0-B3 decision rule."]
        Path(args.markdown).write_text("\n".join(lines) + "\n")
    print(f"risk-coverage: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
