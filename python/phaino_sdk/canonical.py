"""PCJ-0 canonical JSON for the Python side of the Rust/Python boundary.

The rules are fixed by ADR 0006 and must match the Rust core exactly for identity tuples
and digests: ASCII-only keys sorted by code unit, JCS string escaping, ECMAScript number
formatting, no whitespace, UTF-8 output, and rejection of NaN/Infinity and lone surrogates.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

MAX_SAFE_INTEGER = 9_007_199_254_740_991

_JSON_NUMBER_ESCAPE = re.compile(r"[eE]")


class CanonicalError(ValueError):
    """Raised when a value cannot be represented in PCJ-0."""


def canonical_json(value: Any) -> str:
    """Returns the PCJ-0 text for a JSON-native Python value."""
    return pcj0_bytes(value).decode("utf-8")


def pcj0_bytes(value: Any) -> bytes:
    """Returns the PCJ-0 UTF-8 bytes for a JSON-native Python value."""
    return _write_value(value).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Returns the lowercase SHA-256 hex digest of the PCJ-0 bytes of `value`."""
    return hashlib.sha256(pcj0_bytes(value)).hexdigest()


def _write_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return _write_integer(value)
    if isinstance(value, float):
        return _write_float(value)
    if isinstance(value, str):
        return _write_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_write_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return _write_object(value)
    raise CanonicalError(f"unsupported PCJ-0 value type: {type(value).__name__}")


def _write_integer(value: int) -> str:
    if abs(value) <= MAX_SAFE_INTEGER:
        return str(value)
    try:
        return _write_float(float(value))
    except OverflowError as error:
        raise CanonicalError("integer is outside the IEEE 754 range") from error


def _write_float(value: float) -> str:
    if not math.isfinite(value):
        raise CanonicalError("PCJ-0 cannot serialize NaN or infinity")
    if value == 0.0:
        return "0"

    negative = math.copysign(1.0, value) < 0.0
    text = repr(abs(value))
    if "e" in text or "E" in text:
        mantissa, exponent_text = _JSON_NUMBER_ESCAPE.split(text, maxsplit=1)
        exponent = int(exponent_text)
    else:
        mantissa, exponent = text, 0
    if "." in mantissa:
        integer_part, fraction_part = mantissa.split(".", maxsplit=1)
    else:
        integer_part, fraction_part = mantissa, ""

    digits = (integer_part + fraction_part).lstrip("0")
    exponent -= len(fraction_part)
    if not digits:
        return "0"
    stripped = digits.rstrip("0")
    exponent += len(digits) - len(stripped)
    digits = stripped

    digit_count = len(digits)
    scientific_exponent = exponent + digit_count - 1
    decimal_position = scientific_exponent + 1

    if digit_count <= decimal_position <= 21:
        rendered = digits + "0" * (decimal_position - digit_count)
    elif 0 < decimal_position <= 21:
        rendered = digits[:decimal_position] + "." + digits[decimal_position:]
    elif -6 < decimal_position <= 0:
        rendered = "0." + "0" * (-decimal_position) + digits
    else:
        rendered = digits[0]
        if digit_count > 1:
            rendered += "." + digits[1:]
        rendered += "e"
        rendered += "+" if decimal_position - 1 >= 0 else "-"
        rendered += str(abs(decimal_position - 1))

    return "-" + rendered if negative else rendered


def _write_string(value: str) -> str:
    escaped: list[str] = ['"']
    for character in value:
        code_point = ord(character)
        if 0xD800 <= code_point <= 0xDFFF:
            raise CanonicalError("PCJ-0 cannot serialize lone surrogates")
        if character == '"':
            escaped.append('\\"')
        elif character == "\\":
            escaped.append("\\\\")
        elif character == "\b":
            escaped.append("\\b")
        elif character == "\t":
            escaped.append("\\t")
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\f":
            escaped.append("\\f")
        elif character == "\r":
            escaped.append("\\r")
        elif code_point < 0x20:
            escaped.append(f"\\u{code_point:04x}")
        else:
            escaped.append(character)
    escaped.append('"')
    return "".join(escaped)


def _write_object(value: dict[Any, Any]) -> str:
    for key in value:
        if not isinstance(key, str):
            raise CanonicalError("PCJ-0 object keys must be strings")
        if not key.isascii():
            raise CanonicalError(f"PCJ-0 object keys must be ASCII: {key!r}")
    parts = []
    for key in sorted(value):
        parts.append(_write_string(key) + ":" + _write_value(value[key]))
    return "{" + ",".join(parts) + "}"
