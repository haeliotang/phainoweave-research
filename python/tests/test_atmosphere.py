import math

import pytest

from phaino_acoustics.atmosphere import (
    Atmosphere,
    doppler_residual_interval_hz,
    effective_sound_speed,
    predicted_doppler_hz,
    sound_speed_mps,
    sound_speed_uncertainty,
)


def test_sound_speed_reference_values():
    assert sound_speed_mps(0.0, 0.0) == pytest.approx(331.3, abs=0.1)
    assert sound_speed_mps(20.0, 0.0) == pytest.approx(343.42, abs=0.1)
    assert sound_speed_mps(20.0, 50.0) > sound_speed_mps(20.0, 0.0)


def test_effective_speed_and_wind_projection():
    calm = Atmosphere(20.0, 50.0, wind_mps=0.0)
    tail = Atmosphere(20.0, 50.0, wind_mps=3.0, wind_along_path_fraction=1.0)
    head = Atmosphere(20.0, 50.0, wind_mps=3.0, wind_along_path_fraction=-1.0)
    assert effective_sound_speed(tail) == pytest.approx(effective_sound_speed(calm) + 3.0)
    assert effective_sound_speed(head) == pytest.approx(effective_sound_speed(calm) - 3.0)


def test_uncertainty_increases_with_environmental_errors():
    exact = Atmosphere(20.0, 50.0, temperature_uncertainty_c=0.0, humidity_uncertainty_pct=0.0,
                       pressure_uncertainty_hpa=0.0, wind_uncertainty_mps=0.0)
    rough = Atmosphere(20.0, 50.0, temperature_uncertainty_c=2.0, humidity_uncertainty_pct=15.0,
                       pressure_uncertainty_hpa=10.0, wind_uncertainty_mps=2.0)
    assert sound_speed_uncertainty(exact) == 0.0
    assert sound_speed_uncertainty(rough) > 1.0


def test_doppler_prediction_and_interval():
    atmosphere = Atmosphere(20.0, 50.0)
    predicted = predicted_doppler_hz(500.0, 50.0, atmosphere)
    assert predicted > 500.0
    interval = doppler_residual_interval_hz(500.0, 50.0, atmosphere)
    assert interval["lower_hz"] < predicted < interval["upper_hz"]
    assert interval["residual_sigma_hz"] > 0.0


def test_supersonic_radial_speed_is_refused():
    with pytest.raises(ValueError):
        predicted_doppler_hz(500.0, 400.0, Atmosphere(20.0, 50.0))


def test_atmosphere_validation():
    with pytest.raises(ValueError):
        Atmosphere(20.0, 120.0)
    with pytest.raises(ValueError):
        Atmosphere(20.0, 50.0, wind_along_path_fraction=2.0)
    with pytest.raises(ValueError):
        Atmosphere(20.0, 50.0, pressure_hpa=0.0)
