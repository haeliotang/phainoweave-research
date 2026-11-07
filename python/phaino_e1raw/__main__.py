import argparse
import json

from .validate import format_errors, validate_bundle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate an E1-0 raw capture bundle")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = validate_bundle(args.bundle)
    if args.json:
        print(json.dumps(report.to_dict(), indent=1, sort_keys=True))
    elif report.ok:
        print(f"bundle valid: {report.bundle} ({report.checked_files} files checked)")
    else:
        print(f"bundle invalid: {report.bundle}")
        print(format_errors(report.errors))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
