import math

from phaino_acoustics.fault_injection import (
    DEFAULT_FAULTS,
    FaultSpec,
    run_fault_trial,
)


def test_baseline_and_clock_ppm_are_not_false_convergence():
    baseline = run_fault_trial(spec=FaultSpec("baseline"))
    assert not baseline.supported
    assert baseline.abstention_reason is None
    for ppm in (50.0, -50.0):
        result = run_fault_trial(spec=FaultSpec(f"clock_{ppm}", clock_ppm=ppm))
        assert not result.supported
        assert result.decision != "supported"
        assert result.relative_errors["v"] < 0.02


def test_severe_clipping_abstains_or_rejects_with_scale_inflation():
    baseline = run_fault_trial(spec=FaultSpec("baseline"))
    clipped = run_fault_trial(spec=FaultSpec("clip", clipping_peak_fraction=0.10))
    assert not clipped.supported
    assert clipped.decision in ("undetermined", "rejected")
    assert clipped.residual_sigma_hz > baseline.residual_sigma_hz


def test_dropped_buffers_inflate_residual_scale():
    baseline = run_fault_trial(spec=FaultSpec("baseline"))
    dropped = run_fault_trial(
        spec=FaultSpec(
            "dropout",
            dropout_windows=((12.0, 0.5), (27.0, 0.5), (42.0, 0.5)),
        )
    )
    assert not dropped.supported
    assert dropped.residual_sigma_hz > 10.0 * baseline.residual_sigma_hz


def test_wind_burst_does_not_produce_false_support():
    wind = run_fault_trial(spec=FaultSpec("wind", wind_bursts=((30.0, 2.0, 2.0),)))
    assert not wind.supported
    assert wind.decision in ("undetermined", "rejected")


def test_reference_channel_loss_is_an_explicit_abstention():
    for spec in (
        FaultSpec("ref_missing", reference_missing=True),
        FaultSpec("ref_low_snr", reference_snr_db=-3.0),
    ):
        result = run_fault_trial(spec=spec)
        assert not result.supported
        assert result.abstention_reason is not None
        assert result.decision == "undetermined"
        assert math.isnan(result.residual_sigma_hz)


def test_default_suite_is_deterministic():
    first = [run_fault_trial(spec=spec, seed=7) for spec in DEFAULT_FAULTS]
    second = [run_fault_trial(spec=spec, seed=7) for spec in DEFAULT_FAULTS]
    assert [repr(item) for item in first] == [repr(item) for item in second]


def test_suite_acceptance_and_json_projection(tmp_path):
    from phaino_acoustics.fault_injection import main, run_suite

    report = run_suite()
    assert report["ok"], report["errors"]
    assert report["results"][0]["residual_sigma_hz"] is not None
    assert report["results"][-1]["residual_sigma_hz"] is None  # reference abstention

    out = tmp_path / "e1-fault.json"
    assert main(["--out", str(out)]) == 0
    assert out.is_file()
    assert '"ok": true' in out.read_text()
