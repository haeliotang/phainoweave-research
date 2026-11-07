"""Validate an E1-0 raw capture bundle before it can enter the fabric.

The bundle is a directory containing a `bundle.json` manifest and the raw
files it references.  The gate is intentionally strict: a missing independent
frequency/time reference, calibration certificate, site authorization, consent
hash or file digest rejects the bundle at snapshot-creation time rather than
being discovered later in analysis.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "e1-0-bundle-1.0.0"
BUNDLE_ID = re.compile(r"^e1b_[0-9a-f]{16}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDERS = {"", "tbd", "todo", "none", "null", "n/a", "unknown", "fixme"}
TIME_KINDS = {"pps", "gps", "audio_anchor"}
TOP_LEVEL = (
    "schema_version",
    "bundle_id",
    "measurement_model_id",
    "audio",
    "references",
    "authorization",
    "environment",
    "operator",
)


@dataclass
class ValidationError:
    code: str
    path: str
    message: str


@dataclass
class BundleReport:
    bundle: str
    errors: list[ValidationError] = field(default_factory=list)
    checked_files: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, code: str, path: str, message: str) -> None:
        self.errors.append(ValidationError(code=code, path=path, message=message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle,
            "ok": self.ok,
            "checked_files": self.checked_files,
            "errors": [error.__dict__ for error in self.errors],
        }


def _placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDERS


def _is_iso_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _require(obj: dict[str, Any], key: str, path: str, report: BundleReport) -> Any:
    if key not in obj:
        report.add("missing_field", f"{path}.{key}", "required field is missing")
        return None
    value = obj[key]
    if _placeholder(value):
        report.add("placeholder", f"{path}.{key}", "field is empty or a placeholder")
    return value


def _hash(obj: dict[str, Any], key: str, path: str, report: BundleReport) -> str | None:
    value = _require(obj, key, path, report)
    if value is None:
        return None
    if not isinstance(value, str) or not HEX64.match(value):
        report.add("invalid_hash", f"{path}.{key}", "expected a lowercase 64-hex SHA-256")
        return None
    return value


def _number(
    obj: dict[str, Any], key: str, path: str, report: BundleReport, *, positive: bool = True
) -> float | None:
    value = _require(obj, key, path, report)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        report.add("invalid_value", f"{path}.{key}", "expected a number")
        return None
    if positive and not value > 0:
        report.add("invalid_value", f"{path}.{key}", "expected a positive number")
        return None
    if not positive and value < 0:
        report.add("invalid_value", f"{path}.{key}", "expected a non-negative number")
        return None
    return float(value)


def _file(bundle: Path, obj: dict[str, Any], path: str, report: BundleReport) -> None:
    rel = _require(obj, "path", path, report)
    digest = _hash(obj, "sha256", path, report)
    if rel is None or digest is None:
        return
    if not isinstance(rel, str) or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        report.add("path_escape", f"{path}.path", "file path must stay inside the bundle")
        return
    target = bundle / rel
    report.checked_files += 1
    if target.is_symlink():
        report.add("symlink_refused", f"{path}.path", "reference files must not be symlinks")
        return
    if not target.is_file():
        report.add("missing_file", f"{path}.path", f"file does not exist: {rel}")
        return
    hasher = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    actual = hasher.hexdigest()
    if actual != digest:
        report.add("hash_mismatch", f"{path}.sha256", f"expected {digest}, got {actual}")


def _calibration(obj: dict[str, Any], path: str, report: BundleReport) -> None:
    certificate = _require(obj, "calibration_certificate", path, report)
    if not isinstance(certificate, dict):
        if certificate is not None:
            report.add("invalid_value", f"{path}.calibration_certificate", "expected an object")
        return
    _require(certificate, "id", f"{path}.calibration_certificate", report)
    _require(certificate, "issued_by", f"{path}.calibration_certificate", report)
    _number(certificate, "uncertainty_hz", f"{path}.calibration_certificate", report)
    valid_until = _require(certificate, "valid_until", f"{path}.calibration_certificate", report)
    if valid_until is not None and not _is_iso_date(valid_until):
        report.add("invalid_value", f"{path}.calibration_certificate.valid_until", "expected an ISO YYYY-MM-DD date")


def _references(bundle: Path, references: Any, report: BundleReport) -> None:
    path = "references"
    if not isinstance(references, dict):
        report.add("invalid_value", path, "expected an object")
        return
    reference_snr = _number(references, "reference_snr_db", path, report, positive=False)
    if reference_snr is not None and reference_snr < 10.0:
        report.add("invalid_value", f"{path}.reference_snr_db", "reference SNR must be >= 10 dB")
    frequency = _require(references, "frequency", path, report)
    if isinstance(frequency, dict):
        _file(bundle, frequency, f"{path}.frequency", report)
        _calibration(frequency, f"{path}.frequency", report)
    elif frequency is not None:
        report.add("invalid_value", f"{path}.frequency", "expected an object")

    time_ref = _require(references, "time", path, report)
    if isinstance(time_ref, dict):
        kind = _require(time_ref, "kind", f"{path}.time", report)
        if kind is not None and kind not in TIME_KINDS:
            report.add("invalid_value", f"{path}.time.kind", f"expected one of {sorted(TIME_KINDS)}")
        _file(bundle, time_ref, f"{path}.time", report)
        _number(time_ref, "uncertainty_s", f"{path}.time", report)
    elif time_ref is not None:
        report.add("invalid_value", f"{path}.time", "expected an object")

    motion = _require(references, "motion", path, report)
    if isinstance(motion, dict):
        _file(bundle, motion, f"{path}.motion", report)
        _number(motion, "uncertainty_m", f"{path}.motion", report)
    elif motion is not None:
        report.add("invalid_value", f"{path}.motion", "expected an object")


def _authorization(authorization: Any, report: BundleReport) -> None:
    path = "authorization"
    if not isinstance(authorization, dict):
        report.add("invalid_value", path, "expected an object")
        return
    _require(authorization, "site_id", path, report)
    _require(authorization, "jurisdiction", path, report)
    _require(authorization, "legal_review_id", path, report)
    _hash(authorization, "consent_sha256", path, report)


def _environment(environment: Any, report: BundleReport) -> None:
    path = "environment"
    if not isinstance(environment, dict):
        report.add("invalid_value", path, "expected an object")
        return
    _number(environment, "temperature_c", path, report, positive=False)
    humidity = _number(environment, "humidity_pct", path, report, positive=False)
    if humidity is not None and not 0 <= humidity <= 100:
        report.add("invalid_value", f"{path}.humidity_pct", "expected 0..100")
    _number(environment, "wind_mps", path, report, positive=False)
    _number(environment, "sound_speed_mps", path, report)


def _audio(bundle: Path, audio: Any, report: BundleReport) -> None:
    if not isinstance(audio, list) or not audio:
        report.add("invalid_value", "audio", "expected a non-empty list")
        return
    seen: set[str] = set()
    for index, item in enumerate(audio):
        path = f"audio[{index}]"
        if not isinstance(item, dict):
            report.add("invalid_value", path, "expected an object")
            continue
        rel = item.get("path")
        if isinstance(rel, str):
            if rel in seen:
                report.add("duplicate_path", f"{path}.path", f"duplicate audio path {rel}")
            seen.add(rel)
        _file(bundle, item, path, report)
        _number(item, "sample_rate_hz", path, report)
        _number(item, "channels", path, report)
        _number(item, "duration_s", path, report)


def find_manifest(root: Path) -> Path | None:
    """`bundle.json`, else a top-level JSON whose schema_version is E1."""
    conventional = root / "bundle.json"
    if conventional.is_file():
        return conventional
    for path in sorted(root.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema = document.get("schema_version") if isinstance(document, dict) else None
        if isinstance(schema, str) and schema.startswith("e1-0-bundle-"):
            return path
    return None


def validate_bundle(bundle: str | Path) -> BundleReport:
    root = Path(bundle)
    report = BundleReport(bundle=str(root))
    manifest = find_manifest(root)
    if manifest is None:
        report.add("missing_file", "bundle.json", "bundle.json (or an E1 manifest) is required")
        return report
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report.add("invalid_json", manifest.name, str(error))
        return report
    if not isinstance(document, dict):
        report.add("invalid_value", "$", "bundle.json must contain an object")
        return report

    for key in TOP_LEVEL:
        _require(document, key, "$", report)
    if document.get("schema_version") != SCHEMA_VERSION:
        report.add("schema_version", "$.schema_version", f"expected {SCHEMA_VERSION!r}")
    bundle_id = document.get("bundle_id")
    if isinstance(bundle_id, str) and not BUNDLE_ID.match(bundle_id):
        report.add("invalid_value", "$.bundle_id", "expected e1b_<16 lowercase hex>")
    _require(document, "measurement_model_id", "$", report)

    _audio(root, document.get("audio"), report)
    _references(root, document.get("references"), report)
    _authorization(document.get("authorization"), report)
    _environment(document.get("environment"), report)
    operator = document.get("operator")
    if isinstance(operator, dict):
        _require(operator, "id", "$.operator", report)
        _require(operator, "role", "$.operator", report)
    elif operator is not None:
        report.add("invalid_value", "$.operator", "expected an object")
    return report


def format_errors(errors: Iterable[ValidationError]) -> str:
    return "\n".join(f"{error.code} at {error.path}: {error.message}" for error in errors)
