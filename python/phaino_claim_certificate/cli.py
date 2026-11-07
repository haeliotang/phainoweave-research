"""CLI for the independent E0 clock-invariance certificate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .certificate import run_certificate
from .protocol import (
    ClaimsProtocolError,
    builtin_protocol,
    load_claims_protocol,
    load_method_protocol,
)
from .report import certificate_json, certificate_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m phaino_claim_certificate",
        description=(
            "Independent numerical certificate that the E0 forward observation is "
            "preserved by the declared clock transformations and that the declared claim "
            "invariance verdicts hold. Accepts the certificate's own claims schema or the "
            "method workstream's PR-4e claims-protocol schema."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--claims",
        help=(
            "claims protocol JSON in the certificate's own schema; a method-schema file is "
            "auto-detected. Omitted uses the minimal built-in protocol."
        ),
    )
    group.add_argument(
        "--method-protocol",
        help="method workstream PR-4e claims-protocol JSON (declared_model/clock_model/claims[])",
    )
    parser.add_argument(
        "--self-audit",
        action="store_true",
        help="also print the generator-coverage/claim self-audit section",
    )
    parser.add_argument("--out", required=True, help="certificate.json path")
    parser.add_argument("--markdown", required=True, help="certificate.md path")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    try:
        if args.method_protocol:
            protocol = load_method_protocol(args.method_protocol)
        elif args.claims:
            protocol = (
                load_method_protocol(args.claims)
                if _looks_like_method_protocol(args.claims)
                else load_claims_protocol(args.claims)
            )
        else:
            protocol = builtin_protocol()
        certificate = run_certificate(protocol)
        _write(args.out, certificate_json(certificate))
        _write(args.markdown, certificate_markdown(certificate))
    except ClaimsProtocolError as error:
        print(f"claims-protocol error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"certificate error: {error}", file=sys.stderr)
        return 2

    if protocol.builtin:
        print("claims protocol: built-in minimal (method-side claims.json not supplied)")
    elif protocol.method_schema:
        print(f"method protocol: {protocol.source}")
        print(f"protocol digest: {protocol.document.get('protocol_digest')}")
        print(f"source sha256: {protocol.source_sha256}")
    else:
        print(f"claims protocol: {protocol.source}")
    for claim in certificate["claims"]:
        print(
            f"{claim['claim']}: symbolic={claim['symbolic_verdict']} "
            f"numeric={claim['numeric_verdict']} "
            f"max_rel={claim['max_relative_mismatch']:.3e} "
            f"agrees={claim['agrees_with_symbolic']}"
        )
    if args.self_audit:
        print("self-audit:")
        print(json.dumps(certificate["self_audit"], sort_keys=True, indent=2))
    print(f"disagreements: {len(certificate['symbolic_numeric_disagreements'])}")
    print(f"incomplete_group: {certificate['incomplete_group']}")
    print(f"certificate: {args.out}")
    print(f"markdown: {args.markdown}")
    return 0


def _write(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())


def _looks_like_method_protocol(path: str | Path) -> bool:
    """True for the method workstream's PR-4e claims-protocol schema."""
    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        return False
    if not isinstance(document, dict):
        return False
    required = {
        "declared_model",
        "clock_model",
        "symmetry_group",
        "convention_reconciliation",
        "claims",
        "thresholds",
    }
    if not required.issubset(document):
        return False
    claims = document.get("claims")
    return isinstance(claims, list) and bool(claims) and all(
        isinstance(claim, dict) and "claim_id" in claim for claim in claims
    )
