
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Assignment,
    AssignmentRecipient,
    AssignmentStatus,
    AssignmentTargetType,
    Classroom,
    RecipientStatus,
    School,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation
from app.domains.submissions import create_submission
from backend.tests.test_submission_api import student


def test_submission_creates_database_record_and_updates_recipient():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            school = School(name="Demo School", timezone="Asia/Kolkata")
            student = User(
                full_name="Student",
                email="student@test.local",
                password_hash="test",
            )
            teacher = User(
                full_name="Teacher",
                email="teacher@test.local",
                password_hash="test",
            )

            session.add_all([school, student, teacher])
            await session.flush()

            classroom = Classroom(
                school_id=school.id,
                name="Class A",
            )
            session.add(classroom)
            await session.flush()

            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="Math Assignment",
                instructions="Complete the questions.",
                target_type=AssignmentTargetType.CLASS,
                status=AssignmentStatus.ASSIGNED,
                timezone="Asia/Kolkata",
            )
            session.add(assignment)
            await session.flush()

            recipient = AssignmentRecipient(
                assignment_id=assignment.id,
                student_id=student.id,
                status=RecipientStatus.IN_PROGRESS,
            )
            session.add(recipient)
            await session.commit()

            submission = await create_submission(
                session,
                recipient_id=recipient.id,
                actor_user_id=student.id,
                text_content="My completed assignment.",
            )

            await session.commit()

            await session.refresh(recipient)

            assert submission.id is not None
            assert submission.assignment_recipient_id == recipient.id
            assert submission.submitted_by_id == student.id
            assert submission.text_content == "My completed assignment."

            assert recipient.status == RecipientStatus.SUBMITTED
            assert recipient.submitted_at is not None
            assert recipient.blocked_reason is None

            saved = await session.scalar(
                select(Submission).where(Submission.id == submission.id)
            )
            assert saved is not None

        await engine.dispose()

    asyncio.run(scenario())


def test_another_student_cannot_submit_assignment():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            school = School(name="Demo School", timezone="Asia/Kolkata")
            student = User(
                full_name="Assigned Student",
                email="assigned@test.local",
                password_hash="test",
            )
            other_student = User(
                full_name="Other Student",
                email="other@test.local",
                password_hash="test",
            )
            teacher = User(
                full_name="Teacher",
                email="teacher@test.local",
                password_hash="test",
            )

            session.add_all([school, student, other_student, teacher])
            await session.flush()

            classroom = Classroom(
                school_id=school.id,
                name="Class A",
            )
            session.add(classroom)
            await session.flush()

            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="Math Assignment",
                instructions="Complete the questions.",
                target_type=AssignmentTargetType.CLASS,
                status=AssignmentStatus.ASSIGNED,
                timezone="Asia/Kolkata",
            )
            session.add(assignment)
            await session.flush()

            recipient = AssignmentRecipient(
                assignment_id=assignment.id,
                student_id=student.id,
                status=RecipientStatus.IN_PROGRESS,
            )
            session.add(recipient)
            await session.commit()

            recipient_id = recipient.id
            student_id = student.id
            other_student_id = other_student.id

            with pytest.raises(DomainRuleViolation):
                await create_submission(
                    session,
                    recipient_id=recipient_id,
                    actor_user_id=other_student_id,
                    text_content="Unauthorized submission",
                )

            await session.rollback()

            current_recipient = await session.scalar(
                select(AssignmentRecipient).where(
                    AssignmentRecipient.id == recipient_id
                )
            )
            assert current_recipient is not None
            assert current_recipient.student_id == student_id
            assert current_recipient.status == RecipientStatus.IN_PROGRESS

            saved = await session.scalar(select(Submission))
            assert saved is None

        await engine.dispose()

    asyncio.run(scenario())
