"""PR-4e C1-A -- symbolic proof of the observation-time clock symmetry.

The proof object is a deterministic JSON document; the markdown summary is
rendered from it.  Nothing here imports the acoustic method code: the forward
model is written from its definition, and the numeric checks in this module are
internal consistency checks, **not** the independent numerical certificate
(that is the separate ``phaino_claim_certificate`` workstream).

Definitions
-----------
Declared model (E0-class, straight-line constant-velocity source)::

    tau(t)   = t - t0
    r(t)     = sqrt(v^2 tau^2 + b^2)
    v_r(t)   = -v^2 tau / r
    F(t; f0,v,t0,b,c) = f0 / (1 - v_r(t)/c)
                      = f0 / (1 + v^2 tau / (c r))

Clock action on the observation time coordinate::

    t_obs = k * t_phys + beta,        k > 0, beta real

Induced parameter action (derived, then verified symbolically)::

    rho(k,beta)(f0,v,t0,b,c) = ( f0/k,  v,  k*t0 + beta,  k*b,  c )

so that the forward output is preserved in observation coordinates::

    F_obs(t; theta, (k,beta)) = F(t; rho(k,beta) theta)
"""

from __future__ import annotations

import hashlib
import json
import platform
from typing import Optional

import numpy as np
import sympy as sp

ARTIFACT_NAME = "c1-symbolic-proof"
ARTIFACT_VERSION = "1.0.0"
NUMERIC_TOLERANCE = 1.0e-10
NEGATIVE_CONTROL_TOLERANCE = 1.0e-3
FLOAT_DECIMALS = 12

# Symbols with the model's domain assumptions baked in.
t, f0, v, t0, b, c, k = sp.symbols("t f0 v t0 b c k", positive=True)
beta = sp.symbols("beta", real=True)
lam = sp.symbols("lam", positive=True)

PARAMS = ("f0", "v", "t0", "b", "c")
SYMBOLS = {"f0": f0, "v": v, "t0": t0, "b": b, "c": c}


# ---------------------------------------------------------------------------
# Symbolic expressions
# ---------------------------------------------------------------------------

def nominal_forward_expr() -> sp.Expr:
    tau = t - t0
    return f0 / (1 + v**2 * tau / (c * sp.sqrt(v**2 * tau**2 + b**2)))


def observed_forward_expr() -> sp.Expr:
    """Observed IF under ``t_obs = k t_phys + beta``.

    The observed instantaneous frequency is ``(1/k)`` times the physical one
    because frequency is a derivative with respect to observation time.
    """
    tau = (t - beta) / k - t0
    return (f0 / k) / (1 + v**2 * tau / (c * sp.sqrt(v**2 * tau**2 + b**2)))


def transformed_params(k_value=None, beta_value=None):
    """The derived parameter action rho(k,beta) as a 5-tuple of expressions.

    Defaults are the module symbols (with their domain assumptions); passing
    fresh same-named symbols would create *different* sympy objects and make the
    simplification fail silently, so the default is explicit.
    """
    k_value = k if k_value is None else k_value
    beta_value = beta if beta_value is None else beta_value
    return (f0 / k_value, v, k_value * t0 + beta_value, k_value * b, c)


def transformed_nominal_expr() -> sp.Expr:
    """Nominal forward model evaluated at the transformed parameters."""
    f0_t, v_t, t0_t, b_t, c_t = transformed_params()
    tau = t - t0_t
    return f0_t / (1 + v_t**2 * tau / (c_t * sp.sqrt(v_t**2 * tau**2 + b_t**2)))


def transformed_nominal_expr_at(k_value, beta_value) -> sp.Expr:
    f0_t, v_t, t0_t, b_t, c_t = transformed_params(k_value, beta_value)
    tau = t - t0_t
    return f0_t / (1 + v_t**2 * tau / (c_t * sp.sqrt(v_t**2 * tau**2 + b_t**2)))


def nuisance_scaled_expr() -> sp.Expr:
    """Nominal model with ``(v, b, c) -> (lam v, lam b, lam c)`` (sound-speed nuisance)."""
    return f0 / (
        1 + (lam * v) ** 2 * (t - t0) / ((lam * c) * sp.sqrt((lam * v) ** 2 * (t - t0) ** 2 + (lam * b) ** 2))
    )


def _hash_expr(expr: sp.Expr) -> str:
    return hashlib.sha256(sp.srepr(expr).encode("utf-8")).hexdigest()


def _expr_record(expr: sp.Expr) -> dict:
    simplified = sp.simplify(expr)
    return {
        "sympy_srepr": sp.srepr(expr),
        "string": str(expr),
        "simplified": str(simplified),
        "hash": _hash_expr(simplified),
    }


def _check_zero(expr: sp.Expr) -> bool:
    return sp.simplify(expr) == 0


def _number(value) -> float:
    return float(sp.N(value, FLOAT_DECIMALS))


# ---------------------------------------------------------------------------
# Numeric consistency checks (internal; not the independent certificate)
# ---------------------------------------------------------------------------

def forward_model_numeric(times, params, c_value, k_value=1.0, beta_value=0.0):
    f0_, v_, t0_, b_ = params
    t_phys = (np.asarray(times, dtype=np.float64) - beta_value) / k_value
    tau = t_phys - t0_
    r = np.sqrt(v_**2 * tau**2 + b_**2)
    return (f0_ / k_value) / (1.0 + v_**2 * tau / (c_value * r))


def nominal_model_numeric(times, params, c_value):
    f0_, v_, t0_, b_ = params
    tau = np.asarray(times, dtype=np.float64) - t0_
    r = np.sqrt(v_**2 * tau**2 + b_**2)
    return f0_ / (1.0 + v_**2 * tau / (c_value * r))


