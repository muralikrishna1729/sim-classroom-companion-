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
    ClassMembership,
    ClassRole,
    Classroom,
    MembershipStatus,
    RecipientStatus,
    School,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation
from app.domains.reviews import list_classroom_submissions


def test_teacher_lists_only_submissions_in_their_classroom():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            school = School(name=f"School {uuid4()}", timezone="Asia/Kolkata")
            teacher = User(
                full_name="Teacher",
                email=f"teacher-{uuid4()}@test.local",
                password_hash="test",
            )
            student = User(
                full_name="Student A",
                email=f"student-{uuid4()}@test.local",
                password_hash="test",
            )
            session.add_all([school, teacher, student])
            await session.flush()

            classroom = Classroom(school_id=school.id, name="Class A")
            other_classroom = Classroom(school_id=school.id, name="Class B")
            session.add_all([classroom, other_classroom])
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
                text_content="My completed work",
            )
            session.add(submission)
            await session.commit()

            rows = await list_classroom_submissions(
                session,
                classroom_id=classroom.id,
                actor_user_id=teacher.id,
            )
            assert len(rows) == 1
            listed_submission, listed_recipient, listed_assignment, student_id, student_name = rows[0]
            assert listed_submission.id == submission.id
            assert listed_recipient.id == recipient.id
            assert listed_assignment.title == "Math Assignment"
            assert student_id == student.id
            assert student_name == "Student A"
            assert not hasattr(listed_submission, "storage_path")

            with pytest.raises(DomainRuleViolation, match="active teacher membership"):
                await list_classroom_submissions(
                    session,
                    classroom_id=other_classroom.id,
                    actor_user_id=teacher.id,
                )

        await engine.dispose()

    asyncio.run(scenario())
