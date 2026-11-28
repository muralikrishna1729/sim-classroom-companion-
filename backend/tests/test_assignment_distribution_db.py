"""Database-backed tests for teacher assignment targeting and distribution."""
import asyncio
from datetime import datetime, timedelta, timezone
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
    MembershipStatus,
    Notification,
    RecipientStatus,
    Reminder,
    ReminderStatus,
    School,
    StudentGroup,
    StudentGroupMembership,
    User,
)
from app.domains.submissions import create_submission
from app.domains.assignments import (
    DomainRuleViolation,
    create_assignment,
    get_teacher_assignment_progress,
    cancel_assignment,
    list_user_assignments,
    transition_recipient_status,
)


async def seed_classroom(session):
    school = School(name=f"Distribution School {uuid4()}", timezone="Asia/Kolkata")
    teacher = User(
        full_name="Class Teacher",
        email=f"teacher-{uuid4()}@test.local",
        password_hash="test",
    )
    students = [
        User(
            full_name=f"Student {index}",
            email=f"student-{index}-{uuid4()}@test.local",
            password_hash="test",
        )
        for index in range(1, 5)
    ]
    session.add_all([school, teacher, *students])
    await session.flush()

    classroom = Classroom(school_id=school.id, name=f"Class {uuid4()}")
    other_classroom = Classroom(school_id=school.id, name=f"Other {uuid4()}")
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
    for student in students[:3]:
        session.add(
            ClassMembership(
                classroom_id=classroom.id,
                user_id=student.id,
                role=ClassRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
    session.add(
        ClassMembership(
            classroom_id=classroom.id,
            user_id=students[3].id,
            role=ClassRole.STUDENT,
            status=MembershipStatus.INACTIVE,
        )
    )
    await session.flush()
    return school, teacher, students, classroom, other_classroom


def run_test(scenario):
    async def wrapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            await scenario(session)
        await engine.dispose()

    asyncio.run(wrapped())


def test_class_assignment_creates_recipient_for_each_active_student():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Class task",
            instructions="Complete the worksheet.",
            target_type=AssignmentTargetType.CLASS,
            timezone_name="Asia/Kolkata",
        )
        recipients = list(
            (
                await session.scalars(
                    select(AssignmentRecipient).where(
                        AssignmentRecipient.assignment_id == assignment.id
                    )
                )
            ).all()
        )
        assert assignment.status.value == "assigned"
        assert {row.student_id for row in recipients} == {
            student.id for student in students[:3]
        }
        assert len(recipients) == 3
        assert all(row.status == RecipientStatus.PENDING for row in recipients)
        notifications = list((await session.scalars(
            select(Notification).where(Notification.entity_id == assignment.id)
        )).all())
        assert {item.user_id for item in notifications} == {student.id for student in students[:3]}
        assert all(item.notification_type == "assignment_assigned" for item in notifications)
        assert all(item.entity_type == "assignment" for item in notifications)

    run_test(scenario)



def test_assignment_with_due_date_schedules_one_24_hour_reminder_per_recipient():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        due_at = datetime.now(timezone.utc) + timedelta(days=3)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Reminder task",
            instructions="Submit before the deadline.",
            target_type=AssignmentTargetType.CLASS,
            timezone_name="Asia/Kolkata",
            due_at=due_at,
        )
        reminders = list((await session.scalars(
            select(Reminder)
            .join(AssignmentRecipient)
            .where(AssignmentRecipient.assignment_id == assignment.id)
        )).all())
        assert len(reminders) == 3
        assert {item.status for item in reminders} == {ReminderStatus.PENDING}
        assert all(
            abs((item.scheduled_at - (due_at - timedelta(hours=24))).total_seconds()) < 1
            for item in reminders
        )
        assert len({item.idempotency_key for item in reminders}) == 3
        assert all(item.idempotency_key.endswith(":due-24h") for item in reminders)

    run_test(scenario)

def test_individual_assignment_targets_only_selected_active_students():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Individual task",
            instructions="Prepare your own summary.",
            target_type=AssignmentTargetType.INDIVIDUAL,
            timezone_name="Asia/Kolkata",
            student_ids=[students[0].id, students[2].id],
        )
        recipients = list(
            (
                await session.scalars(
                    select(AssignmentRecipient).where(
                        AssignmentRecipient.assignment_id == assignment.id
                    )
                )
            ).all()
        )
        assert {row.student_id for row in recipients} == {
            students[0].id,
            students[2].id,
        }
        assert len(recipients) == 2


    run_test(scenario)


