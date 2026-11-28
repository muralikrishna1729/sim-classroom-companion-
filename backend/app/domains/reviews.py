"""Teacher review and written feedback business rules.

The caller owns the transaction. This service flushes changes but never commits.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Assignment,
    AssignmentRecipient,
    AssignmentStatus,
    ClassMembership,
    ClassRole,
    Feedback,
    MembershipStatus,
    RecipientStatus,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation


async def review_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    actor_user_id: UUID,
    feedback_text: str,
    decision: RecipientStatus,
) -> tuple[Submission, Feedback, AssignmentRecipient]:
    """Save written feedback and apply a teacher review decision atomically."""
    clean_feedback = feedback_text.strip()
    if not clean_feedback:
        raise DomainRuleViolation("Feedback cannot be empty.")
    if len(clean_feedback) > 5000:
        raise DomainRuleViolation("Feedback cannot exceed 5000 characters.")
    if decision not in {
        RecipientStatus.COMPLETED,
        RecipientStatus.NEEDS_REVISION,
    }:
        raise DomainRuleViolation(
            "A teacher must choose completed or needs_revision."
        )

    result = await session.execute(
        select(Submission, AssignmentRecipient, Assignment)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.id == Submission.assignment_recipient_id,
        )
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .where(
            Submission.id == submission_id,
            Assignment.status == AssignmentStatus.ASSIGNED,
        )
        .with_for_update(of=AssignmentRecipient)
    )
    row = result.one_or_none()
    if row is None:
        raise DomainRuleViolation("Submission does not exist or is unavailable.")

    submission, recipient, assignment = row

    teacher_result = await session.execute(
        select(ClassMembership.id).where(
            ClassMembership.classroom_id == assignment.classroom_id,
            ClassMembership.user_id == actor_user_id,
            ClassMembership.role == ClassRole.TEACHER,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if teacher_result.scalar_one_or_none() is None:
        raise DomainRuleViolation(
            "An active teacher membership is required to review this submission."
        )

    if recipient.status != RecipientStatus.SUBMITTED:
        raise DomainRuleViolation("Only submitted assignments can be reviewed.")

    feedback = Feedback(
        submission_id=submission.id,
        author_id=actor_user_id,
        feedback_text=clean_feedback,
    )
    recipient.status = decision
    if decision == RecipientStatus.COMPLETED:
        recipient.completed_at = datetime.now(timezone.utc)

    session.add(feedback)
    await session.flush()
    return submission, feedback, recipient


async def list_classroom_submissions(
    session: AsyncSession,
    *,
    classroom_id: UUID,
    actor_user_id: UUID,
) -> list[tuple[Submission, AssignmentRecipient, Assignment, UUID, str]]:
    """List submissions in a classroom after verifying active teacher access.

    The result includes the student's ID and display name, but never exposes
    the private storage path for uploaded files. The caller owns the session.
    """
    teacher_result = await session.execute(
        select(ClassMembership.id).where(
            ClassMembership.classroom_id == classroom_id,
            ClassMembership.user_id == actor_user_id,
            ClassMembership.role == ClassRole.TEACHER,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if teacher_result.scalar_one_or_none() is None:
        raise DomainRuleViolation(
            "An active teacher membership is required to view classroom submissions."
        )

    result = await session.execute(
        select(
            Submission,
            AssignmentRecipient,
            Assignment,
            AssignmentRecipient.student_id,
            User.full_name,
        )
        .join(
            AssignmentRecipient,
            AssignmentRecipient.id == Submission.assignment_recipient_id,
        )
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(User, User.id == AssignmentRecipient.student_id)
        .where(
            Assignment.classroom_id == classroom_id,
            Assignment.status == AssignmentStatus.ASSIGNED,
        )
        .order_by(Submission.created_at.desc(), Submission.id)
    )
    return list(result.all())
