"""Password hashing and JWT helpers for API authentication."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings


# pwdlib's recommended configuration uses Argon2id.
_password_hasher = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return an Argon2id password hash; never persist the raw password."""
    if not password:
        raise ValueError("Password must not be empty.")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its stored Argon2id hash."""
    if not password or not password_hash:
        return False
    return _password_hasher.verify(password, password_hash)


def _jwt_secret() -> str:
    secret = get_settings().jwt_secret_key
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured. Set it in the environment before "
            "using authentication endpoints."
        )
    return secret


def create_access_token(
    subject: UUID | str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed HS256 access token for a user UUID."""
    subject_value = str(subject)
    try:
        UUID(subject_value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Access-token subject must be a valid user UUID.") from exc

    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(
        minutes=get_settings().access_token_expire_minutes
    )
    if lifetime.total_seconds() <= 0:
        raise ValueError("Access-token lifetime must be positive.")

    payload = {
        "sub": subject_value,
        "iat": now,
        "exp": now + lifetime,
        "token_type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify an access token and return its claims.

    PyJWT rejects invalid signatures and expired tokens. We additionally require
    the claims used by this application and validate the UUID subject.
    """
    payload = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "iat", "exp", "token_type"]},
    )
    if payload.get("token_type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token.")

    try:
        UUID(payload["sub"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise jwt.InvalidTokenError("Token subject is not a valid user UUID.") from exc

    return payload
