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
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def refresh(self, instance):
        return None

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture
def teacher():
    return User(
        id=uuid4(),
        full_name="Demo Teacher",
        email="teacher-review-api@example.com",
        password_hash="not-used",
        is_active=True,
    )


@pytest.fixture
def api_client(teacher):
    original_overrides = app.dependency_overrides.copy()
    session = FakeSession()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: teacher
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client, session
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_teacher_review_endpoint_saves_feedback_and_returns_completed_status(
    api_client, teacher, monkeypatch
):
    client, session = api_client
    submission_id = uuid4()
    feedback_id = uuid4()
    recipient_id = uuid4()
    completed_at = datetime.now(timezone.utc)

    async def fake_review(
        db, *, submission_id, actor_user_id, feedback_text, decision
    ):
        assert actor_user_id == teacher.id
        assert feedback_text == "Good explanation."
        assert decision == RecipientStatus.COMPLETED
        return (
            SimpleNamespace(id=submission_id),
            SimpleNamespace(
                id=feedback_id,
                author_id=teacher.id,
                feedback_text=feedback_text,
            ),
            SimpleNamespace(
                id=recipient_id,
                status=RecipientStatus.COMPLETED,
                completed_at=completed_at,
            ),
        )

    monkeypatch.setattr("app.api.reviews.review_submission", fake_review)
    response = client.post(
        f"/api/v1/reviews/submissions/{submission_id}",
        json={
            "feedback_text": "  Good explanation.  ",
            "decision": "completed",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["submission_id"] == str(submission_id)
    assert body["feedback_id"] == str(feedback_id)
    assert body["author_id"] == str(teacher.id)
    assert body["feedback_text"] == "Good explanation."
    assert body["recipient_id"] == str(recipient_id)
    assert body["recipient_status"] == "completed"
    assert body["completed_at"] is not None
    assert session.committed is True


def test_teacher_review_endpoint_returns_forbidden_when_domain_rejects_access(
    api_client, monkeypatch
):
    client, session = api_client

    async def reject_review(db, **kwargs):
        raise DomainRuleViolation("An active teacher membership is required.")

    monkeypatch.setattr("app.api.reviews.review_submission", reject_review)
    response = client.post(
        f"/api/v1/reviews/submissions/{uuid4()}",
        json={"feedback_text": "Please revise.", "decision": "needs_revision"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "An active teacher membership is required."
    assert session.rolled_back is True
    assert session.committed is False


def test_teacher_review_endpoint_rejects_blank_feedback(api_client):
    client, session = api_client
    response = client.post(
        f"/api/v1/reviews/submissions/{uuid4()}",
        json={"feedback_text": "   ", "decision": "completed"},
    )

    assert response.status_code == 422
    assert session.committed is False


def test_teacher_review_endpoint_rejects_unsupported_decision(api_client):
    client, session = api_client
    response = client.post(
        f"/api/v1/reviews/submissions/{uuid4()}",
        json={"feedback_text": "Good work.", "decision": "approved"},
    )

    assert response.status_code == 422
    assert session.committed is False


def test_teacher_review_endpoint_requires_authentication():
    original_overrides = app.dependency_overrides.copy()

    async def override_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/reviews/submissions/{uuid4()}",
                json={"feedback_text": "Good work.", "decision": "completed"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
