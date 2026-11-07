#!/usr/bin/env python3
"""Independent recomputation of the C2-C sealed metrics.

This script deliberately does NOT import the frozen evaluator, the acoustics
package or any truth helper.  It recomputes support, false rejection and the
accelerations taxonomy directly from the archived artifact and the frozen
truth tolerances, then asserts the published numbers.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "evidence" / "c2c-sealed" / "c2-repair.json.gz"

ALLOWED_CLAIM_STATUSES = {"supported_conditional", "undetermined", "contradicted"}
EXPECTED = {
    "B0": {"supported": (44, 426), "frr": (278, 406), "detected": (90, 120), "undetermined": (30, 120), "false_supported": 0},
    "B1": {"supported": (335, 426), "frr": (8, 406), "detected": (90, 120), "undetermined": (30, 120), "false_supported": 0},
    "B2": {"supported": (102, 426), "frr": (138, 406), "detected": (90, 120), "undetermined": (30, 120), "false_supported": 0},
    "B3": {"supported": (176, 426), "frr": (58, 406), "detected": (90, 120), "undetermined": (30, 120), "false_supported": 0},
}


def load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


def tolerances(artifact: dict) -> dict:
    for trial in artifact["trials"]:
        defs = trial.get("evaluation_only", {}).get("tolerance_definitions")
        if defs:
            return defs
    raise SystemExit("artifact carries no tolerance_definitions")


def correct(trial: dict, candidate: dict, tol: dict) -> bool:
    scenario = trial["evaluation_only"]["scenario"]
    params = candidate["params"]
    f0_rel = tol.get("f0_rel", 0.01)
    v_rel = tol.get("v_rel", 0.02)
    b_rel = tol.get("b_rel", 0.05)
    t0_abs = tol.get("t0_abs_s", tol.get("t0_abs", 0.25))
    return (
        abs(params["f0"] - scenario["f0"]) / scenario["f0"] <= f0_rel
        and abs(params["v"] - scenario["v"]) / scenario["v"] <= v_rel
        and abs(params["b"] - scenario["b"]) / scenario["b"] <= b_rel
        and abs(params["t0"] - scenario["t0"]) <= t0_abs
    )


def supported(candidate: dict) -> bool:
    if candidate.get("decision") != "accept":
        return False
    statuses = candidate.get("claim_statuses", {}) or {}
    if not statuses or not set(statuses.values()) <= ALLOWED_CLAIM_STATUSES:
        return False
    return "supported_conditional" in statuses.values()


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_ARTIFACT
    artifact = load(path)
    tol = tolerances(artifact)
    results = {}
    violations = 0
    for candidate_id in EXPECTED:
        sup_ok = sup_n = frr = correct_n = truth_correct_n = own_correct_n = detected = undetermined = false_supported = null_promoted = 0
        for trial in artifact["trials"]:
            candidate = trial["candidates"].get(candidate_id)
            if candidate is None:
                raise SystemExit(f"missing candidate {candidate_id}")
            statuses = set((candidate.get("claim_statuses") or {}).values())
            if statuses - ALLOWED_CLAIM_STATUSES:
                violations += 1
            is_correct = correct(trial, candidate, tol)
            artifact_label = bool(trial["evaluation_only"].get("truth_correct", False))
            mechanism = trial["mechanism"]
            if mechanism == "correct_cv":
                correct_n += 1
                if is_correct:
                    own_correct_n += 1
                if artifact_label:
                    truth_correct_n += 1
                    sup_n += 1
                    if supported(candidate):
                        sup_ok += 1
                    if candidate.get("adequacy_status") == "discrepancy" or candidate.get("decision") == "reject":
                        frr += 1
            elif mechanism == "acceleration":
                if candidate.get("decision") == "reject" and candidate.get("adequacy_status") == "discrepancy":
                    detected += 1
                elif candidate.get("decision") == "undetermined":
                    undetermined += 1
                elif candidate.get("decision") == "accept":
                    false_supported += 1
            elif mechanism == "null":
                if candidate.get("decision") == "accept" or supported(candidate):
                    null_promoted += 1
        result = {
            "supported": (sup_ok, correct_n),
            "own_correct": own_correct_n,
            "frr": (frr, truth_correct_n),
            "detected": (detected, detected + undetermined + false_supported),
            "undetermined": (undetermined, detected + undetermined + false_supported),
            "false_supported": false_supported,
            "null_promoted": null_promoted,
        }
        results[candidate_id] = result
        exp = EXPECTED[candidate_id]
        assert exp["supported"] == result["supported"], (candidate_id, "supported", result, exp)
        assert exp["frr"] == result["frr"], (candidate_id, "frr", result, exp)
        assert exp["detected"] == result["detected"], (candidate_id, "detected", result, exp)
        assert exp["undetermined"] == result["undetermined"], (candidate_id, "undetermined", result, exp)
        assert exp["false_supported"] == result["false_supported"], (candidate_id, "false_supported", result)
        assert result["null_promoted"] == 0, (candidate_id, "null", result)
    assert violations == 0, f"claim-status violations: {violations}"
    print(f"independent recomputation OK from {path}")
    for candidate_id, result in results.items():
        print(
            f"  {candidate_id}: supported {result['supported'][0]}/{result['supported'][1]}"
            f"  FRR {result['frr'][0]}/{result['frr'][1]}"
            f"  detected {result['detected'][0]}/{result['detected'][1]}"
            f"  undetermined {result['undetermined'][0]}  false_supported {result['false_supported']}  candidate-own-correct {result['own_correct']}"
        )
    print("  claim-status violations: 0; null promotions: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
