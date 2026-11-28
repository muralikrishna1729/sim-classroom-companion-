"""Database-backed tests for student resubmission after teacher revision requests."""
import asyncio
from uuid import uuid4

from sqlalchemy import select
import pytest
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
    RecipientStatus,
    School,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation
from app.domains.reviews import list_classroom_submissions, review_submission
from app.domains.submissions import create_submission


def test_student_can_resubmit_after_revision_and_history_is_preserved():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            school = School(name=f"Resubmission School {uuid4()}", timezone="Asia/Kolkata")
            teacher = User(
                full_name="Revision Teacher",
                email=f"teacher-{uuid4()}@test.local",
                password_hash="test",
            )
            student = User(
                full_name="Revision Student",
                email=f"student-{uuid4()}@test.local",
                password_hash="test",
            )
            session.add_all([school, teacher, student])
            await session.flush()

            classroom = Classroom(school_id=school.id, name="Revision Class")
            session.add(classroom)
            await session.flush()
            session.add(
                ClassMembership(
                    classroom_id=classroom.id,
                    user_id=teacher.id,
                    role=ClassRole.TEACHER,
                    status=MembershipStatus.ACTIVE,
                )
            )

            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="Revision Assignment",
                instructions="Explain the water cycle.",
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

            first_submission = await create_submission(
                session,
                recipient_id=recipient.id,
                actor_user_id=student.id,
                text_content="Water evaporates and forms clouds.",
            )
            await session.commit()

            _, first_feedback, reviewed_recipient = await review_submission(
                session,
                submission_id=first_submission.id,
                actor_user_id=teacher.id,
                feedback_text="Please explain condensation in more detail.",
                decision=RecipientStatus.NEEDS_REVISION,
            )
            await session.commit()
            assert reviewed_recipient.status == RecipientStatus.NEEDS_REVISION

            # The student can submit a new attempt against the same recipient.
            second_submission = await create_submission(
                session,
                recipient_id=recipient.id,
                actor_user_id=student.id,
                text_content=(
                    "Water evaporates, cools and condenses into clouds, "
                    "then falls as precipitation."
                ),
            )
            await session.commit()
            await session.refresh(recipient)

            assert second_submission.id != first_submission.id
            assert second_submission.text_content.startswith("Water evaporates, cools")
            assert recipient.status == RecipientStatus.SUBMITTED
            assert recipient.submitted_at is not None

            # Both attempts and the original feedback remain available.
            saved_submissions = list(
                (
                    await session.scalars(
                        select(Submission)
                        .where(Submission.assignment_recipient_id == recipient.id)
                        .order_by(Submission.created_at, Submission.id)
                    )
                ).all()
            )
            assert len(saved_submissions) == 2
            assert {item.id for item in saved_submissions} == {
                first_submission.id,
                second_submission.id,
            }

            saved_feedback = await session.scalar(
                select(Feedback).where(Feedback.id == first_feedback.id)
            )
            assert saved_feedback is not None
            assert saved_feedback.submission_id == first_submission.id
            assert saved_feedback.feedback_text == (
                "Please explain condensation in more detail."
            )

            # Teachers see every attempt, with a clear latest-attempt marker.
            teacher_rows = await list_classroom_submissions(
                session,
                classroom_id=classroom.id,
                actor_user_id=teacher.id,
            )
            assert len(teacher_rows) == 2
            latest_row = next(row for row in teacher_rows if row[0].id == second_submission.id)
            previous_row = next(row for row in teacher_rows if row[0].id == first_submission.id)
            assert latest_row[5:] == (2, 2)
            assert previous_row[5:] == (1, 2)

            # An older attempt cannot accidentally be reviewed after resubmission.
            with pytest.raises(
                DomainRuleViolation,
                match="Only the latest submission attempt can be reviewed",
            ):
                await review_submission(
                    session,
                    submission_id=first_submission.id,
                    actor_user_id=teacher.id,
                    feedback_text="Reviewing the wrong attempt.",
                    decision=RecipientStatus.COMPLETED,
                )
            await session.rollback()

        await engine.dispose()

    asyncio.run(scenario())


def test_student_cannot_resubmit_before_teacher_requests_revision():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            school = School(name=f"No Revision School {uuid4()}", timezone="Asia/Kolkata")
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
            session.add(classroom)
            await session.flush()
            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="Assignment",
                instructions="Complete the work.",
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
            session.add(
                Submission(
                    assignment_recipient_id=recipient.id,
                    submitted_by_id=student.id,
                    text_content="First attempt.",
                )
            )
            await session.commit()

            recipient_id = recipient.id
            with pytest.raises(ValueError, match="not currently accepting"):
                await create_submission(
                    session,
                    recipient_id=recipient_id,
                    actor_user_id=student.id,
                    text_content="Premature second attempt.",
                )
            await session.rollback()

            saved = list((await session.scalars(select(Submission))).all())
            assert len(saved) == 1
            current_recipient = await session.get(AssignmentRecipient, recipient_id)
            assert current_recipient.status == RecipientStatus.SUBMITTED

        await engine.dispose()

    asyncio.run(scenario())