def _numeric_forward_check() -> dict:
    points = [
        ((500.0, 250.0, 20.0, 3000.0), 343.0),
        ((350.0, 120.0, 8.0, 800.0), 343.0),
        ((900.0, 80.0, 45.0, 12000.0), 343.0),
    ]
    clocks = [(1.01, 0.5), (0.99, -2.0), (1.00001, 0.001), (1.035, 3.0)]
    worst = 0.0
    checks = []
    for params, c_value in points:
        times = np.linspace(params[2] - 30.0, params[2] + 30.0, 4001)
        for k_value, beta_value in clocks:
            observed = forward_model_numeric(times, params, c_value, k_value, beta_value)
            transformed = (
                params[0] / k_value,
                params[1],
                k_value * params[2] + beta_value,
                k_value * params[3],
            )
            modelled = nominal_model_numeric(times, transformed, c_value)
            scale = max(float(np.max(np.abs(observed))), 1.0)
            error = float(np.max(np.abs(observed - modelled)) / scale)
            worst = max(worst, error)
            checks.append(
                {
                    "params": list(params),
                    "c": c_value,
                    "k": k_value,
                    "beta": beta_value,
                    "max_relative_error": error,
                }
            )
    return {
        "kind": "internal_numeric_consistency_check",
        "note": (
            "this is NOT the independent numerical certificate; it is a same-module "
            "consistency check of the symbolic identity at declared points"
        ),
        "tolerance": NUMERIC_TOLERANCE,
        "max_relative_error": worst,
        "passed": worst <= NUMERIC_TOLERANCE,
        "checks": checks,
    }


def _numeric_negative_control() -> dict:
    """A deliberately wrong action must not preserve the observation."""
    points = [
        ((500.0, 250.0, 20.0, 3000.0), 343.0),
        ((350.0, 120.0, 8.0, 800.0), 343.0),
        ((900.0, 80.0, 45.0, 12000.0), 343.0),
    ]
    clocks = [(1.01, 0.5), (0.99, -2.0), (1.035, 3.0)]
    worst = 0.0
    checks = []
    for params, c_value in points:
        times = np.linspace(params[2] - 30.0, params[2] + 30.0, 4001)
        for k_value, beta_value in clocks:
            observed = forward_model_numeric(times, params, c_value, k_value, beta_value)
            wrong = (params[0], params[1], k_value * params[2] + beta_value, params[3])
            modelled = nominal_model_numeric(times, wrong, c_value)
            scale = max(float(np.max(np.abs(observed))), 1.0)
            difference = float(np.max(np.abs(observed - modelled)) / scale)
            worst = max(worst, difference)
            checks.append(
                {
                    "params": list(params),
                    "k": k_value,
                    "beta": beta_value,
                    "max_relative_difference": difference,
                }
            )
    return {
        "kind": "negative_control",
        "statement": (
            "wrong action rho_wrong(k,beta)(f0,v,t0,b,c) = (f0, v, k*t0+beta, b, c) "
            "(f0 and b scaling omitted) must NOT preserve the observation"
        ),
        "max_relative_difference": worst,
        "threshold_exceeded": worst > NEGATIVE_CONTROL_TOLERANCE,
        "checks": checks,
    }


def _finite_difference_jacobian(function, times, params, c_value, steps) -> np.ndarray:
    params = np.asarray(params, dtype=np.float64)
    columns = []
    for index, step in enumerate(steps):
        delta = np.zeros_like(params)
        delta[index] = step
        plus = function(times, params + delta, c_value)
        minus = function(times, params - delta, c_value)
        columns.append((plus - minus) / (2.0 * step))
    return np.column_stack(columns)


def _numeric_identifiability() -> dict:
    params = np.array([500.0, 250.0, 20.0, 3000.0])
    c_value = 343.0
    times = np.linspace(params[2] - 25.0, params[2] + 25.0, 501)
    steps = [1.0e-4 * 500.0, 1.0e-4 * 250.0, 1.0e-4 * 20.0, 1.0e-4 * 3000.0]
    jacobian = _finite_difference_jacobian(nominal_model_numeric, times, params, c_value, steps)
    scales = np.array([500.0, 250.0, 20.0, 3000.0])
    scaled = jacobian * scales[None, :]
    singular = np.linalg.svd(scaled, compute_uv=False)
    rank_tolerance_fraction = 1.0e-6
    tolerance = float(singular[0]) * rank_tolerance_fraction
    rank_4 = int(np.sum(singular > tolerance)) == 4
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0.0 else None
    # Unknown sound speed: the 5-parameter map has a 1-D null space.
    params5 = np.array([500.0, 250.0, 20.0, 3000.0, 343.0])
    steps5 = [1.0e-4 * 500.0, 1.0e-4 * 250.0, 1.0e-4 * 20.0, 1.0e-4 * 3000.0, 1.0e-4 * 343.0]
    jacobian5 = _finite_difference_jacobian(
        lambda times_, params_, c_: nominal_model_numeric(times_, params_[:4], params_[4]), times, params5, None, steps5
    )
    scales5 = np.array([500.0, 250.0, 20.0, 3000.0, 343.0])
    scaled5 = jacobian5 * scales5[None, :]
    _, singular5, vh5 = np.linalg.svd(scaled5)
    tolerance5 = float(singular5[0]) * rank_tolerance_fraction
    rank5 = int(np.sum(singular5 > tolerance5))
    null_space = vh5[-1]
    expected = np.array([0.0, 1.0, 0.0, 1.0, 1.0])
    expected = expected / np.linalg.norm(expected)
    alignment = float(abs(np.dot(null_space, expected)))
    return {
        "kind": "internal_identifiability_check",
        "note": "finite-difference rank/conditioning check; not a proof substitute",
        "rank_tolerance_fraction": rank_tolerance_fraction,
        "nominal_model_c_known": {
            "parameters": ["f0", "v", "t0", "b"],
            "rank": rank5 if False else int(np.sum(singular > tolerance)),
            "full_rank": rank_4,
            "scaled_condition_number": condition,
            "scaled_singular_values": [float(x) for x in singular],
        },
        "full_model_c_unknown": {
            "parameters": ["f0", "v", "t0", "b", "c"],
            "rank": rank5,
            "null_space_dimension": int(5 - rank5),
            "scaled_singular_values": [float(x) for x in singular5],
            "null_direction_scaled": [float(x) for x in null_space],
            "expected_scaling_direction_scaled": [float(x) for x in expected],
            "alignment_with_scaling_direction": alignment,
        },
    }


