"""Database-backed tests for the assignment reminder worker."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Assignment, AssignmentRecipient, AssignmentStatus, AssignmentTargetType,
    ClassMembership, ClassRole, Classroom, MembershipStatus, RecipientStatus,
    Reminder, ReminderStatus, School, TelegramIdentity, User,
)
from app.workers import reminders as reminder_worker


def run_test(scenario):
    async def wrapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await scenario(sessions)
        finally:
            await engine.dispose()
    asyncio.run(wrapped())


async def seed_due_reminder(session, *, linked=True):
    school = School(name=f"Reminder School {uuid4()}", timezone="Asia/Kolkata")
    teacher = User(full_name="Teacher", email=f"teacher-{uuid4()}@test.local", password_hash="test")
    student = User(full_name="Student One", email=f"student-{uuid4()}@test.local", password_hash="test")
    session.add_all([school, teacher, student])
    await session.flush()
    classroom = Classroom(school_id=school.id, name=f"Class {uuid4()}")
    session.add(classroom)
    await session.flush()
    session.add_all([
        ClassMembership(classroom_id=classroom.id, user_id=teacher.id, role=ClassRole.TEACHER, status=MembershipStatus.ACTIVE),
        ClassMembership(classroom_id=classroom.id, user_id=student.id, role=ClassRole.STUDENT, status=MembershipStatus.ACTIVE),
    ])
    assignment = Assignment(
        classroom_id=classroom.id, created_by_id=teacher.id, title="Math worksheet",
        instructions="Complete questions 1-10.", target_type=AssignmentTargetType.CLASS,
        status=AssignmentStatus.ASSIGNED,
        due_at=datetime.now(timezone.utc) + timedelta(days=1), timezone="Asia/Kolkata",
    )
    session.add(assignment)
    await session.flush()
    recipient = AssignmentRecipient(
        assignment_id=assignment.id, student_id=student.id, status=RecipientStatus.PENDING,
    )
    session.add(recipient)
    await session.flush()
    reminder = Reminder(
        assignment_recipient_id=recipient.id,
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        status=ReminderStatus.PENDING, idempotency_key=f"test:{uuid4()}",
    )
    session.add(reminder)
    if linked:
        session.add(TelegramIdentity(
            user_id=student.id, telegram_user_id=123456789, telegram_username="student_test",
        ))
    await session.commit()
    return reminder.id


def test_worker_sends_due_reminder_and_marks_it_sent(monkeypatch):
    async def scenario(sessions):
        async with sessions() as session:
            reminder_id = await seed_due_reminder(session)
        sent = []
        async def fake_send(token, chat_id, message):
            sent.append((token, chat_id, message))
        monkeypatch.setattr(reminder_worker, "send_telegram_message", fake_send)
        counts = await reminder_worker.process_due_reminders(sessions, bot_token="test-token")
        async with sessions() as session:
            reminder = await session.get(Reminder, reminder_id)
        assert counts == {"claimed": 1, "sent": 1, "retrying": 0, "failed": 0, "cancelled": 0}
        assert reminder.status == ReminderStatus.SENT
        assert reminder.attempt_count == 1
        assert len(sent) == 1
        assert sent[0][0:2] == ("test-token", 123456789)
        assert "Math worksheet" in sent[0][2]
    run_test(scenario)


def test_worker_marks_unlinked_student_reminder_failed(monkeypatch):
    async def scenario(sessions):
        async with sessions() as session:
            reminder_id = await seed_due_reminder(session, linked=False)
        async def unexpected_send(*args, **kwargs):
            raise AssertionError("Telegram must not be called for an unlinked student")
        monkeypatch.setattr(reminder_worker, "send_telegram_message", unexpected_send)
        counts = await reminder_worker.process_due_reminders(sessions, bot_token="test-token")
        async with sessions() as session:
            reminder = await session.get(Reminder, reminder_id)
        assert counts["failed"] == 1
        assert reminder.status == ReminderStatus.FAILED
        assert "no linked Telegram account" in reminder.last_error


def test_worker_retries_transient_telegram_failures_and_stops_after_three_attempts(monkeypatch):
    async def scenario(sessions):
        async with sessions() as session:
            reminder_id = await seed_due_reminder(session)
        attempts = 0
        async def failed_send(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise httpx.ConnectError("Telegram temporarily unavailable")
        monkeypatch.setattr(reminder_worker, "send_telegram_message", failed_send)
        first_now = datetime.now(timezone.utc)
        first = await reminder_worker.process_due_reminders(sessions, bot_token="test-token", now=first_now)
        second = await reminder_worker.process_due_reminders(sessions, bot_token="test-token", now=first_now + timedelta(minutes=6))
        third = await reminder_worker.process_due_reminders(sessions, bot_token="test-token", now=first_now + timedelta(minutes=12))
        async with sessions() as session:
            reminder = await session.get(Reminder, reminder_id)
        assert first["retrying"] == 1
        assert second["retrying"] == 1
        assert third["failed"] == 1
        assert attempts == 3
        assert reminder.attempt_count == 3
        assert reminder.status == ReminderStatus.FAILED
    run_test(scenario)


def test_worker_cancels_reminder_when_assignment_is_cancelled(monkeypatch):
    async def scenario(sessions):
        async with sessions() as session:
            reminder_id = await seed_due_reminder(session)
            reminder = await session.get(Reminder, reminder_id)
            from app.db.models import Assignment
            recipient = await session.get(AssignmentRecipient, reminder.assignment_recipient_id)
            assignment = await session.get(Assignment, recipient.assignment_id)
            assignment.status = AssignmentStatus.CANCELLED
            await session.commit()

        async def unexpected_send(*args, **kwargs):
            raise AssertionError("Cancelled assignments must not send Telegram reminders")

        monkeypatch.setattr(reminder_worker, "send_telegram_message", unexpected_send)
        counts = await reminder_worker.process_due_reminders(sessions, bot_token="test-token")
        async with sessions() as session:
            reminder = await session.get(Reminder, reminder_id)
        assert counts["cancelled"] == 1
        assert reminder.status == ReminderStatus.CANCELLED

    run_test(scenario)
