"""Classroom and student-group domain rules."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ClassMembership,
    ClassRole,
    MembershipStatus,
    StudentGroup,
    StudentGroupMembership,
)
from app.domains.assignments import DomainRuleViolation


async def add_student_to_group(
    session: AsyncSession,
    *,
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
