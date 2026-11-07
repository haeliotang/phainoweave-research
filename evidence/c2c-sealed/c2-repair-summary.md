# C2 repair development run (B0-B3)

- experiment: `c2-repair`
- grid: `pr4e-c2c-v1` / `2978c8b24d0ef1bd3b787f13f68431230720154a288575a41067c8ad4c26eeaf`
- protocol: `b61db06d81b473798693446b0d08d6769c1ddbf25a0f432e43789ff1523cbb16`
- environment: `dev-f3766ef64295`
- measurement model: `e0-frontend-hann-stft-512-256@1.0.0`
- detection_loss_bound (pre-registered): 0.1
- undecided_policy: not_detected
- primary_endpoint: correct_cv_supported_coverage_and_detection_B1_vs_B0 (B1 vs B0 (paired on the same observation; B0 is the paired baseline))
- thresholds_changed: True (B2, B3)
- cells / trials: 59 / 566
- truth-correct by mechanism: {'correct_cv': 406, 'acceleration': 0, 'null': 0}
- high-chirp definition: {'observable': 'estimated_chirp_rate_hz_s', 'threshold_hz_s': 150.0, 'n_trials': 128}

| candidate | FRR correct-CV | FRR high-chirp | detection acceleration | abstention |
|---|---|---|---|---|
| B0 | 278/406 (68.5%) | 77/128 (60.2%) | 90/120 (75.0%) | 62/566 (11.0%) |
| B1 | 8/406 (2.0%) | 8/128 (6.2%) | 90/120 (75.0%) | 33/566 (5.8%) |
| B2 | 138/406 (34.0%) | 47/128 (36.7%) | 90/120 (75.0%) | 83/566 (14.7%) |
| B3 | 58/406 (14.3%) | 28/128 (21.9%) | 90/120 (75.0%) | 72/566 (12.7%) |

Descriptive development counts; not an acceptance decision.
