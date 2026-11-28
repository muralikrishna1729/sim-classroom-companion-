"""Database-backed authorization tests for assignment listing."""
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
    SchoolMembership,
    SchoolRole,
    User,
)
from app.domains.assignments import list_user_assignments


@pytest.mark.parametrize("role", ["teacher", "coordinator", "student", "outsider"])
def test_assignment_listing_enforces_database_role_visibility(role):
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            school = School(name="Demo School", timezone="Asia/Kolkata", is_active=True)
            other_school = School(name="Other School", timezone="Asia/Kolkata", is_active=True)
            session.add_all([school, other_school])
            await session.flush()

            teacher = User(full_name="Teacher", email="teacher@test.local", password_hash="x")
            coordinator = User(full_name="Coordinator", email="coordinator@test.local", password_hash="x")
            student_one = User(full_name="Student One", email="one@test.local", password_hash="x")
            student_two = User(full_name="Student Two", email="two@test.local", password_hash="x")
            outsider = User(full_name="Outsider", email="outsider@test.local", password_hash="x")
            session.add_all([teacher, coordinator, student_one, student_two, outsider])
            await session.flush()

            classroom = Classroom(school_id=school.id, name="Class A")
            other_classroom = Classroom(school_id=other_school.id, name="Class B")
            session.add_all([classroom, other_classroom])
            await session.flush()

            session.add_all([
                ClassMembership(classroom_id=classroom.id, user_id=teacher.id, role=ClassRole.TEACHER, status=MembershipStatus.ACTIVE),
                ClassMembership(classroom_id=classroom.id, user_id=student_one.id, role=ClassRole.STUDENT, status=MembershipStatus.ACTIVE),
                ClassMembership(classroom_id=classroom.id, user_id=student_two.id, role=ClassRole.STUDENT, status=MembershipStatus.ACTIVE),
                SchoolMembership(school_id=school.id, user_id=coordinator.id, role=SchoolRole.COORDINATOR, status=MembershipStatus.ACTIVE),
            ])
            assignment = Assignment(
                classroom_id=classroom.id,
                created_by_id=teacher.id,
                title="Class assignment",
                instructions="Complete the task.",
                target_type=AssignmentTargetType.CLASS,
                status=AssignmentStatus.ASSIGNED,
                timezone="Asia/Kolkata",
            )
            other_assignment = Assignment(
                classroom_id=other_classroom.id,
                created_by_id=outsider.id,
                title="Other class assignment",
                instructions="Not visible here.",
                target_type=AssignmentTargetType.CLASS,
                status=AssignmentStatus.ASSIGNED,
                timezone="Asia/Kolkata",
            )
            session.add_all([assignment, other_assignment])
            await session.flush()
            session.add_all([
                AssignmentRecipient(assignment_id=assignment.id, student_id=student_one.id, status=RecipientStatus.IN_PROGRESS),
                AssignmentRecipient(assignment_id=assignment.id, student_id=student_two.id, status=RecipientStatus.BLOCKED, blocked_reason="Needs help"),
            ])
            await session.commit()

            actors = {
                "teacher": teacher,
                "coordinator": coordinator,
                "student": student_one,
                "outsider": outsider,
            }
            rows = await list_user_assignments(session, user_id=actors[role].id)
            assert [row[0].id for row in rows] == ([assignment.id] if role != "outsider" else [])

            if role == "student":
                assert rows[0][1] is not None
                assert rows[0][1].student_id == student_one.id
                assert rows[0][1].status == RecipientStatus.IN_PROGRESS
            elif role in {"teacher", "coordinator"}:
                assert rows[0][1] is None

            # A teacher scoped to Class A cannot see assignments from Class B.
            if role == "teacher":
                scoped = await list_user_assignments(
                    session, user_id=teacher.id, classroom_id=other_classroom.id
                )
                assert scoped == []

        await engine.dispose()

    asyncio.run(scenario())
