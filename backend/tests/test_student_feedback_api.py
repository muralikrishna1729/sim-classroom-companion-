from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import RecipientStatus, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.assignments import DomainRuleViolation
from app.main import app


class FakeSession:
    pass


@pytest.fixture
def student():
    return User(
        id=uuid4(),
        full_name="Demo Student",
        email="student-feedback@example.com",
        password_hash="not-used",
        is_active=True,
    )


@pytest.fixture
def client(student):
    original_overrides = app.dependency_overrides.copy()
    session = FakeSession()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: student
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_student_feedback_endpoint_returns_teacher_feedback(client, student, monkeypatch):
    submission_id = uuid4()
    feedback_id = uuid4()
    teacher_id = uuid4()
    created_at = datetime.now(timezone.utc)

    async def fake_get_feedback(db, *, submission_id, actor_user_id):
        assert actor_user_id == student.id
        return (
            SimpleNamespace(id=submission_id),
            SimpleNamespace(status=RecipientStatus.COMPLETED),
            [
                (
                    SimpleNamespace(
                        id=feedback_id,
                        author_id=teacher_id,
                        feedback_text="Good explanation.",
                        created_at=created_at,
                    ),
                    SimpleNamespace(id=teacher_id, full_name="Teacher One"),
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.submissions.get_student_submission_feedback",
        fake_get_feedback,
    )
    response = client.get(f"/api/v1/submissions/{submission_id}/feedback")

    assert response.status_code == 200
    body = response.json()
    assert body["submission_id"] == str(submission_id)
    assert body["recipient_status"] == "completed"
    assert body["feedback"][0]["feedback_id"] == str(feedback_id)
    assert body["feedback"][0]["author_name"] == "Teacher One"
    assert body["feedback"][0]["feedback_text"] == "Good explanation."


def test_student_feedback_endpoint_hides_other_students_submissions(client, monkeypatch):
    async def reject_access(db, *, submission_id, actor_user_id):
        raise DomainRuleViolation("Submission not found.")

    monkeypatch.setattr(
        "app.api.submissions.get_student_submission_feedback",
        reject_access,
    )
    response = client.get(f"/api/v1/submissions/{uuid4()}/feedback")
    assert response.status_code == 404
    assert response.json()["detail"] == "Submission not found."


def test_student_feedback_endpoint_requires_authentication():
    original_overrides = app.dependency_overrides.copy()

    async def override_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as test_client:
            response = test_client.get(f"/api/v1/submissions/{uuid4()}/feedback")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)



def test_student_assignment_history_endpoint_returns_assignment_and_attempts(
    client, student, monkeypatch
):
    recipient_id = uuid4()
    assignment_id = uuid4()
    submission_id = uuid4()
    feedback_id = uuid4()
    teacher_id = uuid4()
    now = datetime.now(timezone.utc)
    assignment = SimpleNamespace(
        id=assignment_id,
        title="Water cycle",
        instructions="Explain evaporation and condensation.",
        status=SimpleNamespace(value="cancelled"),
        due_at=now,
        timezone="Asia/Kolkata",
    )
    recipient = SimpleNamespace(
        id=recipient_id,
        status=RecipientStatus.NEEDS_REVISION,
        blocked_reason="Add more detail.",
    )
    submission = SimpleNamespace(
        id=submission_id,
        created_at=now,
        text_content="Water evaporates.",
        file_name=None,
        mime_type=None,
        file_size_bytes=None,
    )
    feedback = SimpleNamespace(
        id=feedback_id,
        author_id=teacher_id,
        feedback_text="Please explain condensation.",
        created_at=now,
    )
    teacher = SimpleNamespace(id=teacher_id, full_name="Teacher One")

    async def fake_history(db, *, recipient_id, actor_user_id):
        assert actor_user_id == student.id
        return assignment, recipient, [(submission, [(feedback, teacher)])]

    monkeypatch.setattr(
        "app.api.submissions.get_student_assignment_history",
        fake_history,
    )
    response = client.get(
        f"/api/v1/submissions/recipients/{recipient_id}/history"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assignment_status"] == "cancelled"
    assert body["assignment_title"] == "Water cycle"
    assert body["recipient_status"] == "needs_revision"
    assert body["attempts"][0]["submission_id"] == str(submission_id)
    assert body["attempts"][0]["feedback"][0]["author_name"] == "Teacher One"
    assert body["attempts"][0]["feedback"][0]["feedback_text"] == (
        "Please explain condensation."
    )
