"""Classroom and student-group domain rules."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClassMembership,
    Classroom,
    ClassRole,
    MembershipStatus,
    School,
    SchoolMembership,
    SchoolRole,
    StudentGroup,
    StudentGroupMembership,
    User,
)
from app.domains.assignments import DomainRuleViolation


class ClassroomRuleViolation(Exception):
    """Raised when a classroom operation violates access or membership rules."""


async def _require_school_coordinator(
    db: AsyncSession,
    *,
    school_id: UUID,
    actor_user_id: UUID,
) -> School:
    """Ensure the actor is an active coordinator of an active school."""

    result = await db.execute(
        select(School)
        .join(
            SchoolMembership,
            SchoolMembership.school_id == School.id,
        )
        .where(
            School.id == school_id,
            School.is_active.is_(True),
            SchoolMembership.user_id == actor_user_id,
            SchoolMembership.role == SchoolRole.COORDINATOR,
            SchoolMembership.status == MembershipStatus.ACTIVE,
        )
    )

    school = result.scalar_one_or_none()

    if school is None:
        raise ClassroomRuleViolation(
            "An active coordinator membership is required for this school."
        )

    return school


async def create_classroom(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    school_id: UUID,
    name: str,
    grade_label: str | None = None,
) -> Classroom:
    """Create a classroom within a school managed by the coordinator."""

    await _require_school_coordinator(
        db,
        school_id=school_id,
        actor_user_id=actor_user_id,
    )

    classroom = Classroom(
        school_id=school_id,
        name=name,
        grade_label=grade_label,
    )

    db.add(classroom)
    await db.flush()

    return classroom


async def add_classroom_member(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    classroom_id: UUID,
    user_id: UUID,
    role: ClassRole,
) -> ClassMembership:
    """Add or reactivate a registered user as teacher or student."""

    classroom_result = await db.execute(
        select(Classroom).where(Classroom.id == classroom_id)
    )
    classroom = classroom_result.scalar_one_or_none()

    if classroom is None:
        raise ClassroomRuleViolation("Classroom does not exist.")

    await _require_school_coordinator(
        db,
        school_id=classroom.school_id,
        actor_user_id=actor_user_id,
    )

    user_result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
        )
    )
    target_user = user_result.scalar_one_or_none()

    if target_user is None:
        raise ClassroomRuleViolation(
            "The selected user does not exist or is inactive."
        )

    membership_result = await db.execute(
        select(ClassMembership).where(
            ClassMembership.classroom_id == classroom_id,
            ClassMembership.user_id == user_id,
        )
    )
    existing = membership_result.scalar_one_or_none()

    if existing is not None:
        if existing.role != role:
            raise ClassroomRuleViolation(
                "This user already has a different role in this classroom."
            )

        if existing.status == MembershipStatus.ACTIVE:
            return existing

        existing.status = MembershipStatus.ACTIVE
        await db.flush()
        return existing

    membership = ClassMembership(
        classroom_id=classroom_id,
        user_id=user_id,
        role=role,
        status=MembershipStatus.ACTIVE,
    )

    db.add(membership)
    await db.flush()

    return membership


async def list_user_classrooms(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[Classroom]:
    """List classrooms managed by the user or joined by the user.

    Execute the two ORM queries separately. Combining ORM entity selects with
    UNION can cause SQLAlchemy to expose only the first selected column rather
    than mapped Classroom instances on some dialect/result paths.
    """

    coordinator_query = (
        select(Classroom)
        .join(
            SchoolMembership,
            SchoolMembership.school_id == Classroom.school_id,
        )
        .join(
            School,
            School.id == Classroom.school_id,
        )
        .where(
            SchoolMembership.user_id == user_id,
            SchoolMembership.role == SchoolRole.COORDINATOR,
            SchoolMembership.status == MembershipStatus.ACTIVE,
            School.is_active.is_(True),
        )
    )

    member_query = (
        select(Classroom)
        .join(
            ClassMembership,
            ClassMembership.classroom_id == Classroom.id,
        )
        .where(
            ClassMembership.user_id == user_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )

    coordinator_result = await db.execute(coordinator_query)
    member_result = await db.execute(member_query)

    # Deduplicate users who may qualify through both access paths.
    classrooms_by_id = {
        classroom.id: classroom
        for classroom in coordinator_result.scalars().all()
    }
    classrooms_by_id.update(
        {
            classroom.id: classroom
            for classroom in member_result.scalars().all()
        }
    )

    return list(classrooms_by_id.values())


async def add_student_to_group(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    group_id: UUID,
    student_id: UUID,
) -> StudentGroupMembership:
    """Add only an active student of the group's classroom to that group."""
    result = await session.execute(
        select(StudentGroup).where(StudentGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise DomainRuleViolation("Student group does not exist.")

    actor_result = await session.execute(
        select(ClassMembership.id).where(
            ClassMembership.classroom_id == group.classroom_id,
            ClassMembership.user_id == actor_user_id,
            ClassMembership.role == ClassRole.TEACHER,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if actor_result.scalar_one_or_none() is None:
        raise DomainRuleViolation("An active teacher membership is required to manage this group.")

    result = await session.execute(
        select(ClassMembership.id).where(
            ClassMembership.classroom_id == group.classroom_id,
            ClassMembership.user_id == student_id,
            ClassMembership.role == ClassRole.STUDENT,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if result.scalar_one_or_none() is None:
        raise DomainRuleViolation(
            "Only an active student in the group's classroom can join this group."
        )

    result = await session.execute(
        select(StudentGroupMembership).where(
            StudentGroupMembership.group_id == group_id,
            StudentGroupMembership.student_id == student_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    membership = StudentGroupMembership(group_id=group_id, student_id=student_id)
    session.add(membership)
    await session.flush()
    return membership
