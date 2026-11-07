"""PhainoWeave acoustics package.

PR-2 / E0: synthetic Doppler identifiability experiment.  The package is
deliberately split into a physical model + generator (:mod:`synthetic`), a
model-free front end (:mod:`features`), a physical-model estimator
(:mod:`fit`), and the sweep runner (:mod:`experiment`).

E0 is an estimator/numerical-solver study on synthetic data.  It makes no
claim about real recordings, reverberation, propagation, or localization.
"""

from .features import InstantaneousFrequencyTrack, estimate_if_track
from .fit import (
    FitResult,
    NaiveResult,
    fit_doppler,
    naive_inversion,
)
from .synthetic import (
    C_SOUND_DEFAULT,
    Scenario,
    SyntheticObservation,
    doppler_frequency,
    generate,
    observation_window,
)

__all__ = [
    "C_SOUND_DEFAULT",
    "FitResult",
    "InstantaneousFrequencyTrack",
    "NaiveResult",
    "Scenario",
    "SyntheticObservation",
    "doppler_frequency",
    "estimate_if_track",
    "fit_doppler",
    "generate",
    "naive_inversion",
    "observation_window",
]
