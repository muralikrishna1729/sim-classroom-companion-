import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Assignment,
    AssignmentRecipient,
    AssignmentStatus,
    AssignmentTargetType,
    Feedback,
    RecipientStatus,
    School,
    Submission,
    User,
    Classroom,
)
from app.domains.assignments import DomainRuleViolation
from app.domains.submissions import get_student_submission_feedback


async def _seed_submission(session, *, with_feedback=True):
    school = School(name=f"School {uuid4()}", timezone="Asia/Kolkata")
    teacher = User(
        full_name="Teacher One",
        email=f"teacher-{uuid4()}@test.local",
        password_hash="test",
    )
    student = User(
        full_name="Student One",
        email=f"student-{uuid4()}@test.local",
        password_hash="test",
    )
    other_student = User(
        full_name="Student Two",
        email=f"other-{uuid4()}@test.local",
        password_hash="test",
    )
    session.add_all([school, teacher, student, other_student])
    await session.flush()

    classroom = Classroom(school_id=school.id, name="Class A")
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
        status=RecipientStatus.COMPLETED if with_feedback else RecipientStatus.SUBMITTED,
    )
    session.add(recipient)
    await session.flush()
    submission = Submission(
        assignment_recipient_id=recipient.id,
        submitted_by_id=student.id,
        text_content="My completed work",
    )
    session.add(submission)
    await session.flush()

    if with_feedback:
        session.add(
            Feedback(
                submission_id=submission.id,
                author_id=teacher.id,
                feedback_text="Good work. Your explanation is clear.",
            )
        )
        await session.flush()

    return student.id, other_student.id, submission.id, teacher.id


def test_student_can_view_feedback_on_own_submission():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            student_id, _, submission_id, teacher_id = await _seed_submission(session)
            await session.commit()

            submission, recipient, rows = await get_student_submission_feedback(
                session,
                submission_id=submission_id,
                actor_user_id=student_id,
            )
            assert submission.id == submission_id
            assert recipient.status == RecipientStatus.COMPLETED
            assert len(rows) == 1
            feedback, author = rows[0]
            assert feedback.feedback_text == "Good work. Your explanation is clear."
            assert author.id == teacher_id
            assert author.full_name == "Teacher One"

        await engine.dispose()

    asyncio.run(scenario())


def test_student_cannot_view_another_students_feedback():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            _, other_student_id, submission_id, _ = await _seed_submission(session)
            await session.commit()

            with pytest.raises(DomainRuleViolation, match="Submission not found"):
                await get_student_submission_feedback(
                    session,
                    submission_id=submission_id,
                    actor_user_id=other_student_id,
                )

        await engine.dispose()

    asyncio.run(scenario())


def test_submission_without_feedback_returns_empty_feedback_list():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            student_id, _, submission_id, _ = await _seed_submission(
                session, with_feedback=False
            )
            await session.commit()

            submission, recipient, rows = await get_student_submission_feedback(
                session,
                submission_id=submission_id,
                actor_user_id=student_id,
            )
            assert submission.id == submission_id
            assert recipient.status == RecipientStatus.SUBMITTED
            assert rows == []

        await engine.dispose()

    asyncio.run(scenario())
