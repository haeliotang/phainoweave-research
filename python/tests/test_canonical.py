"""PCJ-0 conformance vectors shared with the Rust core (ADR 0006, RFC 8785 Appendix B)."""

import json
import math

import pytest

from phaino_sdk import canonical_sha256, pcj0_bytes
from phaino_sdk.canonical import CanonicalError


def canonical(value: object) -> str:
    return pcj0_bytes(value).decode("utf-8")


def test_rfc8785_number_vectors() -> None:
    value = {
        "numbers": [
            333333333.33333329,
            1e30,
            4.50,
            2e-3,
            1e-27,
            -0.0,
            9007199254740991,
            1e21,
            1e-7,
            1e20,
            5e-324,
            1.7976931348623157e308,
            295147905179352830000.0,
        ]
    }
    assert canonical(value) == (
        '{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27,0,9007199254740991,'
        "1e+21,1e-7,100000000000000000000,5e-324,1.7976931348623157e+308,"
        "295147905179352830000]}"
    )


def test_rfc8785_string_vector() -> None:
    input_document = json.loads(
        r'''{"string":"\u20ac$\u000F\u000aA'\u0042\u0022\u005c\\\"\/"}'''
    )
    expected = r'''{"string":"€$\u000f\nA'B\"\\\\\"/"}'''
    assert canonical(input_document) == expected


def test_ecmascript_boundaries() -> None:
    assert canonical(1e-7) == "1e-7"
    assert canonical(1e-6) == "0.000001"
    assert canonical(1e20) == "100000000000000000000"
    assert canonical(1e21) == "1e+21"
    assert canonical(-0.0) == "0"
    assert canonical(9007199254740991) == "9007199254740991"
    assert canonical(4.0) == "4"


def test_object_keys_are_sorted_and_ascii_only() -> None:
    assert canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    with pytest.raises(CanonicalError):
        canonical({"é": 1})
    with pytest.raises(CanonicalError):
        canonical({"a": math.nan})
    with pytest.raises(CanonicalError):
        canonical({"a": math.inf})
    with pytest.raises(CanonicalError):
        canonical({1: "not a string key"})


def test_hashes_are_stable_and_match_key_order() -> None:
    first = {"b": [True, None, 1.5], "a": "value"}
    second = {"a": "value", "b": [True, None, 1.5]}
    assert canonical_sha256(first) == canonical_sha256(second)
    assert len(canonical_sha256(first)) == 64
    assert canonical_sha256(first).isalnum()
