"""API tests for authenticated in-app notifications."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.main import app


class FakeSession:
    async def commit(self):
        pass

    async def refresh(self, instance):
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
        email="notification-student@example.com",
        password_hash="not-used",
        is_active=True,
    )


def authenticate_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_notification_list_requires_authentication(client):
    response = client.get("/api/v1/notifications")
    assert response.status_code == 401


def test_user_can_list_only_their_notification_feed(client, student, monkeypatch):
    authenticate_as(student)
    notification = SimpleNamespace(
        id=uuid4(),
        notification_type="assignment_assigned",
        title="New assignment",
        message="Math homework has been assigned.",
        entity_type="assignment",
        entity_id=uuid4(),
        payload={"classroom": "Grade 8"},
        read_at=None,
        created_at=datetime.now(timezone.utc),
    )

    async def list_items(db, **kwargs):
        assert kwargs == {"user_id": student.id, "limit": 10, "offset": 5}
        return [notification]

    async def unread(db, **kwargs):
        assert kwargs["user_id"] == student.id
        return 2

    monkeypatch.setattr("app.api.notifications.list_user_notifications", list_items)
    monkeypatch.setattr("app.api.notifications.count_unread_notifications", unread)

    response = client.get("/api/v1/notifications?limit=10&offset=5")

    assert response.status_code == 200
    body = response.json()
    assert body["unread_count"] == 2
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["items"][0]["id"] == str(notification.id)
    assert body["items"][0]["payload"] == {"classroom": "Grade 8"}


def test_notification_list_rejects_invalid_pagination(client, student):
    authenticate_as(student)
    assert client.get("/api/v1/notifications?limit=101").status_code == 422
    assert client.get("/api/v1/notifications?offset=-1").status_code == 422


def test_user_can_mark_own_notification_as_read(client, student, monkeypatch):
    authenticate_as(student)
    notification = SimpleNamespace(
        id=uuid4(), read_at=datetime.now(timezone.utc)
    )

    async def mark_read(db, **kwargs):
        assert kwargs == {"notification_id": notification.id, "user_id": student.id}
        return notification

    monkeypatch.setattr("app.api.notifications.mark_notification_read", mark_read)
    response = client.patch(f"/api/v1/notifications/{notification.id}/read")

    assert response.status_code == 200
    assert response.json()["id"] == str(notification.id)
    assert response.json()["read_at"] is not None


def test_user_cannot_mark_another_users_notification_as_read(client, student, monkeypatch):
    authenticate_as(student)

    async def missing(db, **kwargs):
        return None

    monkeypatch.setattr("app.api.notifications.mark_notification_read", missing)
    response = client.patch(f"/api/v1/notifications/{uuid4()}/read")

    assert response.status_code == 404


def test_user_can_mark_all_notifications_as_read(client, student, monkeypatch):
    authenticate_as(student)

    async def mark_all(db, **kwargs):
        assert kwargs["user_id"] == student.id
        return 3

    monkeypatch.setattr("app.api.notifications.mark_all_notifications_read", mark_all)
    response = client.patch("/api/v1/notifications/read-all")

    assert response.status_code == 200
    assert response.json() == {"updated_count": 3}
