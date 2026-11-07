import hashlib
import json
from pathlib import Path

import pytest

from phaino_e1raw import validate_bundle
from phaino_e1raw.__main__ import main


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_bundle(tmp_path: Path, *, mutate=None) -> Path:
    root = tmp_path / "bundle"
    (root / "audio").mkdir(parents=True)
    (root / "ref").mkdir()
    audio = root / "audio" / "take.wav"
    audio.write_bytes(b"RIFF-fake-audio")
    freq = root / "ref" / "freq.wav"
    freq.write_bytes(b"calibrated-tone")
    time_ref = root / "ref" / "pps.txt"
    time_ref.write_bytes(b"pps")
    motion = root / "ref" / "motion.csv"
    motion.write_bytes(b"pos")
    document = {
        "schema_version": "e1-0-bundle-1.0.0",
        "bundle_id": "e1b_0123456789abcdef",
        "measurement_model_id": "e0-frontend-hann-stft-512-256@1.0.0",
        "audio": [
            {
                "path": "audio/take.wav",
                "sha256": sha(audio),
                "sample_rate_hz": 48000,
                "channels": 1,
                "duration_s": 60.0,
            }
        ],
        "references": {
            "reference_snr_db": 20.0,
            "frequency": {
                "path": "ref/freq.wav",
                "sha256": sha(freq),
                "calibration_certificate": {
                    "id": "CAL-2026-001",
                    "issued_by": "independent-lab",
                    "uncertainty_hz": 0.01,
                    "valid_until": "2027-01-01",
                },
            },
            "time": {"kind": "pps", "path": "ref/pps.txt", "sha256": sha(time_ref), "uncertainty_s": 1e-6},
            "motion": {"path": "ref/motion.csv", "sha256": sha(motion), "uncertainty_m": 0.01},
        },
        "authorization": {
            "site_id": "site-001",
            "jurisdiction": "NP",
            "legal_review_id": "LR-2026-001",
            "consent_sha256": "a" * 64,
        },
        "environment": {"temperature_c": 18.0, "humidity_pct": 55.0, "wind_mps": 1.2, "sound_speed_mps": 342.0},
        "operator": {"id": "op-1", "role": "researcher"},
    }
    (root / "bundle.json").write_text(json.dumps(document), encoding="utf-8")
    if mutate:
        mutate(root, document)
        (root / "bundle.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def codes(report):
    return {error.code for error in report.errors}


def test_valid_bundle_passes(tmp_path):
    report = validate_bundle(make_bundle(tmp_path))
    assert report.ok, report.errors
    assert report.checked_files == 4


def test_missing_reference_rejects(tmp_path):
    report = validate_bundle(make_bundle(tmp_path, mutate=lambda root, doc: doc["references"].pop("time")))
    assert "missing_field" in codes(report)


def test_missing_calibration_certificate_rejects(tmp_path):
    def mutate(root, doc):
        doc["references"]["frequency"].pop("calibration_certificate")

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "missing_field" in codes(report)


def test_invalid_calibration_date_rejects(tmp_path):
    root = make_bundle(
        tmp_path,
        mutate=lambda _root, doc: doc["references"]["frequency"]["calibration_certificate"].update(
            valid_until="not-a-date"
        ),
    )
    report = validate_bundle(root)
    assert not report.ok
    assert "invalid_value" in codes(report)


def test_symlinked_audio_rejects(tmp_path):
    root = make_bundle(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes((root / "audio/take.wav").read_bytes())
    audio = root / "audio/take.wav"
    audio.unlink()
    audio.symlink_to(outside)
    report = validate_bundle(root)
    assert "symlink_refused" in codes(report)


def test_low_reference_snr_rejects(tmp_path):
    def mutate(root, doc):
        doc["references"]["reference_snr_db"] = 3.0

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "invalid_value" in codes(report)


def test_wrong_audio_hash_rejects(tmp_path):
    def mutate(root, doc):
        doc["audio"][0]["sha256"] = "0" * 64

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "hash_mismatch" in codes(report)


def test_placeholder_authorization_rejects(tmp_path):
    def mutate(root, doc):
        doc["authorization"]["site_id"] = "TBD"

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "placeholder" in codes(report)


def test_path_escape_rejects(tmp_path):
    def mutate(root, doc):
        doc["audio"][0]["path"] = "../outside.wav"

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "path_escape" in codes(report)


def test_bad_schema_version_and_consent_hash_reject(tmp_path):
    def mutate(root, doc):
        doc["schema_version"] = "e1-0-bundle-0.9"
        doc["authorization"]["consent_sha256"] = "short"

    report = validate_bundle(make_bundle(tmp_path, mutate=mutate))
    assert "schema_version" in codes(report)
    assert "invalid_hash" in codes(report)


def test_cli_exit_codes(tmp_path, capsys):
    valid = make_bundle(tmp_path / "valid")
    assert main(["--bundle", str(valid)]) == 0
    assert "bundle valid" in capsys.readouterr().out
    invalid = make_bundle(tmp_path / "invalid", mutate=lambda root, doc: doc["references"].pop("motion"))
    assert main(["--bundle", str(invalid)]) == 1


def test_alternate_manifest_filename_is_accepted(tmp_path):
    root = make_bundle(tmp_path)
    (root / "bundle.json").rename(root / "e1-capture.json")
    report = validate_bundle(root)
    assert report.ok, report.errors
