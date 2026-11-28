"""Database-backed end-to-end test for the student/teacher assignment workflow."""
import asyncio
from uuid import uuid4

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
    MembershipStatus,
    RecipientStatus,
    School,
    User,
)
from app.domains.assignments import list_user_assignments
from app.domains.reviews import review_submission
from app.domains.submissions import create_submission, get_student_submission_feedback


def test_student_assignment_submission_teacher_review_and_feedback_workflow():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            school = School(
                name=f"Workflow School {uuid4()}",
                timezone="Asia/Kolkata",
                is_active=True,
            )
            teacher = User(
                full_name="Workflow Teacher",
                email=f"teacher-{uuid4()}@test.local",
                password_hash="test",
            )
            student = User(
                full_name="Workflow Student",
                email=f"student-{uuid4()}@test.local",
                password_hash="test",
            )
            session.add_all([school, teacher, student])
            await session.flush()

            classroom = Classroom(school_id=school.id, name="Workflow Class")
            session.add(classroom)
            await session.flush()

            session.add_all([
                ClassMembership(
                    classroom_id=classroom.id,
                    user_id=teacher.id,
                    role=ClassRole.TEACHER,
                    status=MembershipStatus.ACTIVE,
                ),
                ClassMembership(
                    classroom_id=classroom.id,
                    user_id=student.id,
                    role=ClassRole.STUDENT,
                    status=MembershipStatus.ACTIVE,
                ),
            ])
            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="End-to-end Science Assignment",
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

            # Student sees the assignment and only their own progress.
            visible_assignments = await list_user_assignments(
                session,
                user_id=student.id,
                classroom_id=classroom.id,
            )
            assert len(visible_assignments) == 1
            visible_assignment, visible_recipient = visible_assignments[0]
            assert visible_assignment.id == assignment.id
            assert visible_recipient.id == recipient.id
            assert visible_recipient.status == RecipientStatus.IN_PROGRESS

            # Student submits work; the recipient moves to SUBMITTED.
            submission = await create_submission(
                session,
                recipient_id=recipient.id,
                actor_user_id=student.id,
                text_content="Water evaporates, condenses into clouds, and falls as rain.",
            )
            await session.commit()
            await session.refresh(recipient)
            assert recipient.status == RecipientStatus.SUBMITTED
            assert recipient.submitted_at is not None

            # An active classroom teacher reviews the submission.
            _, feedback, reviewed_recipient = await review_submission(
                session,
                submission_id=submission.id,
                actor_user_id=teacher.id,
                feedback_text="Good explanation. Include one example of collection.",
                decision=RecipientStatus.NEEDS_REVISION,
            )
            await session.commit()
            assert feedback.author_id == teacher.id
            assert feedback.feedback_text == (
                "Good explanation. Include one example of collection."
            )
            assert reviewed_recipient.status == RecipientStatus.NEEDS_REVISION

            # Student can retrieve the teacher's feedback on their own submission.
            returned_submission, returned_recipient, feedback_rows = (
                await get_student_submission_feedback(
                    session,
                    submission_id=submission.id,
                    actor_user_id=student.id,
                )
            )
            assert returned_submission.id == submission.id
            assert returned_recipient.status == RecipientStatus.NEEDS_REVISION
            assert len(feedback_rows) == 1
            returned_feedback, author = feedback_rows[0]
            assert returned_feedback.id == feedback.id
            assert author.id == teacher.id
            assert author.full_name == "Workflow Teacher"

        await engine.dispose()

    asyncio.run(scenario())
