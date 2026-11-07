"""Frozen protocol for the Model Adequacy & Discrepancy layer (ADR 0015).

Everything that could be tuned lives here: test parameters, calibrated
thresholds, the calibration population, the clock model, the status
vocabularies, and the decision precedence.  Each entry carries a one-line
rationale.  The protocol digest is the SHA-256 of a canonical JSON dump of
:data:`PROTOCOL`; it is recorded in every artifact and is the frozen reference
for the Locked Validation layer.

The thresholds below were calibrated on the **Tuning layer only** (the nine E0
conditions listed in ``CALIBRATION_POPULATION``/``CALIBRATION_EXCLUDED``) and
then frozen.  The calibration margin and the resulting maxima are reproduced in
the tuning artifact's ``calibration`` block.  No threshold was adjusted after
the Locked layer was opened.

What this protocol can and cannot do (measured, ADR 0015 sections 3-5)
----------------------------------------------------------------------
E0's clock perturbations are *exact reparameterizations* of the nominal model:

    t_observed = alpha * t_physical + beta
    observed curve == nominal-model curve with
        f0 -> f0 / alpha,  v -> v,  t0 -> alpha*t0 + beta,  b -> alpha*b

so a clock offset and a clock rate error are observationally indistinguishable
from a clean recording of a source with rescaled parameters (verified in
``test_adequacy`` at ~1e-12 relative).  No test that uses only the recording
can separate them.  The protocol therefore declares the clock-degenerate
parameters (``f0``, ``t0``, ``b`` under an unknown clock) **not separately
identifiable**, and the epistemic decision for the declared physical-state
claim is ``undetermined`` unless an external clock reference exists.  This is
the ADR's "canonical case", and it is intentionally universal: the same
statement is true of a clean recording.  ``supported`` is reachable by design
only when the claim is restricted to clock-invariant content; that restriction
is a protocol decision the Lead must make explicitly.
"""

from __future__ import annotations

import hashlib
import json

# Parameter order used by the adequacy tests and the artifacts.
PARAM_ORDER = ("f0", "v", "t0", "b")

# Physical scales, identical to the hardened estimator's declaration.
PARAMETER_SCALES = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0}

# ---------------------------------------------------------------------------
# Calibration design
# ---------------------------------------------------------------------------

# Conditions used to calibrate the null distribution of every test.  These are
# the tuning conditions whose residual process is the nominal-model null:
# correct-model conditions, plus the two 20 dB clock conditions that are exact
# observational equivalences of a clean recording (their residuals are the
# nominal-model null at that noise level; this is logged deliberately).
CALIBRATION_POPULATION = (
    "snr_+5dB",          # correct model, noise-dominated regime (5 dB)
    "window_20s",        # correct model, different window
    "geom_v100_b300",    # correct model, different geometry
    "amp_geometric",     # correct model, amplitude variation
    "amp_mod30pct",      # correct model, amplitude modulation
    "clock_1000ppm",     # observationally equivalent to a clean recording (20 dB)
    "offset_0.3s",       # observationally equivalent to a clean recording (20 dB)
)

# Tuning conditions deliberately *not* used for threshold calibration.
CALIBRATION_EXCLUDED = {
    "accel_0.1": "known model-form mismatch (1.19% v / 2.89% b bias); would inflate thresholds",
    "null_noise_only": "no source; no nominal-model null exists; used only for the held-out-variance bound",
}

CALIBRATION_MARGIN = 1.3  # thresholds = max(calibration statistic) * margin
CALIBRATION_TRIALS_PER_CONDITION = 100

# ---------------------------------------------------------------------------
# Frozen thresholds (calibrated from the Tuning layer; see the artifact)
# ---------------------------------------------------------------------------

