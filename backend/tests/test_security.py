from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest

from app.core import security


@pytest.fixture
def configured_jwt(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="test-only-secret-key-that-is-long-enough-123456",
            access_token_expire_minutes=30,
        ),
    )


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "Correct-Horse-Battery-Staple-42"
    stored_hash = security.hash_password(password)

    assert stored_hash != password
    assert stored_hash.startswith("$argon2id$")
    assert security.verify_password(password, stored_hash)
    assert not security.verify_password("wrong-password", stored_hash)


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValueError):
        security.hash_password("")


def test_access_token_contains_user_subject_and_access_type(configured_jwt) -> None:
    user_id = uuid4()

    token = security.create_access_token(user_id)
    claims = security.decode_access_token(token)

    assert claims["sub"] == str(user_id)
    assert claims["token_type"] == "access"


def test_expired_access_token_is_rejected(configured_jwt) -> None:
    token = security.create_access_token(uuid4(), expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected(configured_jwt, monkeypatch) -> None:
    token = security.create_access_token(uuid4())
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="a-different-test-secret-that-is-long-enough-123456",
            access_token_expire_minutes=30,
        ),
    )

    with pytest.raises(jwt.InvalidSignatureError):
        security.decode_access_token(token)


def test_non_access_token_is_rejected(configured_jwt) -> None:
    now = security.datetime.now(security.timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "token_type": "refresh",
        },
        "test-only-secret-key-that-is-long-enough-123456",
        algorithm=security.JWT_ALGORITHM,
    )

    with pytest.raises(jwt.InvalidTokenError, match="not an access token"):
        security.decode_access_token(token)


def test_invalid_uuid_subject_is_rejected(configured_jwt) -> None:
    now = security.datetime.now(security.timezone.utc)
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "token_type": "access",
        },
        "test-only-secret-key-that-is-long-enough-123456",
        algorithm=security.JWT_ALGORITHM,
    )

    with pytest.raises(jwt.InvalidTokenError, match="valid user UUID"):
        security.decode_access_token(token)
