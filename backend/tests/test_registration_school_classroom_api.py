"""Integration-style API tests for registration, schools, and classroom routes.

The tests replace database/domain boundaries so they can verify HTTP contracts,
authentication requirements, response shapes, and error mapping without relying
on a developer's local database.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import ClassRole, MembershipStatus, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains import classrooms as classroom_domain
from app.domains import registration as registration_domain
from app.domains import schools as school_domain
from app.main import app


class FakeSession:
    async def commit(self):
        pass

    async def refresh(self, instance):
        pass

    async def rollback(self):
        pass


@pytest.fixture
def client():
    original_overrides = app.dependency_overrides.copy()

    async def override_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture
def current_user():
    return User(
        id=uuid4(),
        full_name="Demo Coordinator",
        email="coordinator@example.com",
        password_hash="not-used-in-these-tests",
        is_active=True,
    )


def authenticate_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_registration_returns_user_and_access_token(client, monkeypatch):
    user = User(
        id=uuid4(),
        full_name="Demo Teacher",
        email="teacher@example.com",
        password_hash="hashed",
        is_active=True,
    )
    monkeypatch.setattr("app.api.auth.register_user", _async_return(user))
    monkeypatch.setattr("app.api.auth.create_access_token", lambda subject: "test-token")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "  Demo   Teacher ",
            "email": " TEACHER@EXAMPLE.COM ",
            "password": "StrongPassword123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user"] == {
        "id": str(user.id),
        "full_name": "Demo Teacher",
        "email": "teacher@example.com",
    }
    assert data["access_token"] == "test-token"
    assert data["token_type"] == "bearer"
    assert "password_hash" not in data


def test_registration_rejects_duplicate_email(client, monkeypatch):
    async def duplicate(*args, **kwargs):
        raise registration_domain.RegistrationRuleViolation(
            "An account with this email already exists."
        )

    monkeypatch.setattr("app.api.auth.register_user", duplicate)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Demo Teacher",
            "email": "teacher@example.com",
            "password": "StrongPassword123",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists."


def test_registration_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Demo Teacher",
            "email": "teacher@example.com",
            "password": "short",
        },
    )
    assert response.status_code == 422


def test_school_creation_requires_authentication(client):
    response = client.post(
        "/api/v1/schools",
        json={"name": "SIM Demo School", "timezone": "Asia/Kolkata"},
    )
    assert response.status_code == 401


def test_coordinator_can_create_school(client, current_user, monkeypatch):
    authenticate_as(current_user)
    school = SimpleNamespace(
        id=uuid4(),
        name="SIM Demo School",
        timezone="Asia/Kolkata",
        is_active=True,
    )
    monkeypatch.setattr("app.api.schools.create_school", _async_return(school))

    response = client.post(
        "/api/v1/schools",
        json={"name": " SIM   Demo School ", "timezone": "Asia/Kolkata"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(school.id),
        "name": "SIM Demo School",
        "timezone": "Asia/Kolkata",
        "is_active": True,
    }


def test_school_list_returns_only_domain_service_results(
    client, current_user, monkeypatch
):
    authenticate_as(current_user)
    school = SimpleNamespace(
        id=uuid4(),
        name="SIM Demo School",
        timezone="Asia/Kolkata",
        is_active=True,
    )
    monkeypatch.setattr("app.api.schools.list_user_schools", _async_return([school]))

    response = client.get("/api/v1/schools/me")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(school.id),
            "name": "SIM Demo School",
            "timezone": "Asia/Kolkata",
            "is_active": True,
        }
    ]


def test_classroom_creation_requires_authentication(client):
    response = client.post(
        "/api/v1/classrooms",
        json={"school_id": str(uuid4()), "name": "Class 10-A"},
    )
    assert response.status_code == 401


def test_coordinator_can_create_classroom(client, current_user, monkeypatch):
    authenticate_as(current_user)
    classroom = SimpleNamespace(
        id=uuid4(),
        school_id=uuid4(),
        name="Class 10-A",
        grade_label="Grade 10",
    )
    monkeypatch.setattr(
        "app.api.classrooms.create_classroom", _async_return(classroom)
    )

    response = client.post(
        "/api/v1/classrooms",
        json={
            "school_id": str(classroom.school_id),
            "name": " Class   10-A ",
            "grade_label": " Grade 10 ",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(classroom.id),
        "school_id": str(classroom.school_id),
        "name": "Class 10-A",
        "grade_label": "Grade 10",
    }


def test_classroom_access_rule_violation_is_forbidden(
    client, current_user, monkeypatch
):
    authenticate_as(current_user)

    async def denied(*args, **kwargs):
        raise classroom_domain.ClassroomRuleViolation(
            "An active coordinator membership is required for this school."
        )

    monkeypatch.setattr("app.api.classrooms.create_classroom", denied)
    response = client.post(
        "/api/v1/classrooms",
        json={"school_id": str(uuid4()), "name": "Class 10-A"},
    )

    assert response.status_code == 403


def test_classroom_member_endpoint_uses_authenticated_actor(
    client, current_user, monkeypatch
):
    authenticate_as(current_user)
    classroom_id = uuid4()
    student_id = uuid4()
    membership = SimpleNamespace(
        classroom_id=classroom_id,
        user_id=student_id,
        role=ClassRole.STUDENT,
        status=MembershipStatus.ACTIVE,
    )

    async def add_member(db, **kwargs):
        assert kwargs["actor_user_id"] == current_user.id
        assert kwargs["classroom_id"] == classroom_id
        assert kwargs["user_id"] == student_id
        assert kwargs["role"] == ClassRole.STUDENT
        return membership

    monkeypatch.setattr("app.api.classrooms.add_classroom_member", add_member)

    response = client.post(
        f"/api/v1/classrooms/{classroom_id}/students",
        json={"user_id": str(student_id)},
    )

    assert response.status_code == 201
    assert response.json() == {
        "classroom_id": str(classroom_id),
        "user_id": str(student_id),
        "role": "student",
        "status": "active",
    }


def _async_return(value):
    async def result(*args, **kwargs):
        return value

    return result
