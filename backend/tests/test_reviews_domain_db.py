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
    ClassMembership,
    ClassRole,
    Classroom,
    Feedback,
    MembershipStatus,
    Notification,
    RecipientStatus,
    School,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation
from app.domains.reviews import review_submission


async def _seed_review_case(session, *, teacher_in_class=True):
    school = School(name=f"School {uuid4()}", timezone="Asia/Kolkata")
    teacher = User(
        full_name="Teacher",
        email=f"teacher-{uuid4()}@test.local",
        password_hash="test",
    )
    student = User(
        full_name="Student",
        email=f"student-{uuid4()}@test.local",
        password_hash="test",
    )
    session.add_all([school, teacher, student])
    await session.flush()

    classroom = Classroom(school_id=school.id, name="Class A")
    other_classroom = Classroom(school_id=school.id, name="Class B")
    session.add_all([classroom, other_classroom])
    await session.flush()

    teacher_membership = ClassMembership(
        classroom_id=classroom.id if teacher_in_class else other_classroom.id,
        user_id=teacher.id,
        role=ClassRole.TEACHER,
        status=MembershipStatus.ACTIVE,
    )
    session.add(teacher_membership)

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
        status=RecipientStatus.SUBMITTED,
    )
    session.add(recipient)
    await session.flush()

    submission = Submission(
        assignment_recipient_id=recipient.id,
        submitted_by_id=student.id,
        text_content="Completed work",
    )
    session.add(submission)
    await session.flush()

    return teacher.id, recipient.id, submission.id


def test_teacher_review_saves_feedback_and_completes_submission():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            teacher_id, recipient_id, submission_id = await _seed_review_case(session)
            await session.commit()

            submission, feedback, recipient = await review_submission(
                session,
                submission_id=submission_id,
                actor_user_id=teacher_id,
                feedback_text="  Good work.  ",
                decision=RecipientStatus.COMPLETED,
            )
            await session.commit()

            assert submission.id == submission_id
            assert feedback.feedback_text == "Good work."
            assert feedback.author_id == teacher_id
            assert recipient.id == recipient_id
            assert recipient.status == RecipientStatus.COMPLETED
            assert recipient.completed_at is not None
            notification = await session.scalar(
                select(Notification).where(Notification.entity_id == submission_id)
            )
            assert notification.user_id == recipient.student_id
            assert notification.notification_type == "submission_approved"
            assert notification.entity_type == "submission"

            saved_feedback = await session.scalar(
                select(Feedback).where(Feedback.submission_id == submission_id)
            )
            assert saved_feedback is not None

        await engine.dispose()

    asyncio.run(scenario())


def test_teacher_from_another_classroom_cannot_review_submission():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            teacher_id, recipient_id, submission_id = await _seed_review_case(
                session, teacher_in_class=False
            )
            await session.commit()

            with pytest.raises(DomainRuleViolation):
                await review_submission(
                    session,
                    submission_id=submission_id,
                    actor_user_id=teacher_id,
                    feedback_text="Please revise.",
                    decision=RecipientStatus.NEEDS_REVISION,
                )
            await session.rollback()

            recipient = await session.get(AssignmentRecipient, recipient_id)
            assert recipient is not None
            assert recipient.status == RecipientStatus.SUBMITTED
            assert await session.scalar(select(Feedback)) is None

        await engine.dispose()

    asyncio.run(scenario())


def test_review_rejects_blank_feedback():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            teacher_id, _, submission_id = await _seed_review_case(session)
            await session.commit()

            with pytest.raises(DomainRuleViolation, match="Feedback cannot be empty"):
                await review_submission(
                    session,
                    submission_id=submission_id,
                    actor_user_id=teacher_id,
                    feedback_text="   ",
                    decision=RecipientStatus.COMPLETED,
                )

        await engine.dispose()

    asyncio.run(scenario())


def test_teacher_can_request_revision_with_written_feedback():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            teacher_id, recipient_id, submission_id = await _seed_review_case(session)
            await session.commit()

            _, feedback, recipient = await review_submission(
                session,
                submission_id=submission_id,
                actor_user_id=teacher_id,
                feedback_text="Please show your calculation steps.",
                decision=RecipientStatus.NEEDS_REVISION,
            )
            await session.commit()

            assert feedback.feedback_text == "Please show your calculation steps."
            assert recipient.id == recipient_id
            assert recipient.status == RecipientStatus.NEEDS_REVISION
            assert recipient.completed_at is None
            notification = await session.scalar(
                select(Notification).where(Notification.entity_id == submission_id)
            )
            assert notification.user_id == recipient.student_id
            assert notification.notification_type == "revision_requested"
            assert notification.payload["assignment_title"] == "Math Assignment"

        await engine.dispose()

    asyncio.run(scenario())
