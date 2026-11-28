"""API contract tests for assignment creation and student progress updates."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import AssignmentStatus, AssignmentTargetType, RecipientStatus, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains import assignments as assignment_domain
from app.main import app


class FakeResult:
    def scalars(self):
        return self

    def all(self):
        return [uuid4(), uuid4()]


class FakeSession:
    async def execute(self, statement):
        return FakeResult()

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
def student():
    return User(
        id=uuid4(),
        full_name="Demo Student",
        email="student@example.com",
        password_hash="not-used",
        is_active=True,
    )


def authenticate_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_assignment_creation_requires_authentication(client):
    response = client.post(
        "/api/v1/assignments",
        json={
            "classroom_id": str(uuid4()),
            "title": "Math homework",
            "instructions": "Complete questions 1 to 5.",
            "target_type": "class",
            "timezone": "Asia/Kolkata",
        },
    )
    assert response.status_code == 401


def test_assignment_title_must_have_two_non_whitespace_characters(client, student):
    authenticate_as(student)
    response = client.post(
        "/api/v1/assignments",
        json={
            "classroom_id": str(uuid4()),
            "title": " x ",
            "instructions": "Complete questions 1 to 5.",
            "target_type": "class",
            "timezone": "Asia/Kolkata",
        },
    )
    assert response.status_code == 422


def test_student_cannot_request_teacher_or_system_progress_status(client, student):
    authenticate_as(student)
    response = client.patch(
        f"/api/v1/assignments/recipients/{uuid4()}/progress",
        json={"status": "completed"},
    )
    assert response.status_code == 422


def test_teacher_can_create_class_assignment(client, student, monkeypatch):
    authenticate_as(student)
    assignment = SimpleNamespace(
        id=uuid4(),
        classroom_id=uuid4(),
        created_by_id=student.id,
        title="Math homework",
        instructions="Complete questions 1 to 5.",
        target_type=AssignmentTargetType.CLASS,
        status=AssignmentStatus.ASSIGNED,
        due_at=None,
        timezone="Asia/Kolkata",
    )
    captured = {}

    async def create(db, **kwargs):
        captured.update(kwargs)
        return assignment

    monkeypatch.setattr("app.api.assignments.create_assignment", create)
    response = client.post(
        "/api/v1/assignments",
        json={
            "classroom_id": str(assignment.classroom_id),
            "title": "Math homework",
            "instructions": "Complete questions 1 to 5.",
            "target_type": "class",
            "timezone": "Asia/Kolkata",
        },
    )

    assert response.status_code == 201
    assert captured["actor_user_id"] == student.id
    assert captured["classroom_id"] == assignment.classroom_id
    assert captured["target_type"] == AssignmentTargetType.CLASS
    data = response.json()
    assert data["id"] == str(assignment.id)
    assert data["status"] == "assigned"
    assert len(data["recipient_ids"]) == 2


def test_student_can_update_own_progress(client, student, monkeypatch):
    authenticate_as(student)
    recipient = SimpleNamespace(
        id=uuid4(),
        assignment_id=uuid4(),
        student_id=student.id,
        status=RecipientStatus.IN_PROGRESS,
        blocked_reason=None,
    )

    async def transition(db, **kwargs):
        assert kwargs["actor_user_id"] == student.id
        assert kwargs["recipient_id"] == recipient.id
        assert kwargs["new_status"] == RecipientStatus.IN_PROGRESS
        return recipient

    monkeypatch.setattr("app.api.assignments.transition_recipient_status", transition)
    response = client.patch(
        f"/api/v1/assignments/recipients/{recipient.id}/progress",
        json={"status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert response.json()["student_id"] == str(student.id)


def test_invalid_progress_transition_is_rejected(client, student, monkeypatch):
    authenticate_as(student)

    async def denied(*args, **kwargs):
        raise assignment_domain.DomainRuleViolation(
            "Only the assigned student may update this progress."
        )

    monkeypatch.setattr("app.api.assignments.transition_recipient_status", denied)
    response = client.patch(
        f"/api/v1/assignments/recipients/{uuid4()}/progress",
        json={"status": "in_progress"},
    )

    assert response.status_code == 403


def test_assignment_listing_requires_authentication(client):
    response = client.get("/api/v1/assignments")
    assert response.status_code == 401


def test_assignment_listing_returns_only_requesting_students_progress(client, student, monkeypatch):
    authenticate_as(student)
    assignment = SimpleNamespace(
        id=uuid4(),
        classroom_id=uuid4(),
        created_by_id=uuid4(),
        title="Science project",
        instructions="Prepare a short report.",
        target_type=AssignmentTargetType.INDIVIDUAL,
        status=AssignmentStatus.ASSIGNED,
        due_at=None,
        timezone="Asia/Kolkata",
    )
    recipient = SimpleNamespace(
        id=uuid4(),
        status=RecipientStatus.IN_PROGRESS,
        blocked_reason=None,
    )
    captured = {}

    async def listing(db, **kwargs):
        captured.update(kwargs)
        return [(assignment, recipient)]

    monkeypatch.setattr("app.api.assignments.list_user_assignments", listing)
    response = client.get(f"/api/v1/assignments?classroom_id={assignment.classroom_id}")

    assert response.status_code == 200
    assert captured["user_id"] == student.id
    assert captured["classroom_id"] == assignment.classroom_id
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(assignment.id)
    assert data[0]["recipient_id"] == str(recipient.id)
    assert data[0]["my_status"] == "in_progress"


def test_teacher_assignment_listing_does_not_expose_student_progress(client, student, monkeypatch):
    authenticate_as(student)
    assignment = SimpleNamespace(
        id=uuid4(),
        classroom_id=uuid4(),
        created_by_id=student.id,
        title="Class assignment",
        instructions="Read chapter 1.",
        target_type=AssignmentTargetType.CLASS,
        status=AssignmentStatus.ASSIGNED,
        due_at=None,
        timezone="Asia/Kolkata",
    )

    async def listing(db, **kwargs):
        return [(assignment, None)]

    monkeypatch.setattr("app.api.assignments.list_user_assignments", listing)
    response = client.get("/api/v1/assignments")

    assert response.status_code == 200
    assert response.json()[0]["recipient_id"] is None
    assert response.json()[0]["my_status"] is None


@pytest.mark.parametrize(
    ("target_type", "target_field"),
    [
        ("individual", "student_ids"),
        ("group", "group_ids"),
    ],
)
def test_teacher_can_create_targeted_assignment(
    client, student, monkeypatch, target_type, target_field
):
    authenticate_as(student)
    classroom_id = uuid4()
    target_ids = [uuid4(), uuid4()]
    assignment = SimpleNamespace(
        id=uuid4(),
        classroom_id=classroom_id,
        created_by_id=student.id,
        title="Targeted assignment",
        instructions="Complete the assigned task.",
        target_type=AssignmentTargetType(target_type),
        status=AssignmentStatus.ASSIGNED,
        due_at=None,
        timezone="Asia/Kolkata",
    )
    captured = {}

    async def create(db, **kwargs):
        captured.update(kwargs)
        return assignment

    monkeypatch.setattr("app.api.assignments.create_assignment", create)
    payload = {
        "classroom_id": str(classroom_id),
        "title": "Targeted assignment",
        "instructions": "Complete the assigned task.",
        "target_type": target_type,
        "timezone": "Asia/Kolkata",
        target_field: [str(value) for value in target_ids],
    }
    response = client.post("/api/v1/assignments", json=payload)

    assert response.status_code == 201
    assert captured[target_field] == target_ids
    assert captured["target_type"] == AssignmentTargetType(target_type)
    assert response.json()["target_type"] == target_type
