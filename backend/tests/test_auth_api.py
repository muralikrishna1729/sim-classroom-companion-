
"""API tests for authentication endpoints."""

from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db
from app.dependencies import auth as auth_dependencies
from app.main import app


# --------------------------------------------------
# Fake database objects
# --------------------------------------------------

class FakeResult:
    """Mimic the SQLAlchemy result used by authentication endpoints."""

    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class FakeAsyncSession:
    """Provide a lightweight database substitute for API tests."""

    def __init__(self, user):
        self.user = user

    async def execute(self, statement):
        return FakeResult(self.user)


# --------------------------------------------------
# Test fixtures and helpers
# --------------------------------------------------

@pytest.fixture
def test_user():
    """Create a sample active user for authentication tests."""

    return User(
        id=uuid4(),
        full_name="Demo Teacher",
        email="teacher@example.com",
        password_hash=hash_password("CorrectPassword123"),
        is_active=True,
    )


@pytest.fixture
def client():
    """Create a test client and restore dependency overrides afterward."""

    original_overrides = app.dependency_overrides.copy()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture
def configure_database():
    """Override the database dependency with a fake session."""

    def configure(user):
        async def override_get_db():
            yield FakeAsyncSession(user)

        app.dependency_overrides[get_db] = override_get_db

    return configure


# --------------------------------------------------
# Login tests
# --------------------------------------------------

def test_successful_login(
    client,
    test_user,
    configure_database,
    monkeypatch,
):
    """A valid email and password should return an access token."""

    configure_database(test_user)

    monkeypatch.setattr(
        auth_api,
        "create_access_token",
        lambda subject: "test-access-token",
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": " TEACHER@EXAMPLE.COM ",
            "password": "CorrectPassword123",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "test-access-token",
        "token_type": "bearer",
    }


def test_login_with_wrong_password(
    client,
    test_user,
    configure_database,
):
    """An incorrect password should return HTTP 401."""

    configure_database(test_user)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "teacher@example.com",
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_with_unknown_email(
    client,
    configure_database,
):
    """An email not found in the database should return HTTP 401."""

    configure_database(None)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "SomePassword123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_inactive_user_cannot_login(
    client,
    test_user,
    configure_database,
):
    """Inactive users must not receive access tokens."""

    test_user.is_active = False
    configure_database(test_user)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "teacher@example.com",
            "password": "CorrectPassword123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


# --------------------------------------------------
# Current-user authentication tests
# --------------------------------------------------

def test_me_without_token_returns_401(client):
    """Requests without a Bearer token must be rejected."""

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_with_invalid_token_returns_401(
    client,
    monkeypatch,
):
    """Invalid JWTs must be rejected."""

    def invalid_token(token):
        raise jwt.InvalidTokenError("Invalid token")

    monkeypatch.setattr(
        auth_dependencies,
        "decode_access_token",
        invalid_token,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_me_with_expired_token_returns_401(
    client,
    monkeypatch,
):
    """Expired JWTs must be rejected."""

    def expired_token(token):
        raise jwt.ExpiredSignatureError("Token expired")

    monkeypatch.setattr(
        auth_dependencies,
        "decode_access_token",
        expired_token,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer expired-token"},
    )

    assert response.status_code == 401


def test_successful_me_request(
    client,
    test_user,
    configure_database,
    monkeypatch,
):
    """A valid token should return the authenticated user's profile."""

    configure_database(test_user)

    monkeypatch.setattr(
        auth_dependencies,
        "decode_access_token",
        lambda token: {"sub": str(test_user.id)},
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer valid-test-token"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == str(test_user.id)
    assert data["full_name"] == "Demo Teacher"
    assert data["email"] == "teacher@example.com"

    # Password hashes must never be exposed through the API.
    assert "password_hash" not in data



def test_inactive_user_with_existing_token_cannot_access_me(
    client,
    test_user,
    configure_database,
    monkeypatch,
):
    """An inactive user must not access protected endpoints with an old token."""

    # Simulate an account that was deactivated after token issuance.
    test_user.is_active = False
    configure_database(test_user)

    # Simulate a valid, previously issued JWT.
    monkeypatch.setattr(
        auth_dependencies,
        "decode_access_token",
        lambda token: {"sub": str(test_user.id)},
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer valid-existing-token"},
    )

    assert response.status_code == 401