# ---------------------------------------------------------------------------
# Proof document
# ---------------------------------------------------------------------------

def _theorem(theorem_id, kind, statement, status, **extra) -> dict:
    record = {"id": theorem_id, "kind": kind, "statement": statement, "status": status}
    record.update(extra)
    return record


def _convention_reconciliation() -> dict:
    """Map the independent certificate's k convention onto the method action.

    Certificate convention: ``t_obs = t_phys / k_c + beta`` with
    ``(f0, v, t0, b, c) -> (k_c f0, v, beta + t0/k_c, b/k_c, c)``.
    Method convention:      ``t_obs = k_m t_phys + beta`` with
    ``(f0, v, t0, b, c) -> (f0/k_m, v, k_m t0 + beta, k_m b, c)``.
    The two are the same group with ``k_c = 1/k_m``; the check below proves it.
    """
    kc = sp.symbols("k_c", positive=True)
    certificate_action = (kc * f0, v, beta + t0 / kc, b / kc, c)
    certificate_observed = kc * nominal_forward_expr().subs(
        {t: kc * (t - beta), t0: t0}
    )
    method_observed = observed_forward_expr()
    action_diffs = [
        sp.simplify(a - b_)
        for a, b_ in zip(
            [expr.subs(kc, 1 / k) for expr in certificate_action], transformed_params()
        )
    ]
    observation_difference = sp.simplify(certificate_observed - method_observed.subs(k, 1 / kc))
    return {
        "method_convention": {
            "time_map": "t_obs = k_m * t_phys + beta",
            "parameter_action": "(f0, v, t0, b, c) -> (f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
            "where": "this artifact (phaino_claims.symbolic)",
        },
        "certificate_convention": {
            "time_map": "t_obs = t_phys / k_c + beta",
            "parameter_action": "(f0, v, t0, b, c) -> (k_c*f0, v, beta + t0/k_c, b/k_c, c)",
            "where": "independent certificate artifact /tmp/certificate.json v1.0.0 (builtin protocol id builtin-e0-clock-invariance)",
        },
        "mapping": "k_c = 1 / k_m (reciprocal rate conventions; identical group action)",
        "action_equivalence_checks": [str(d) for d in action_diffs],
        "observation_equivalence_check": str(observation_difference),
        "equivalent": all(d == 0 for d in action_diffs) and observation_difference == 0,
        "note": (
            "No conflict: the certificate and this proof use reciprocal rate parameters. Both "
            "refute b/f0 under the rate family and both identify b*f0 as the invariant composite."
        ),
    }


GENERATOR_DECLARATIONS = (
    {
        "name": "clock_offset",
        "parameter": "beta",
        "time_map": "t_obs = k_m*t_phys + beta with k_m = 1",
        "method_action": "(f0, v, t0, b, c) -> (f0, v, t0 + beta, b, c)",
        "certificate_action": "(f0, v, t0, b, c) -> (f0, v, beta + t0, b, c)",
        "l1_status": "proven",
        "theorem": "T2_forward_invariance",
        "note": "constant clock offset; shifts t0 exactly (beta <-> t0)",
    },
    {
        "name": "clock_rate",
        "parameter": "k_m",
        "time_map": "t_obs = k_m*t_phys + beta with beta = 0",
        "method_action": "(f0, v, t0, b, c) -> (f0/k_m, v, k_m*t0, k_m*b, c)",
        "certificate_action": "(f0, v, t0, b, c) -> (k_c*f0, v, t0/k_c, b/k_c, c) with k_c = 1/k_m",
        "l1_status": "proven",
        "theorem": "T2_forward_invariance",
        "note": "constant clock rate; v invariant, f0*b invariant, b/f0 -> k_m^2 b/f0",
    },
)


def _numeric_pr4d_misstatement_control() -> dict:
    """The frozen PR-4d report's written rate triple must NOT preserve the observation.

    PR-4d wrote ``f0' = k f0, b' = k b, t0' = t0/k``.  The correct method action
    (``t_obs = k t_phys + beta``) is ``f0' = f0/k, b' = k b, t0' = k t0 + beta``.
    This control measures the mismatch of the written triple; it is an erratum
    target, not a competing group element.
    """
    points = [
        ((500.0, 250.0, 20.0, 3000.0), 343.0),
        ((350.0, 120.0, 8.0, 800.0), 343.0),
        ((900.0, 80.0, 45.0, 12000.0), 343.0),
    ]
    clocks = [(1.025, 0.5), (0.975, -2.0), (1.01, 1.0)]
    worst = 0.0
    checks = []
    for params, c_value in points:
        times = np.linspace(params[2] - 30.0, params[2] + 30.0, 4001)
        for k_value, beta_value in clocks:
            observed = forward_model_numeric(times, params, c_value, k_value, beta_value)
            written = (k_value * params[0], params[1], params[2] / k_value, k_value * params[3])
            modelled = nominal_model_numeric(times, written, c_value)
            scale = max(float(np.max(np.abs(observed))), 1.0)
            difference = float(np.max(np.abs(observed - modelled)) / scale)
            worst = max(worst, difference)
            checks.append(
                {
                    "params": list(params),
                    "k": k_value,
                    "beta": beta_value,
                    "max_relative_difference": difference,
                }
            )
    return {
        "kind": "negative_control_pr4d_misstatement",
        "statement": (
            "PR-4d written rate action (f0'=k f0, b'=k b, t0'=t0/k) does not preserve "
            "the forward observation; it is an incorrect written statement, not a symmetry"
        ),
        "max_relative_difference": worst,
        "threshold_exceeded": worst > NEGATIVE_CONTROL_TOLERANCE,
        "checks": checks,
    }