def test_group_assignment_targets_distinct_active_group_members():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        group_a = StudentGroup(classroom_id=classroom.id, name="Group A")
        group_b = StudentGroup(classroom_id=classroom.id, name="Group B")
        session.add_all([group_a, group_b])
        await session.flush()
        session.add_all(
            [
                StudentGroupMembership(group_id=group_a.id, student_id=students[0].id),
                StudentGroupMembership(group_id=group_a.id, student_id=students[1].id),
                StudentGroupMembership(group_id=group_b.id, student_id=students[1].id),
                StudentGroupMembership(group_id=group_b.id, student_id=students[2].id),
                # Inactive classroom members must not receive an assignment.
                StudentGroupMembership(group_id=group_b.id, student_id=students[3].id),
            ]
        )
        await session.flush()

        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Group task",
            instructions="Work together on the project.",
            target_type=AssignmentTargetType.GROUP,
            timezone_name="Asia/Kolkata",
            group_ids=[group_a.id, group_b.id],
        )
        recipients = list(
            (
                await session.scalars(
                    select(AssignmentRecipient).where(
                        AssignmentRecipient.assignment_id == assignment.id
                    )
                )
            ).all()
        )
        assert {row.student_id for row in recipients} == {
            students[0].id,
            students[1].id,
            students[2].id,
        }
        assert len(recipients) == 3
        assert all(row.source_group_id in {group_a.id, group_b.id} for row in recipients)


    run_test(scenario)


def test_individual_assignment_rejects_student_outside_class_and_creates_nothing():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        with pytest.raises(DomainRuleViolation, match="Every selected student"):
            await create_assignment(
                session,
                actor_user_id=teacher.id,
                classroom_id=classroom.id,
                title="Invalid individual task",
                instructions="This should not be assigned.",
                target_type=AssignmentTargetType.INDIVIDUAL,
                timezone_name="Asia/Kolkata",
                student_ids=[students[3].id],
            )
        await session.rollback()
        assert await session.scalar(select(Assignment.id)) is None
        assert await session.scalar(select(AssignmentRecipient.id)) is None


    run_test(scenario)


def test_teacher_cannot_assign_to_classroom_without_active_teacher_membership():
    async def scenario(session):
        _, teacher, _, _, other_classroom = await seed_classroom(session)
        with pytest.raises(DomainRuleViolation, match="active teacher membership"):
            await create_assignment(
                session,
                actor_user_id=teacher.id,
                classroom_id=other_classroom.id,
                title="Unauthorized task",
                instructions="This must not be created.",
                target_type=AssignmentTargetType.CLASS,
                timezone_name="Asia/Kolkata",
            )
        await session.rollback()
        assert await session.scalar(select(Assignment.id)) is None


    run_test(scenario)


def test_group_assignment_rejects_group_from_another_classroom():
    async def scenario(session):
        _, teacher, _, classroom, other_classroom = await seed_classroom(session)
        foreign_group = StudentGroup(
            classroom_id=other_classroom.id,
            name="Foreign group",
        )
        session.add(foreign_group)
        await session.flush()

        with pytest.raises(DomainRuleViolation, match="Every selected group"):
            await create_assignment(
                session,
                actor_user_id=teacher.id,
                classroom_id=classroom.id,
                title="Invalid group task",
                instructions="This should not be assigned.",
                target_type=AssignmentTargetType.GROUP,
                timezone_name="Asia/Kolkata",
                group_ids=[foreign_group.id],
            )
        await session.rollback()
        assert await session.scalar(select(Assignment.id)) is None
        assert await session.scalar(select(AssignmentRecipient.id)) is None

    run_test(scenario)


def test_assignment_rejects_timezone_that_does_not_match_school():
    async def scenario(session):
        _, teacher, _, classroom, _ = await seed_classroom(session)
        with pytest.raises(DomainRuleViolation, match="must match the school timezone"):
            await create_assignment(
                session,
                actor_user_id=teacher.id,
                classroom_id=classroom.id,
                title="Wrong timezone task",
                instructions="Use the school's timezone.",
                target_type=AssignmentTargetType.CLASS,
                timezone_name="UTC",
            )
        await session.rollback()
        assert await session.scalar(select(Assignment.id)) is None

    run_test(scenario)



