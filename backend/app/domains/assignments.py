"""Assignment creation and per-student progress business rules.

The caller owns the SQLAlchemy transaction and must commit or roll back.
This keeps assignment and recipient writes atomic at the request/job boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    StudentGroup,
    StudentGroupMembership,
)


class DomainRuleViolation(ValueError):
    """Raised when a requested operation violates a domain invariant."""


ALLOWED_RECIPIENT_TRANSITIONS: dict[RecipientStatus, set[RecipientStatus]] = {
    RecipientStatus.PENDING: {RecipientStatus.ACKNOWLEDGED, RecipientStatus.IN_PROGRESS},
    RecipientStatus.ACKNOWLEDGED: {RecipientStatus.IN_PROGRESS},
    RecipientStatus.IN_PROGRESS: {RecipientStatus.BLOCKED, RecipientStatus.SUBMITTED},
    RecipientStatus.BLOCKED: {RecipientStatus.IN_PROGRESS, RecipientStatus.SUBMITTED},
    RecipientStatus.SUBMITTED: {RecipientStatus.NEEDS_REVISION, RecipientStatus.COMPLETED},
    RecipientStatus.NEEDS_REVISION: {RecipientStatus.IN_PROGRESS, RecipientStatus.SUBMITTED},
    RecipientStatus.COMPLETED: set(),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_assignment(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    classroom_id: UUID,
    title: str,
    instructions: str,
    target_type: AssignmentTargetType,
    timezone_name: str,
    due_at: datetime | None = None,
    student_ids: list[UUID] | None = None,
    group_ids: list[UUID] | None = None,
) -> Assignment:
    """Create an assignment and one recipient per resolved active student.

    CLASS resolves all active classroom students.
    INDIVIDUAL validates each requested student against active class membership.
    GROUP validates group ownership and resolves the distinct active members.

    Flushes but never commits. The caller owns the transaction.
    """
    clean_title = title.strip()
    clean_instructions = instructions.strip()
    clean_timezone = timezone_name.strip()
    if not clean_title or not clean_instructions or not clean_timezone:
        raise DomainRuleViolation("Title, instructions and school timezone are required.")
    try:
        ZoneInfo(clean_timezone)
    except ZoneInfoNotFoundError as exc:
        raise DomainRuleViolation("A valid IANA school timezone is required.") from exc
    if due_at is not None and (due_at.tzinfo is None or due_at.utcoffset() is None):
        raise DomainRuleViolation("due_at must be timezone-aware.")

    result = await session.execute(
        select(Classroom, School)
        .join(School, School.id == Classroom.school_id)
        .where(Classroom.id == classroom_id)
    )
    pair = result.one_or_none()
    if pair is None:
        raise DomainRuleViolation("Classroom does not exist.")
    classroom, school = pair
    if not school.is_active:
        raise DomainRuleViolation("The school is inactive.")
    if clean_timezone != school.timezone:
        raise DomainRuleViolation("Assignment timezone must match the school timezone.")

    teacher_result = await session.execute(
        select(ClassMembership.id)
        .where(
            ClassMembership.classroom_id == classroom_id,
            ClassMembership.user_id == actor_user_id,
            ClassMembership.role == ClassRole.TEACHER,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if teacher_result.scalar_one_or_none() is None:
        raise DomainRuleViolation("An active teacher membership is required.")

    resolved_student_ids: set[UUID]
    requested_group_ids: set[UUID] = set()

    if target_type == AssignmentTargetType.CLASS:
        if student_ids or group_ids:
            raise DomainRuleViolation("Class targeting cannot include student or group IDs.")
        result = await session.execute(
            select(ClassMembership.user_id).where(
                ClassMembership.classroom_id == classroom_id,
                ClassMembership.role == ClassRole.STUDENT,
                ClassMembership.status == MembershipStatus.ACTIVE,
            )
        )
        resolved_student_ids = set(result.scalars().all())

    elif target_type == AssignmentTargetType.INDIVIDUAL:
        if not student_ids or group_ids:
            raise DomainRuleViolation("Individual targeting requires student IDs only.")
        requested_ids = set(student_ids)
        if len(requested_ids) != len(student_ids):
            raise DomainRuleViolation("Duplicate student IDs were supplied.")
        result = await session.execute(
            select(ClassMembership.user_id).where(
                ClassMembership.classroom_id == classroom_id,
                ClassMembership.user_id.in_(requested_ids),
                ClassMembership.role == ClassRole.STUDENT,
                ClassMembership.status == MembershipStatus.ACTIVE,
            )
        )
        resolved_student_ids = set(result.scalars().all())
        if resolved_student_ids != requested_ids:
            raise DomainRuleViolation("Every selected student must be active in this classroom.")

    elif target_type == AssignmentTargetType.GROUP:
        if not group_ids or student_ids:
            raise DomainRuleViolation("Group targeting requires group IDs only.")
        requested_group_ids = set(group_ids)
        if len(requested_group_ids) != len(group_ids):
            raise DomainRuleViolation("Duplicate group IDs were supplied.")
        result = await session.execute(
            select(StudentGroup.id).where(
                StudentGroup.classroom_id == classroom_id,
                StudentGroup.id.in_(requested_group_ids),
            )
        )
        valid_group_ids = set(result.scalars().all())
        if valid_group_ids != requested_group_ids:
            raise DomainRuleViolation("Every selected group must belong to this classroom.")

        result = await session.execute(
            select(StudentGroupMembership.student_id)
            .join(
                ClassMembership,
                ClassMembership.user_id == StudentGroupMembership.student_id,
            )
            .where(
                StudentGroupMembership.group_id.in_(requested_group_ids),
                ClassMembership.classroom_id == classroom_id,
                ClassMembership.role == ClassRole.STUDENT,
                ClassMembership.status == MembershipStatus.ACTIVE,
            )
        )
        resolved_student_ids = set(result.scalars().all())
    else:
        raise DomainRuleViolation("Unsupported assignment target type.")

    if not resolved_student_ids:
        raise DomainRuleViolation("The assignment target has no active students.")

    assignment = Assignment(
        classroom_id=classroom_id,
        created_by_id=actor_user_id,
        title=clean_title,
        instructions=clean_instructions,
        target_type=target_type,
        status=AssignmentStatus.ASSIGNED,
        due_at=due_at.astimezone(timezone.utc) if due_at is not None else None,
        timezone=clean_timezone,
    )
    session.add(assignment)
    await session.flush()

    source_group_by_student: dict[UUID, UUID] = {}
    if target_type == AssignmentTargetType.GROUP:
        result = await session.execute(
            select(StudentGroupMembership.student_id, StudentGroupMembership.group_id)
            .where(
                StudentGroupMembership.group_id.in_(requested_group_ids),
                StudentGroupMembership.student_id.in_(resolved_student_ids),
            )
            .order_by(StudentGroupMembership.group_id)
        )
        for student_id, group_id in result.all():
            source_group_by_student.setdefault(student_id, group_id)

    session.add_all(
        [
            AssignmentRecipient(
                assignment_id=assignment.id,
                student_id=student_id,
                source_group_id=source_group_by_student.get(student_id),
                status=RecipientStatus.PENDING,
            )
            for student_id in sorted(resolved_student_ids, key=str)
        ]
    )
    await session.flush()
    return assignment


async def transition_recipient_status(
    session: AsyncSession,
    *,
    recipient_id: UUID,
    actor_user_id: UUID,
    new_status: RecipientStatus,
    blocked_reason: str | None = None,
) -> AssignmentRecipient:
    """Apply a student-owned progress transition while locking the recipient row."""
    result = await session.execute(
        select(AssignmentRecipient)
        .where(AssignmentRecipient.id == recipient_id)
        .with_for_update()
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise DomainRuleViolation("Assignment recipient does not exist.")
    if recipient.student_id != actor_user_id:
        raise DomainRuleViolation("Only the assigned student may update this progress.")

    reason = blocked_reason.strip() if blocked_reason else None
    if new_status == RecipientStatus.BLOCKED and not reason:
        raise DomainRuleViolation("A blocked status requires a reason.")
    if new_status != RecipientStatus.BLOCKED and reason:
        raise DomainRuleViolation("A blocked reason is only valid for blocked status.")
    if new_status not in ALLOWED_RECIPIENT_TRANSITIONS[recipient.status]:
        raise DomainRuleViolation(
            f"Transition from {recipient.status.value} to {new_status.value} is not allowed."
        )

    now = _utc_now()
    recipient.status = new_status
    recipient.blocked_reason = reason
    if new_status == RecipientStatus.ACKNOWLEDGED:
        recipient.acknowledged_at = now
    elif new_status == RecipientStatus.SUBMITTED:
        recipient.submitted_at = now
    elif new_status == RecipientStatus.COMPLETED:
        recipient.completed_at = now

    await session.flush()
    return recipient