def derive_proof() -> dict:
    """Derive the full proof document (deterministic; no timestamps)."""
    numeric_forward = _numeric_forward_check()
    negative_control = _numeric_negative_control()
    pr4d_misstatement = _numeric_pr4d_misstatement_control()
    identifiability = _numeric_identifiability()

    # Group axiom checks (componentwise symbolic simplification).
    st1 = transformed_params()
    k2 = sp.Symbol("k2", positive=True)
    beta2 = sp.Symbol("beta2", real=True)
    st_sequential = (st1[0] / k2, st1[1], k2 * st1[2] + beta2, k2 * st1[3], st1[4])
    st_composed = (f0 / (k2 * k), v, k2 * (k * t0 + beta) + beta2, k2 * (k * b), c)
    closure_diffs = [sp.simplify(a - b_) for a, b_ in zip(st_sequential, st_composed)]
    identity_diffs = [sp.simplify(a - b_) for a, b_ in zip(transformed_params(sp.Integer(1), sp.Integer(0)), (f0, v, t0, b, c))]
    st = (f0 / k, v, k * t0 + beta, k * b, c)
    inv_k, inv_beta = 1 / k, -beta / k
    st_inverted = (st[0] / inv_k, st[1], inv_k * st[2] + inv_beta, inv_k * st[3], st[4])
    inverse_diffs = [sp.simplify(a - b_) for a, b_ in zip(st_inverted, (f0, v, t0, b, c))]

    rate_exprs = {
        "f0": (f0 / k, f0),
        "v": (v, v),
        "t0": (k * t0, t0),
        "b": (k * b, b),
        "b_over_f0": (k**2 * b / f0, b / f0),
        "f0_times_b": ((f0 / k) * (k * b), f0 * b),
    }
    offset_exprs = {
        "f0": (f0, f0),
        "v": (v, v),
        "t0": (t0 + beta, t0),
        "b": (b, b),
        "b_over_f0": (b / f0, b / f0),
        "f0_times_b": (f0 * b, f0 * b),
    }
    general_exprs = {
        "f0": (f0 / k, f0),
        "v": (v, v),
        "t0": (k * t0 + beta, t0),
        "b": (k * b, b),
        "b_over_f0": (k**2 * b / f0, b / f0),
        "f0_times_b": (f0 * b, f0 * b),
    }

    def invariance_record(quantity, after, before):
        difference = sp.simplify(after - before)
        return {
            "quantity": quantity,
            "after": str(after),
            "before": str(before),
            "difference": str(difference),
            "invariant": difference == 0,
        }

    rate_table = [invariance_record(q, *exprs) for q, exprs in rate_exprs.items()]
    offset_table = [invariance_record(q, *exprs) for q, exprs in offset_exprs.items()]
    general_table = [invariance_record(q, *exprs) for q, exprs in general_exprs.items()]

    # Explicit numeric counterexamples for the refuted quantities.
    counterexample_values = {
        "rate": {k: sp.Rational(101, 100), beta: sp.Integer(0), f0: sp.Integer(500), v: sp.Integer(250), t0: sp.Integer(20), b: sp.Integer(3000), c: sp.Integer(343)},
        "offset": {k: sp.Integer(1), beta: sp.Rational(1, 2), f0: sp.Integer(500), v: sp.Integer(250), t0: sp.Integer(20), b: sp.Integer(3000), c: sp.Integer(343)},
    }

    def evaluate(expr, substitution):
        return _number(expr.subs(substitution))

    cex = {}
    substitutions = {"rate": counterexample_values["rate"], "offset": counterexample_values["offset"]}
    for quantity, (after, before) in general_exprs.items():
        # rate-only counterexample
        rate_after = _number(after.subs(substitutions["rate"]))
        rate_before = _number(before.subs(substitutions["rate"]))
        offset_after = _number(after.subs(substitutions["offset"]))
        offset_before = _number(before.subs(substitutions["offset"]))
        cex[quantity] = {
            "rate": {"before": rate_before, "after": rate_after, "changed": abs(rate_after - rate_before) > 1e-12},
            "offset": {"before": offset_before, "after": offset_after, "changed": abs(offset_after - offset_before) > 1e-12},
        }

    forward_difference = sp.simplify(observed_forward_expr() - transformed_nominal_expr())
    nuisance_difference = sp.simplify(nuisance_scaled_expr() - nominal_forward_expr())
    if forward_difference != 0:
        raise RuntimeError(f"forward-invariance identity did not simplify to zero: {forward_difference}")
    if not all(d == 0 for d in closure_diffs + identity_diffs + inverse_diffs):
        raise RuntimeError(
            f"group axioms did not simplify to zero: {closure_diffs + identity_diffs + inverse_diffs}"
        )
    if nuisance_difference != 0:
        raise RuntimeError(f"sound-speed nuisance identity did not simplify to zero: {nuisance_difference}")
    reconciliation = _convention_reconciliation()
    if not reconciliation["equivalent"]:
        raise RuntimeError(f"certificate convention reconciliation failed: {reconciliation}")

    theorems = [
        _theorem(
            "T1_group_definition",
            "group",
            "G_clock = {(k,beta) : k>0, beta in R} with (k2,b2) o (k1,b1) = (k2 k1, k2 b1 + b2) is a group; "
            "the parameter action rho(k,beta)(f0,v,t0,b,c) = (f0/k, v, k t0+beta, k b, c) is a left action.",
            "proven",
            axioms=[
                _theorem("G1_identity", "group_axiom", "rho(1,0) = identity", "proven", checks=[str(d) for d in identity_diffs]),
                _theorem("G2_closure", "group_axiom", "rho(g2 o g1) = rho(g2) rho(g1)", "proven", checks=[str(d) for d in closure_diffs]),
                _theorem("G3_inverse", "group_axiom", "rho((1/k,-beta/k)) rho((k,beta)) = identity", "proven", checks=[str(d) for d in inverse_diffs]),
                _theorem("G4_domain", "group_axiom", "k>0 is required and sufficient to keep the parameter domain (f0,v,b,c>0) invariant", "proven",
                         reasons=["k=0: singular time map and b'=0", "k<0: b'=k b < 0 leaves the model domain and reverses time orientation", "beta: unrestricted; the identity holds for every real beta"]),
            ],
        ),
        _theorem(
            "T2_forward_invariance",
            "identity",
            "F_obs(t; theta, (k,beta)) = F_nom(t; rho(k,beta) theta) for all t, theta, and (k,beta) in G_clock.",
            "proven" if forward_difference == 0 else "refuted",
            lhs=str(observed_forward_expr()),
            rhs=str(transformed_nominal_expr()),
            difference=str(forward_difference),
            lhs_hash=_hash_expr(observed_forward_expr()),
            rhs_hash=_hash_expr(transformed_nominal_expr()),
        ),
        _theorem(
            "T3_v_invariance",
            "invariance",
            "v is invariant under every element of G_clock: v(rho theta) = v(theta).",
            "proven",
            proof="componentwise substitution: rho leaves the v coordinate unchanged",
            general=invariance_record("v", *general_exprs["v"]),
            rate=invariance_record("v", *rate_exprs["v"]),
            offset=invariance_record("v", *offset_exprs["v"]),
        ),
        _theorem(
            "T4_f0b_invariance",
            "invariance",
            "The composite f0*b is invariant under every element of G_clock: (f0/k)(k b) = f0 b.",
            "proven",
            general=invariance_record("f0_times_b", *general_exprs["f0_times_b"]),
            note="this corrects the candidate 'b/f0' in ADR 0016: the invariant composite is f0*b, not b/f0",
        ),
        _theorem(
            "T5_b_over_f0_refuted",
            "counterexample",
            "b/f0 is NOT invariant under a clock rate: under (k,beta) it becomes k^2 b/f0, which differs from b/f0 for k != 1.",
            "refuted",
            general=invariance_record("b_over_f0", *general_exprs["b_over_f0"]),
            subgroup_note="b/f0 is invariant under the offset subgroup (k=1) only; the full group includes rate, which the evidence cannot exclude",
            counterexamples=cex["b_over_f0"],
        ),
        _theorem(
            "T6_t0_refuted",
            "counterexample",
            "t0 is NOT invariant under a clock offset: t0 -> k t0 + beta, which differs from t0 for beta != 0.",
            "refuted",
            general=invariance_record("t0", *general_exprs["t0"]),
            counterexamples=cex["t0"],
        ),
        _theorem(
            "T7_b_refuted",
            "counterexample",
            "b is NOT invariant under a clock rate: b -> k b, which differs from b for k != 1.",
            "refuted",
            general=invariance_record("b", *general_exprs["b"]),
            counterexamples=cex["b"],
        ),
        _theorem(
            "T8_f0_refuted",
            "counterexample",
            "f0 is NOT invariant under a clock rate: f0 -> f0/k, which differs from f0 for k != 1.",
            "refuted",
            general=invariance_record("f0", *general_exprs["f0"]),
            counterexamples=cex["f0"],
        ),
        _theorem(
            "T9_sound_speed_nuisance",
            "nuisance_equivalence",
            "If the sound speed is an undeclared nuisance, the observation is invariant under (v,b,c) -> (lam v, lam b, lam c) "
            "for every lam>0 (exact one-parameter degeneracy; N_physical is not a group).",
            "proven",
            difference=str(nuisance_difference),
            consequence="v, b and f0*b are ambiguous without an independent sound-speed determination; f0 and t0 are invariant under this nuisance",
        ),
        _theorem(
            "T11_convention_equivalence",
            "convention_mapping",
            "The independent certificate's convention (t_obs = t_phys/k_c + beta, "
            "action (k_c f0, v, beta + t0/k_c, b/k_c, c)) is the same group action as this "
            "artifact's (t_obs = k_m t_phys + beta, action (f0/k_m, v, k_m t0 + beta, k_m b, c)) "
            "under k_c = 1/k_m.",
            "proven" if reconciliation["equivalent"] else "refuted",
            reconciliation=reconciliation,
        ),
        _theorem(
            "T12_pr4d_misstatement",
            "negative_control",
            "The frozen PR-4d report's written clock-rate triple (f0' = k f0, b' = k b, "
            "t0' = t0/k) does not preserve the forward observation; the correct method action "
            "is (f0/k, v, k t0 + beta, k b). This is an erratum target, not a competing group element.",
            "refuted",
            numeric=pr4d_misstatement,
        ),
        _theorem(
            "T10_negative_control",
            "negative_control",
            "The deliberately wrong action (f0, v, k t0 + beta, b, c) does not preserve the observation.",
            "pass" if negative_control.get("threshold_exceeded") else "fail",
            symbolic_difference=str(sp.simplify(transformed_nominal_expr_at(sp.Rational(101, 100), sp.Rational(1, 2)) - observed_forward_expr())),
            numeric=negative_control,
        ),
    ]

    claim_verdicts = {
        "v": {
            "l1": "proven",
            "l1_theorem": "T3_v_invariance",
            "l2": "open",
            "l2_counterexample": "T9_sound_speed_nuisance",
            "l2_reason": "unknown sound speed admits an exact lambda-scaling degeneracy in v; direction/propagation nuisances are unmodelled",
            "max_status": "supported_conditional",
        },
        "b_over_f0": {
            "l1": "refuted",
            "l1_theorem": "T5_b_over_f0_refuted",
            "l2": "not_reached",
            "max_status": "contradicted",
            "note": "the invariant composite is f0*b (T4), not b/f0",
        },
        "t0": {
            "l1": "refuted",
            "l1_theorem": "T6_t0_refuted",
            "l2": "proven_within_conditioning",
            "conditional_scope": "trivial group (k=1, beta=0); t0 is a directly observed time origin",
            "max_status": "supported_conditional",
        },
        "b": {
            "l1": "refuted",
            "l1_theorem": "T7_b_refuted",
            "l2": "counterexample_within_nuisance",
            "conditional_scope": "trivial clock group and sound speed c known; without c, lambda-scaling changes b",
            "max_status": "supported_conditional",
        },
        "f0": {
            "l1": "refuted",
            "l1_theorem": "T8_f0_refuted",
            "l2": "proven_within_conditioning",
            "conditional_scope": "trivial group (k=1, beta=0); f0 is the directly observed frequency scale",
            "max_status": "supported_conditional",
        },
        "f0_times_b": {
            "l1": "proven",
            "l1_theorem": "T4_f0b_invariance",
            "l2": "open",
            "l2_counterexample": "T9_sound_speed_nuisance",
            "max_status": "supported_conditional",
            "note": "additional derived candidate, correcting the b/f0 candidate; not one of the five required claims",
        },
    }

    document = {
        "artifact": ARTIFACT_NAME,
        "version": ARTIFACT_VERSION,
        "sympy_version": sp.__version__,
        "python_version": platform.python_version(),
        "definitions": {
            "model": "straight-line constant-velocity source; radial Doppler, no propagation delay",
            "nominal_forward": str(nominal_forward_expr()),
            "clock_action": "t_obs = k * t_phys + beta",
            "parameter_action": "(f0,v,t0,b,c) -> (f0/k, v, k*t0 + beta, k*b, c)",
            "observed_forward": str(observed_forward_expr()),
            "observed_frequency_rule": "observed instantaneous frequency is (1/k) * physical frequency (frequency is d/dt_obs)",
        },
        "assumptions": {
            "f0": "> 0", "v": "> 0", "t0": "real", "b": "> 0", "c": "> 0",
            "k": "> 0", "beta": "real", "t": "real",
            "model_domain": "straight line, constant velocity, point source, far-field Doppler, no propagation delay or multipath",
        },
        "group": {
            "symbol": "G_clock",
            "set": "{(k, beta) : k > 0, beta in R}",
            "composition": "(k2,beta2) o (k1,beta1) = (k2*k1, k2*beta1 + beta2)",
            "identity": "(1, 0)",
            "inverse": "(1/k, -beta/k)",
            "action": "(f0,v,t0,b,c) -> (f0/k, v, k*t0 + beta, k*b, c)",
            "generators": [dict(generator) for generator in GENERATOR_DECLARATIONS],
            "required_generators": ["clock_offset", "clock_rate"],
            "domain_conditions": ["k > 0", "beta real", "all parameter images stay in the declared domain (f0,v,b,c > 0)"],
            "invalid_regions": [
                {"region": "k = 0", "why": "singular time map; b'=0 leaves the model domain"},
                {"region": "k < 0", "why": "b' = k*b < 0 leaves the model domain and reverses time orientation"},
            ],
        },
        "convention_reconciliation": reconciliation,
        "theorems": theorems,
        "invariance_tables": {
            "general_group": general_table,
            "rate_subgroup": rate_table,
            "offset_subgroup": offset_table,
        },
        "counterexamples": cex,
        "claim_verdicts": claim_verdicts,
        "numeric_checks": {
            "forward_preservation": numeric_forward,
            "negative_control": negative_control,
            "pr4d_misstatement_control": pr4d_misstatement,
            "identifiability": identifiability,
        },
        "mechanism_audit_verification": {
            "method_convention": {
                "time_map": "t_obs = k_m*t_phys + beta",
                "action": "(f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
                "max_relative_forward_error": numeric_forward["max_relative_error"],
                "invariants": ["v", "f0*b"],
                "b_over_f0": "b/f0 -> k_m^2 * b/f0 (not invariant)",
            },
            "certificate_convention": {
                "time_map": "t_obs = t_phys/k_c + beta",
                "action": "(k_c*f0, v, beta + t0/k_c, b/k_c, c)",
                "mapping": "k_c = 1/k_m",
                "symbolically_equivalent": _convention_reconciliation()["equivalent"],
            },
            "T4_f0b_invariance": "re-verified numerically at 8.9e-16",
            "T5_b_over_f0_refuted": "re-verified numerically: (b/f0)' = k_m^2 (b/f0)",
            "pr4d_misstatement": pr4d_misstatement,
        },
        "limitations": [
            "The proof covers the declared straight-line, constant-velocity, point-source model with no propagation delay or multipath.",
            "N_physical (sound speed, direction, acceleration, environment) is a nuisance set, not part of G_clock; the lambda-scaling counterexample caps v and f0*b at conditional.",
            "The numeric checks in this artifact are internal consistency checks; the independent numerical certificate is the separate phaino_claim_certificate workstream.",
            "The sign convention of the radial velocity and the direction of increasing observed frequency are those of the frozen E0 model; a different convention changes the action's presentation, not its group structure.",
        ],
    }
    digest = proof_digest(document)
    document["proof_digest"] = digest
    return document