def test_teacher_can_view_recipient_wise_assignment_progress():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Progress task",
            instructions="Complete the task.",
            target_type=AssignmentTargetType.CLASS,
            timezone_name="Asia/Kolkata",
        )
        assignment, recipients, names = await get_teacher_assignment_progress(
            session, assignment_id=assignment.id, actor_user_id=teacher.id
        )
        assert assignment.id
        assert len(recipients) == 3
        assert {row.student_id for row in recipients} == {row.id for row in students[:3]}
        assert {names[row.id] for row in recipients} == {row.full_name for row in students[:3]}

    run_test(scenario)


def test_non_teacher_cannot_view_assignment_progress():
    async def scenario(session):
        _, _, students, classroom, _ = await seed_classroom(session)
        # Create an assignment using a valid teacher, then attempt access as a student.
        teacher_id = await session.scalar(
            select(ClassMembership.user_id).where(
                ClassMembership.classroom_id == classroom.id,
                ClassMembership.role == ClassRole.TEACHER,
            )
        )
        assignment = await create_assignment(
            session,
            actor_user_id=teacher_id,
            classroom_id=classroom.id,
            title="Private progress",
            instructions="Teacher-only progress.",
            target_type=AssignmentTargetType.CLASS,
            timezone_name="Asia/Kolkata",
        )
        with pytest.raises(DomainRuleViolation, match="active teacher membership"):
            await get_teacher_assignment_progress(
                session, assignment_id=assignment.id, actor_user_id=students[0].id
            )

    run_test(scenario)


def test_cancelling_assignment_preserves_recipient_history_and_blocks_repeat_cancel():
    async def scenario(session):
        _, teacher, _, classroom, _ = await seed_classroom(session)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Cancel safely",
            instructions="History must remain.",
            target_type=AssignmentTargetType.CLASS,
            timezone_name="Asia/Kolkata",
        )
        before = list(
            (await session.scalars(
                select(AssignmentRecipient).where(
                    AssignmentRecipient.assignment_id == assignment.id
                )
            )).all()
        )
        cancelled = await cancel_assignment(
            session, assignment_id=assignment.id, actor_user_id=teacher.id
        )
        after = list(
            (await session.scalars(
                select(AssignmentRecipient).where(
                    AssignmentRecipient.assignment_id == assignment.id
                )
            )).all()
        )
        assert cancelled.status == AssignmentStatus.CANCELLED
        assert {row.id for row in after} == {row.id for row in before}
        with pytest.raises(DomainRuleViolation, match="not currently assigned"):
            await cancel_assignment(
                session, assignment_id=assignment.id, actor_user_id=teacher.id
            )

    run_test(scenario)



def test_cancelled_assignment_remains_visible_but_rejects_student_writes():
    async def scenario(session):
        _, teacher, students, classroom, _ = await seed_classroom(session)
        assignment = await create_assignment(
            session,
            actor_user_id=teacher.id,
            classroom_id=classroom.id,
            title="Cancelled task",
            instructions="This task will be cancelled.",
            target_type=AssignmentTargetType.INDIVIDUAL,
            timezone_name="Asia/Kolkata",
            student_ids=[students[0].id],
        )
        recipient = await session.scalar(
            select(AssignmentRecipient).where(
                AssignmentRecipient.assignment_id == assignment.id
            )
        )
        recipient_id = recipient.id
        assignment_id = assignment.id
        student_id = students[0].id
        classroom_id = classroom.id
        await cancel_assignment(
            session, assignment_id=assignment_id, actor_user_id=teacher.id
        )
        await session.commit()
        visible = await list_user_assignments(
            session, user_id=student_id, classroom_id=classroom_id
        )
        assert len(visible) == 1
        assert visible[0][0].status == AssignmentStatus.CANCELLED
        assert visible[0][1].id == recipient_id

        with pytest.raises(DomainRuleViolation, match="recipient does not exist"):
            await transition_recipient_status(
                session,
                recipient_id=recipient_id,
                actor_user_id=student_id,
                new_status=RecipientStatus.IN_PROGRESS,
            )
        await session.rollback()

        with pytest.raises(DomainRuleViolation, match="recipient does not exist"):
            await create_submission(
                session,
                recipient_id=recipient_id,
                actor_user_id=student_id,
                text_content="This must not be accepted.",
            )
        await session.rollback()

    run_test(scenario)
