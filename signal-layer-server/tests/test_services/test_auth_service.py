import time

import pytest

from app.services.auth_service import (
    create_access_token, decode_access_token, hash_password, verify_password,
)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("Secure123!")
    second = hash_password("Secure123!")
    assert first != second
    assert verify_password("Secure123!", first)
    assert not verify_password("incorrect", first)


def test_signed_access_token_round_trip():
    token, expires_at = create_access_token(42)
    assert expires_at > int(time.time())
    assert decode_access_token(token) == 42


def test_tampered_access_token_is_rejected():
    token, _ = create_access_token(42)
    with pytest.raises(ValueError):
        decode_access_token(token[:-1] + ("a" if token[-1] != "a" else "b"))
