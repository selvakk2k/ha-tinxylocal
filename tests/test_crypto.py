"""Unit tests for pure-Python XXTEA encryption in ha-tinxylocal."""

import pytest
from custom_components.tinxylocal.crypto import (
    derive_key,
    encrypt_tinxy_payload,
    longs_to_bytes,
    str_to_longs,
    xxtea_encrypt,
)


def xxtea_decrypt(v: list[int], k: list[int]) -> list[int]:
    """Helper decrypt function for round-trip validation."""
    n = len(v)
    delta = 0x9E3779B9
    rounds = 6 + 52 // n
    sum_val = (rounds * delta) & 0xFFFFFFFF
    y = v[0]
    for _ in range(rounds):
        e = (sum_val >> 2) & 3
        for p in range(n - 1, -1, -1):
            z = v[(p - 1 + n) % n]
            term1 = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) & 0xFFFFFFFF
            term2 = ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z)) & 0xFFFFFFFF
            mx = (term1 ^ term2) & 0xFFFFFFFF
            v[p] = (v[p] - mx) & 0xFFFFFFFF
            y = v[p]
        sum_val = (sum_val - delta) & 0xFFFFFFFF
    return v


def test_xxtea_parity_with_go_cli():
    """Verify that Python output exactly matches the compiled Go CLI output."""
    pw = "my_secret_device_pass"
    ts = 1788774045
    expected_hex = "3682322e3fd66d7760c87c8b"

    actual_hex = encrypt_tinxy_payload(pw, timestamp=ts)
    assert actual_hex == expected_hex


def test_key_derivation_padding():
    """Verify key padding for short passwords."""
    short_pw = b"short"
    k = derive_key(short_pw)
    assert len(k) == 4  # 4 x 32-bit uints = 16 bytes


def test_round_trip_encryption_decryption():
    """Verify encrypt and decrypt round trip."""
    pw = "test_password_12345"
    ts = 1712345678
    token_hex = encrypt_tinxy_payload(pw, timestamp=ts)

    # Decrypt
    raw_bytes = bytes.fromhex(token_hex)
    v = str_to_longs(raw_bytes)
    k = derive_key(pw.encode("utf-8"))
    decrypted_v = xxtea_decrypt(v, k)
    decrypted_bytes = longs_to_bytes(decrypted_v)

    recovered_ts = int(decrypted_bytes.split(b"\x00")[0].decode("utf-8"))
    assert recovered_ts == ts
