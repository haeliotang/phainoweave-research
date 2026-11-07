import argparse
import json

from .schema import BenchSession, Capture, validate_session


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="E1-0 bench session validator")
    parser.add_argument("--session", required=True, help="bench session JSON path")
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args(argv)
    raw = json.load(open(args.session, encoding="utf-8"))
    session = BenchSession(
        session_id=raw["session_id"],
        measurement_model_id=raw["measurement_model_id"],
        device=raw.get("device", {}),
        environment=raw.get("environment", {}),
        reference=raw.get("reference", {}),
        captures=[Capture(**c) for c in raw.get("captures", [])],
        calibration_split=raw.get("calibration_split", []),
        evaluation_split=raw.get("evaluation_split", []),
        protocol_version=raw.get("protocol_version", "e1-0-bench-1.0.0"),
        notes=raw.get("notes", ""),
    )
    validate_session(session, require_files=args.check_files)
    print(f"bench session valid: {session.session_id} ({len(session.captures)} captures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
