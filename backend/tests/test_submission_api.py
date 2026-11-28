
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
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
        pass

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture
def student():
    return User(
        id=uuid4(),
        full_name="Demo Student",
        email="student@example.com",
        password_hash="not-used",
        is_active=True,
    )


@pytest.fixture
def session():
    return FakeSession()


@pytest.fixture
def client(session, student):
    original_overrides = app.dependency_overrides.copy()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: student

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_submission_requires_authentication(session):
    original_overrides = app.dependency_overrides.copy()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides.pop(get_current_user, None)

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/assignments/recipients/{uuid4()}/submissions",
                data={"text_content": "My answer"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


def test_student_can_submit_text(client, student, session, monkeypatch):
    captured = {}

    async def fake_create_submission(db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            assignment_recipient_id=kwargs["recipient_id"],
            text_content=kwargs["text_content"],
            file_name=None,
            mime_type=None,
            file_size_bytes=None,
        )

    monkeypatch.setattr(
        "app.api.submissions.create_submission",
        fake_create_submission,
    )

    response = client.post(
        f"/api/v1/assignments/recipients/{uuid4()}/submissions",
        data={"text_content": "My assignment answer"},
    )

    assert response.status_code == 201
    assert response.json()["text_content"] == "My assignment answer"
    assert captured["actor_user_id"] == student.id
    assert captured["text_content"] == "My assignment answer"
    assert session.committed is True


def test_student_can_submit_file(client, session, monkeypatch):
    recipient_id = uuid4()
    stored = SimpleNamespace(
        storage_key=f"submissions/{uuid4()}/test.pdf",
        file_name="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
    )

    async def fake_save(upload):
        return stored

    async def fake_create_submission(db, **kwargs):
        assert kwargs["file_path"] == stored.storage_key
        return SimpleNamespace(
            id=uuid4(),
            assignment_recipient_id=recipient_id,
            text_content=None,
            file_name=stored.file_name,
            mime_type=stored.mime_type,
            file_size_bytes=stored.file_size_bytes,
        )

    monkeypatch.setattr("app.api.submissions.save_submission_file", fake_save)
    monkeypatch.setattr(
        "app.api.submissions.create_submission",
        fake_create_submission,
    )

    response = client.post(
        f"/api/v1/assignments/recipients/{recipient_id}/submissions",
        files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["file_name"] == "test.pdf"
    assert session.committed is True


def test_invalid_file_returns_bad_request(client, session, monkeypatch):
    async def reject_file(upload):
        raise ValueError("Unsupported file extension.")

    monkeypatch.setattr(
        "app.api.submissions.save_submission_file",
        reject_file,
    )

    response = client.post(
        f"/api/v1/assignments/recipients/{uuid4()}/submissions",
        files={"file": ("malware.exe", b"invalid", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert session.rolled_back is True


def test_domain_rule_violation_is_rejected(client, session, monkeypatch):
    async def reject_submission(db, **kwargs):
        raise DomainRuleViolation("Only the assigned student may submit.")

    monkeypatch.setattr(
        "app.api.submissions.create_submission",
        reject_submission,
    )

    response = client.post(
        f"/api/v1/assignments/recipients/{uuid4()}/submissions",
        data={"text_content": "My answer"},
    )

    assert response.status_code == 403
    assert session.rolled_back is True


def test_file_is_deleted_when_database_commit_fails(
    client, session, monkeypatch
):
    stored = SimpleNamespace(
        storage_key=f"submissions/{uuid4()}/test.pdf",
        file_name="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
    )
    deleted = []

    async def fake_save(upload):
        return stored

    async def fake_create_submission(db, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            assignment_recipient_id=kwargs["recipient_id"],
            text_content=None,
            file_name=stored.file_name,
            mime_type=stored.mime_type,
            file_size_bytes=stored.file_size_bytes,
        )

    async def failed_commit():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr("app.api.submissions.save_submission_file", fake_save)
    monkeypatch.setattr(
        "app.api.submissions.create_submission",
        fake_create_submission,
    )
    monkeypatch.setattr(
        "app.api.submissions.delete_submission_file",
        lambda key: deleted.append(key),
    )
    monkeypatch.setattr(session, "commit", failed_commit)

    response = client.post(
        f"/api/v1/assignments/recipients/{uuid4()}/submissions",
        files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 500
    assert session.rolled_back is True
    assert deleted == [stored.storage_key]


def test_file_is_preserved_when_refresh_fails_after_commit(
    client, session, monkeypatch
):
    stored = SimpleNamespace(
        storage_key=f"submissions/{uuid4()}/test.pdf",
        file_name="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
    )
    deleted = []

    async def fake_save(upload):
        return stored

    async def fake_create_submission(db, **kwargs):
        return SimpleNamespace(
            id=uuid4(),
            assignment_recipient_id=kwargs["recipient_id"],
            text_content=None,
            file_name=stored.file_name,
            mime_type=stored.mime_type,
            file_size_bytes=stored.file_size_bytes,
        )

    async def failed_refresh(instance):
        raise RuntimeError("Database refresh failed")

    monkeypatch.setattr(
        "app.api.submissions.save_submission_file",
        fake_save,
    )
    monkeypatch.setattr(
        "app.api.submissions.create_submission",
        fake_create_submission,
    )
    monkeypatch.setattr(
        "app.api.submissions.delete_submission_file",
        lambda key: deleted.append(key),
    )
    monkeypatch.setattr(session, "refresh", failed_refresh)

    response = client.post(
        f"/api/v1/assignments/recipients/{uuid4()}/submissions",
        files={"file": ("test.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 500
    assert session.committed is True
    assert session.rolled_back is False
    assert deleted == []