PROTOCOL = {
    "protocol_version": "adeq-1.0.0",
    "layer": "model-adequacy-and-discrepancy",
    "authority": "ADR 0015 sections 3-6",
    "declared_claim": (
        "the fitted physical state (f0, v, t0, b) of a straight-line "
        "constant-velocity acoustic source, under the nominal clock assumption"
    ),
    "clock_model": "t_observed = alpha * t_physical + beta",
    "clock_equivalence": {
        "statement": (
            "alpha,b are not separately identifiable from (f0,t0,b); a clock "
            "excursion is exactly a nominal-model reparameterization, so a "
            "recording cannot distinguish clock error from a different source state"
        ),
        "invariant_parameter": "v",
        "degenerate_parameters": ["f0", "t0", "b"],
        "required_external_measurement": (
            "an absolute time reference or calibrated clock trace; without it "
            "the physical event time and the f0/b scale are undetermined"
        ),
    },
    "parameter_scales": dict(PARAMETER_SCALES),
    "calibration": {
        "population": list(CALIBRATION_POPULATION),
        "excluded": dict(CALIBRATION_EXCLUDED),
        "margin": CALIBRATION_MARGIN,
        "trials_per_condition": CALIBRATION_TRIALS_PER_CONDITION,
        "rationale": (
            "threshold = calibration max * 1.3 on the nominal-model-null "
            "population; 1.3 is a declared false-positive margin, not a target"
        ),
    },
    "tests": {
        "standardized_residuals": {
            "rms_bounds": [0.50, 1.50],
            "robust_scale_ratio_bounds": [0.5888553080421093, 1.5607995612350736],
            "max_abs_z_max": 8.836590088010263,
            "tail_fraction_abs_z_gt_3_max": 0.014567769477054428,
            "abs_excess_kurtosis_max": 2.7168916887131105,
            "rationale": (
                "rms is ~1 by construction (sigma_f is the fit's own scale), so "
                "the informative statistics are the robust-scale ratio, tails "
                "and kurtosis; bounds are calibration max * margin"
            ),
        },
        "autocorrelation": {
            "lags": [1, 2, 3, 5, 8, 13, 21, 34, 55, 89],
            "ljung_box_order": 89,
            "ljung_box_df": 85,
            "ljung_box_statistic_max": 7671.565001358366,
            "max_abs_acf_max": 1.0216147160003164,
            "decided_by": "ljung_box_statistic",
            "rationale": (
                "LB aggregates the declared lags; df = order - 4 fitted "
                "parameters, and the calibrated threshold replaces the "
                "asymptotic p<0.05 rule (which is not used). ACF is reported "
                "as per-lag evidence but the 20 dB front-end bias already "
                "produces ACF ~0.78 on clean data, so it cannot be the gate"
            ),
        },
        "time_structure": {
            "abs_corr_time_max": 0.07471727010660516,
            "abs_quadratic_coefficient_max": 0.18966674077894527,
            "abs_phase_correlation_max": 0.14312644659907517,
            "rationale": (
                "omitted dynamics (acceleration) leave a smooth trend; the "
                "quadratic coefficient is normalized by sigma_f and by the "
                "unit-variance time coordinate, the phase correlation is with "
                "the model-predicted Doppler phase"
            ),
        },
        "block_prediction": {
            "n_blocks": 5,
            "heldout_normalized_rmse_max": 1.4061367132434965,
            "heldout_explained_fraction_min": 0.500,
            "rationale": (
                "K=5 contiguous blocks; each block is held out and the model is "
                "re-refined from the full-fit solution on the remaining blocks "
                "(local refinement, deterministic); decision statistic is the "
                "MEDIAN block-normalized RMSE (one ill-conditioned block must "
                "not decide), and the explained-fraction floor catches a fit "
                "that explains none of the held-out variation (null)"
            ),
        },
        "degeneracy": {
            "worst_rel_se_max": 0.01,
            "condition_number_max": 10000.0,
            "clock_null_ratio_max": 1.0e-10,
            "clock_profile_flatness_max": 1.0e-4,
            "alpha_perturbation": 1.0e-3,
            "beta_perturbation_s": 0.05,
            "rationale": (
                "nominal gate follows ADR 0013 section 2 (worst_rel_se<=1e-2, "
                "condition<=1e4); the clock null-space test uses the scaled "
                "6-parameter Gauss-Newton information matrix and requires the "
                "smallest normalized eigenvalue to be ~0, confirmed by a flat "
                "profile along the analytic null direction"
            ),
        },
    },
    "decision": {
        "test_statuses": ["pass", "fail", "indeterminate"],
        "margin_fraction": 0.10,
        "margin_rationale": (
            "a statistic within +-10% of a threshold is reported indeterminate "
            "rather than decided (ADR 0013 section 3 boundary stability)"
        ),
        "model_adequacy_precedence": [
            "distribution test fail -> insufficient_evidence (noise scale untrustworthy)",
            "distribution test indeterminate -> indeterminate",
            "any structure/prediction test fail -> discrepancy",
            "any structure/prediction test indeterminate -> indeterminate",
            "otherwise -> adequate",
        ],
        "identifiability_values": [
            "identifiable",
            "not_separately_identifiable",
            "insufficient_evidence",
        ],
        "identifiability_precedence": [
            "optimization not converged, or sigma_f unavailable -> insufficient_evidence",
            "nominal gate fail (worst_rel_se>1e-2 or condition>1e4) -> insufficient_evidence",
            "clock null space detected -> not_separately_identifiable",
            "otherwise -> identifiable",
        ],
        "epistemic_precedence": [
            "optimization_status != converged -> undetermined (reason optimization_*)",
            "model_adequacy_status == discrepancy -> rejected (model_discrepancy)",
            "model_adequacy_status in {insufficient_evidence, indeterminate} -> undetermined",
            "identifiability_status != identifiable -> undetermined",
            "otherwise -> supported",
        ],
        "epistemic_rationale": (
            "a physical conclusion requires stable optimization, adequate model "
            "form, and identifiable parameters; under an unknown clock the "
            "declared physical-state claim is not identifiable, so it is "
            "undetermined rather than either accepted or rejected"
        ),
    },
}


def _canonical_json(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def protocol_digest(document=None) -> str:
    """SHA-256 of the canonical protocol document (frozen reference)."""
    return hashlib.sha256(_canonical_json(PROTOCOL if document is None else document)).hexdigest()


PROTOCOL_DIGEST = protocol_digest()


def test_thresholds(name: str):
    """The declared thresholds of one test (read-only view)."""
    return PROTOCOL["tests"][name]