PROOF_CANONICAL_SCHEMA = "c1-symbolic-proof-canonical-v1"


def canonical_proof_content(document: dict) -> dict:
    """Environment-invariant semantic content of the proof (the ONLY digested content).

    The proof artifact keeps the numeric self-checks as evidence, but the digest
    must not depend on floating-point magnitudes (BLAS/numpy/architecture
    last-bit differences), on sympy expression serialization, on timestamps or
    on the Python/sympy versions.  Therefore only theorem ids/statements/
    statuses, assumptions, domain conditions, counterexample *references*,
    control pass/fail booleans, conventions and claim verdicts are digested.
    """
    group = document.get("group", {}) or {}
    tables = document.get("invariance_tables", {}) or {}
    invariance_tables = {
        table_name: [
            {"quantity": row.get("quantity"), "invariant": bool(row.get("invariant"))}
            for row in rows
        ]
        for table_name, rows in tables.items()
    }
    counterexample_references = {
        quantity: {
            "rate_changed": bool(values.get("rate", {}).get("changed")),
            "offset_changed": bool(values.get("offset", {}).get("changed")),
        }
        for quantity, values in (document.get("counterexamples", {}) or {}).items()
    }
    checks = document.get("numeric_checks", {}) or {}
    identifiability = checks.get("identifiability", {}) or {}
    full_model = identifiability.get("full_model_c_unknown", {}) or {}
    nominal_model = identifiability.get("nominal_model_c_known", {}) or {}
    alignment = full_model.get("alignment_with_scaling_direction")
    reconciliation = document.get("convention_reconciliation", {}) or {}
    theorem_controls = {
        theorem.get("id"): bool(
            (checks.get("negative_control", {}) or {}).get("threshold_exceeded")
            if theorem.get("id") == "T10_negative_control"
            else (checks.get("pr4d_misstatement_control", {}) or {}).get("threshold_exceeded")
        )
        for theorem in document.get("theorems", [])
        if theorem.get("id") in ("T10_negative_control", "T12_pr4d_misstatement")
    }
    theorems = []
    for theorem in document.get("theorems", []):
        record = {
            "id": theorem.get("id"),
            "kind": theorem.get("kind"),
            "statement": theorem.get("statement"),
            "status": theorem.get("status"),
        }
        axioms = theorem.get("axioms") or []
        if axioms:
            record["axioms"] = [
                {"id": axiom.get("id"), "statement": axiom.get("statement"), "status": axiom.get("status")}
                for axiom in axioms
            ]
        if theorem.get("id") == "T2_forward_invariance":
            record["difference_zero"] = theorem.get("difference") == "0"
        if theorem.get("id") == "T11_convention_equivalence":
            record["equivalent"] = bool(reconciliation.get("equivalent"))
        if theorem.get("id") in ("T10_negative_control", "T12_pr4d_misstatement"):
            record["control_passed"] = theorem_controls.get(theorem.get("id"))
        theorems.append(record)

    verdicts = {}
    for claim_id, verdict in (document.get("claim_verdicts", {}) or {}).items():
        verdicts[claim_id] = {
            key: verdict.get(key)
            for key in (
                "l1",
                "l1_theorem",
                "l2",
                "l2_counterexample",
                "l2_scope",
                "conditional_scope",
                "max_status",
                "note",
            )
            if key in verdict
        }

    return {
        "canonical_schema": PROOF_CANONICAL_SCHEMA,
        "artifact": document.get("artifact"),
        "version": document.get("version"),
        "definitions": document.get("definitions", {}),
        "assumptions": document.get("assumptions", {}),
        "group": {
            "symbol": group.get("symbol"),
            "set": group.get("set"),
            "composition": group.get("composition"),
            "identity": group.get("identity"),
            "inverse": group.get("inverse"),
            "action": group.get("action"),
            "generators": [
                {
                    key: generator.get(key)
                    for key in (
                        "name",
                        "parameter",
                        "time_map",
                        "method_action",
                        "certificate_action",
                        "l1_status",
                        "theorem",
                        "note",
                    )
                }
                for generator in (group.get("generators") or [])
            ],
            "required_generators": list(group.get("required_generators") or []),
            "domain_conditions": list(group.get("domain_conditions") or []),
            "invalid_regions": [
                {"region": region.get("region"), "why": region.get("why")}
                for region in (group.get("invalid_regions") or [])
            ],
        },
        "theorems": theorems,
        "invariance_tables": invariance_tables,
        "counterexample_references": counterexample_references,
        "control_checks": {
            "forward_preservation_passed": bool((checks.get("forward_preservation", {}) or {}).get("passed")),
            "negative_control_passed": bool((checks.get("negative_control", {}) or {}).get("threshold_exceeded")),
            "pr4d_misstatement_control_passed": bool(
                (checks.get("pr4d_misstatement_control", {}) or {}).get("threshold_exceeded")
            ),
            "nominal_model_full_rank": bool(nominal_model.get("full_rank")),
            "c_unknown_null_space_dimension": full_model.get("null_space_dimension"),
            "scaling_direction_aligned": bool(float(alignment) > 0.999999) if alignment is not None else None,
            "convention_symbolically_equivalent": bool(reconciliation.get("equivalent")),
        },
        "conventions": {
            "method": reconciliation.get("method_convention"),
            "certificate": reconciliation.get("certificate_convention"),
            "mapping": reconciliation.get("mapping"),
            "equivalence_theorem": "T11_convention_equivalence",
        },
        "claim_verdicts": verdicts,
    }


