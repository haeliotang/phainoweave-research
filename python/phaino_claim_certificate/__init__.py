"""Independent numerical certificate for E0 clock-invariance claims.

This package implements the narrowband Doppler forward model and the induced clock action
from physics in pure numpy. It checks group axioms, forward-model preservation in the same
observation coordinates, and the five declared claims. It does not import
``phaino_acoustics`` and it is designed to fail loudly when a generator or claim does not
hold.
"""

from .certificate import run_certificate
from .cli import main
from .model import (
    ClockTransform,
    ModelParameters,
    claim_value,
    forward_model,
    forward_preservation,
    physical_frequency,
    relative_mismatch,
    sample_grid,
)
from .protocol import (
    CERTIFICATE_VERSION,
    ClaimsProtocol,
    ClaimsProtocolError,
    builtin_protocol,
    load_claims_protocol,
    load_method_protocol,
)
from .report import certificate_json, certificate_markdown

__all__ = [
    "CERTIFICATE_VERSION",
    "ClaimsProtocol",
    "ClaimsProtocolError",
    "ClockTransform",
    "ModelParameters",
    "builtin_protocol",
    "certificate_json",
    "certificate_markdown",
    "claim_value",
    "forward_model",
    "forward_preservation",
    "load_claims_protocol",
    "load_method_protocol",
    "main",
    "physical_frequency",
    "relative_mismatch",
    "run_certificate",
    "sample_grid",
]
