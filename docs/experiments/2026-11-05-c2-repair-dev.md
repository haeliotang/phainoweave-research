# C2 repair development comparison — B0–B3 on a development grid

**Status:** development comparison complete; NOT a confirmation; sealed grid unopened; candidates not selected · 2026-11-05 · **Authority:** [ADR 0022](../decisions/0022-candidate-classification-and-sealed-run.md), [ADR 0020](../decisions/0020-measurement-model-and-c2-repair.md) · **Prior:** [C2-M2](2026-11-05-c2m2-conditional-error.md)

## 1. What ran

Development grid `pr4e-c2-dev-repair-v1` (not the sealed grid): 36 cells / 124 trials — correct-CV continuum 64 (8 geometries 150–6500 m × 2 speeds × 20 dB, N=4), correct-CV low SNR 18, acceleration 36 (geometry 600/3000 m × accel 0.15/0.30/0.50), noise-only 6. Evaluation seeds base 90M, calibration seeds base 91M; disjoint from all prior bases. Calibration: 80/80 admissible correct-model trials. Frozen adequacy protocol digest unchanged (`c86cb63d…`); B2/B3 change *candidate-local* thresholds/null distributions only (`thresholds_changed = true` for B2/B3), which is exactly why ADR 0022 classifies them as test/calibration changes.

Candidates: B0 original; B1 de-chirp (compensate the candidate CV model's predicted phase before re-extraction; same estimator re-fit on the repaired track); B2 AR(8) residual pre-whitening (replaces only the Ljung–Box dependence test); B3 conditional calibration of LB/time-structure/block thresholds from runtime-observable chirp-rate × estimated-SNR cells.

## 2. Development result

| Candidate | FRR, all correct-CV | FRR, high-chirp subset | Acceleration detection | Abstention |
|---|---:|---:|---:|---:|
| B0 | 55/82 (67.1%) | 12/25 (48.0%) | 27/36 (75.0%) | 14/124 (11.3%) |
| **B1 de-chirp** | **0/82 (0.0%)** | **0/25 (0.0%)** | 27/36 (75.0%) | 9/124 (7.3%) |
| B2 pre-whitening | 27/82 (32.9%) | 8/25 (32.0%) | 27/36 (75.0%) | 12/124 (9.7%) |
| **B3 conditional calibration** | **0/82 (0.0%)** | **0/25 (0.0%)** | 27/36 (75.0%) | 14/124 (11.3%) |

Independent paired evaluator on the artifact (matched observations, Bx−B0):

| Candidate | FRR delta | Detection delta | Claim-integrity violations | Negative-result flag |
|---|---:|---:|---:|---|
| B1 | −0.6707 | 0.0000 | 0 | false |
| B2 | −0.3415 | 0.0000 | 0 | false |
| B3 | −0.6707 | 0.0000 | 0 | false |

Claim statuses (`supported_conditional`; all others undetermined; no contradicted, no `supported_invariant`): B0 v 10 / f0·b 7 / t0 12; B1 **43 / 31 / 60**; B2 18 / 15 / 20; B3 26 / 23 / 43. The C1 gate was not bypassed; more claims pass because the observation representation or calibration changed, and this must be read together with the candidate class (ADR 0022).

## 3. Interpretation — and why this is not a winner

- **B1 is the only measurement-representation repair in the set.** It removes the front end's bias by compensating the model-predicted frequency history. Detection is unchanged (27/36). It re-fits the same estimator on the repaired track, so its parameters are not directly comparable to B0; this is reported, not hidden.
- **B3 reaches 0/82 by conditioning thresholds/zero distributions on runtime-observable chirp rate.** That is a calibration change, not a measurement fix. It is operationally attractive and scientifically weaker; the sealed run must test whether it generalises to unseen geometry. It also changes its own thresholds (`thresholds_changed = true`), the exact risk ADR 0020 flagged.
- **B2 only partially corrects the dependence** (67.1% → 32.9%; high-chirp still 32%). Its whitening threshold (12683) is much larger than the whitened median (215) under the max×1.3 calibration on 80 trials, so it cannot remove most of the inflated LB statistic.
- **Acceleration detection is 27/36 for every candidate.** The 9 missing cells are all `b=600 m, v=250 m/s`, where the frozen distribution test returns `insufficient_evidence` (not `reject`). This is **undecided**, not detection loss, and no candidate caused it; the sealed analysis must report it separately (ADR 0022 §3).
- These are development numbers with 124 trials and wide paired intervals; **0/82 is not evidence that the population FRR is zero**. B1 is a hypothesis for the sealed confirmation, not an accepted repair.

## 4. Deviations and limitations

1. The development run changed once after its first artifact (decision mapping adequacy vs epistemic; B3 threshold coverage extended). The evaluation conditions/seeds did not change, but the final code is what gets frozen; this is recorded rather than presented as a pristine single run.
2. B3's SNR conditioning did not activate: the estimated-SNR proxy saturated on this grid (all cells in one SNR bin), so only chirp-rate conditioning was exercised. Stated limitation.
3. B2 and B3 share one calibration sample (independent candidates, not a combination).
4. B1 de-chirps only the CV model's predicted frequency history; true acceleration remains as a residual slope, which is why detection is preserved on this grid.
5. Local environment only (macOS arm64, Python 3.14, NumPy 2.4.4); no cross-platform claim for repair artifacts.
6. The sealed grid `pr4e-c2c-v1` (566 trials) was not opened and was not used for any parameter choice.
7. Claim support counts under B1/B3 must not be read as new physical knowledge: C1's L2 (sound-speed identifiability) is unchanged; more conditional support is a measurement-adequacy effect.

## 5. Next step (sealed run rule)

Freeze candidate code, calibration samples, evaluation rules, tolerances and the detection-loss bound (with an undecided-trial policy), hash them, then run `pr4e-c2c-v1` once per frozen candidate set and evaluate with `phaino_c2_eval`. B3 must be reported as calibration, B1 as measurement repair; the reference estimator remains outside the competition. If no candidate improves rejection without detection loss and abstention gaming, the predefined negative result stands: representation insufficiency.

## 6. Provenance

Artifact: `/tmp/c2-repair-dev/c2-repair.json` (sha `1392b3d2…`, 2.09 MB), `c2-repair-summary.md`; `protocol_digest a1d56b94…`, `frozen_grid_digest b0e381fa…`, `environment_id dev-f3766ef64295`, `measurement_model_id e0-frontend-hann-stft-512-256@1.0.0`, `gate_policy_digest b1379457…`, `detection_loss_bound 0.10`. Code: `python/phaino_acoustics/repair_candidates.py`, `experiment_repair.py`; tests `test_repair_candidates.py` (15). Evaluator: `phaino_c2_eval`.