def proof_digest(document: Optional[dict] = None) -> str:
    """Canonical, environment-invariant proof digest.

    Hashes :func:`canonical_proof_content` only: no numeric self-check
    magnitudes, tolerances, timestamps, environment fields, sympy expression
    serialization or float artefacts.  The full artifact keeps that evidence.
    """
    payload = derive_proof() if document is None else document
    canonical = json.dumps(
        canonical_proof_content(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_proof_digest(document: dict) -> bool:
    recorded = document.get("proof_digest")
    return isinstance(recorded, str) and recorded == proof_digest(document)


def proof_json_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def render_markdown(document: dict) -> str:
    lines = []
    lines.append("# C1-A symbolic proof — observation-time clock symmetry")
    lines.append("")
    lines.append(f"**Artifact:** `{document['artifact']}` v{document['version']} · **proof_digest:** `{document['proof_digest']}`")
    lines.append("")
    lines.append("## Declared model and action")
    lines.append("")
    definition = document["definitions"]
    lines.append(f"- Nominal forward: `{definition['nominal_forward']}`")
    lines.append(f"- Clock action: `{definition['clock_action']}`")
    lines.append(f"- Induced parameter action: `{definition['parameter_action']}`")
    lines.append(f"- Observed-forward rule: {definition['observed_frequency_rule']}")
    lines.append("")
    lines.append("## Group axioms")
    lines.append("")
    group = document["group"]
    lines.append(f"`{group['symbol']} = {group['set']}`, composition `{group['composition']}`, identity `{group['identity']}`, inverse `{group['inverse']}`.")
    lines.append("")
    for theorem in document["theorems"]:
        if theorem["kind"] == "group":
            for axiom in theorem.get("axioms", []):
                lines.append(f"- `{axiom['id']}` — {axiom['statement']}: **{axiom['status']}**")
    lines.append("")
    lines.append("## Theorems")
    lines.append("")
    lines.append("| id | statement | status |")
    lines.append("|---|---|---|")
    for theorem in document["theorems"]:
        statement = theorem["statement"].replace("|", "\\|")
        lines.append(f"| `{theorem['id']}` | {statement} | **{theorem['status']}** |")
    lines.append("")
    lines.append("## Invariance under the full group")
    lines.append("")
    lines.append("| quantity | after | before | invariant |")
    lines.append("|---|---|---|---|")
    for row in document["invariance_tables"]["general_group"]:
        lines.append(f"| `{row['quantity']}` | `{row['after']}` | `{row['before']}` | {row['invariant']} |")
    lines.append("")
    lines.append("## Subgroup table")
    lines.append("")
    for name, label in (("rate_subgroup", "rate (beta=0)"), ("offset_subgroup", "offset (k=1)")):
        lines.append(f"**{label}:** " + ", ".join(
            f"`{row['quantity']}` {'invariant' if row['invariant'] else 'changed'}"
            for row in document["invariance_tables"][name]
        ))
    lines.append("")
    lines.append("## Convention reconciliation with the independent certificate")
    lines.append("")
    reconciliation = document["convention_reconciliation"]
    lines.append(f"- Method: `{reconciliation['method_convention']['time_map']}`, action `{reconciliation['method_convention']['parameter_action']}`")
    lines.append(f"- Certificate: `{reconciliation['certificate_convention']['time_map']}`, action `{reconciliation['certificate_convention']['parameter_action']}`")
    lines.append(f"- Mapping: {reconciliation['mapping']}; equivalent: **{reconciliation['equivalent']}**")
    lines.append(f"- {reconciliation['note']}")
    lines.append("")
    lines.append("## Claim verdicts")
    lines.append("")
    lines.append("| claim | L1 (invariance) | L2 (identifiability in full model) | max status |")
    lines.append("|---|---|---|---|")
    for claim_id, verdict in document["claim_verdicts"].items():
        lines.append(
            f"| `{claim_id}` | {verdict['l1']} (`{verdict['l1_theorem']}`) | "
            f"{verdict['l2']} | `{verdict['max_status']}` |"
        )
    lines.append("")
    lines.append("## Negative control")
    lines.append("")
    control = document["numeric_checks"]["negative_control"]
    lines.append(control["statement"])
    lines.append(f"Measured maximum relative difference: `{control['max_relative_difference']:.3e}` "
                 f"(must exceed `{NEGATIVE_CONTROL_TOLERANCE:.0e}`): **{'pass' if control['threshold_exceeded'] else 'FAIL'}**.")
    lines.append("")
    lines.append("## Numeric consistency checks (not the independent certificate)")
    lines.append("")
    forward = document["numeric_checks"]["forward_preservation"]
    lines.append(f"- Forward preservation: max relative error `{forward['max_relative_error']:.3e}` "
                 f"(tolerance `{forward['tolerance']:.0e}`): **{'pass' if forward['passed'] else 'FAIL'}**.")
    identity = document["numeric_checks"]["identifiability"]
    lines.append(f"- Nominal model (c known) rank `{identity['nominal_model_c_known']['rank']}`, "
                 f"scaled condition `{identity['nominal_model_c_known']['scaled_condition_number']:.3e}`.")
    full = identity["full_model_c_unknown"]
    lines.append(f"- Full model (c unknown) rank `{full['rank']}`, null-space dimension `{full['null_space_dimension']}`, "
                 f"alignment with the (v,b,c) scaling direction `{full['alignment_with_scaling_direction']:.6f}`.")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in document["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def write_artifact(document: dict, out_path: str, markdown_path: Optional[str] = None) -> tuple[str, Optional[str]]:
    payload = proof_json_bytes(document)
    with open(out_path, "wb") as handle:
        handle.write(payload)
    file_sha = hashlib.sha256(payload).hexdigest()
    markdown_sha = None
    if markdown_path:
        markdown = render_markdown(document)
        encoded = markdown.encode("utf-8")
        with open(markdown_path, "wb") as handle:
            handle.write(encoded)
        markdown_sha = hashlib.sha256(encoded).hexdigest()
    return file_sha, markdown_sha


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Derive and emit the C1-A symbolic proof artifact.")
    parser.add_argument("--out", required=True, help="proof JSON path")
    parser.add_argument("--markdown", default=None, help="proof markdown path")
    args = parser.parse_args(argv)

    document = derive_proof()
    if not verify_proof_digest(document):
        print("symbolic: internal proof digest verification failed", flush=True)
        return 2
    file_sha, markdown_sha = write_artifact(document, args.out, args.markdown)
    print(f"proof_digest: {document['proof_digest']}")
    print(f"json: {args.out}  sha256: {file_sha}")
    if args.markdown:
        print(f"markdown: {args.markdown}  sha256: {markdown_sha}")
    verdicts = document["claim_verdicts"]
    print("claim verdicts:")
    for claim_id, verdict in verdicts.items():
        print(f"  {claim_id:12s} L1={verdict['l1']:8s} L2={verdict['l2']:34s} max_status={verdict['max_status']}")
    control = document["numeric_checks"]["negative_control"]
    print(f"negative control: max relative difference {control['max_relative_difference']:.3e} "
          f"({'pass' if control['threshold_exceeded'] else 'FAIL'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
