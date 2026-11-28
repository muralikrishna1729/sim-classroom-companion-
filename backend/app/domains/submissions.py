"""Student submission rules.

The caller owns the transaction. File bytes must be validated and stored by
an upload adapter before calling this service; only a storage key/path belongs
in the database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Assignment,
    AssignmentRecipient,
    AssignmentStatus,
    Feedback,
    RecipientStatus,
    Submission,
    User,
)
from app.domains.assignments import DomainRuleViolation


async def create_submission(
    session: AsyncSession,
    *,
    recipient_id: UUID,
    actor_user_id: UUID,
    text_content: str | None = None,
    file_path: str | None = None,
    file_name: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
) -> Submission:
    """Create a submission for the authenticated student's own recipient."""
    clean_text = text_content.strip() if text_content else None
    file_metadata_supplied = any(
        value is not None for value in (file_path, file_name, mime_type, file_size_bytes)
    )
    has_file = bool(file_path and file_name and mime_type and file_size_bytes is not None)

    if file_metadata_supplied and not has_file:
        raise DomainRuleViolation("File path, name, MIME type and size must be supplied together.")
    if not clean_text and not has_file:
        raise DomainRuleViolation("A submission must contain text or a complete file reference.")
    if file_size_bytes is not None and file_size_bytes <= 0:
        raise DomainRuleViolation("File size must be positive.")
    if file_name and ("/" in file_name or "\\" in file_name):
        raise DomainRuleViolation("File name must not contain path separators.")

    result = await session.execute(
        select(AssignmentRecipient)
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .where(
            AssignmentRecipient.id == recipient_id,
            Assignment.status == AssignmentStatus.ASSIGNED,
        )
        .with_for_update(of=AssignmentRecipient)
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise DomainRuleViolation("Assignment recipient does not exist.")
    if recipient.student_id != actor_user_id:
        raise DomainRuleViolation("Only the assigned student may submit this work.")
    if recipient.status not in {
        RecipientStatus.IN_PROGRESS,
        RecipientStatus.BLOCKED,
        RecipientStatus.NEEDS_REVISION,
    }:
        raise DomainRuleViolation(
            "This assignment is not currently accepting a submission or revision."
        )

    submission = Submission(
        assignment_recipient_id=recipient.id,
        submitted_by_id=actor_user_id,
        text_content=clean_text,
        file_path=file_path if has_file else None,
        file_name=file_name if has_file else None,
        mime_type=mime_type if has_file else None,
        file_size_bytes=file_size_bytes if has_file else None,
    )
    recipient.status = RecipientStatus.SUBMITTED
    recipient.submitted_at = datetime.now(timezone.utc)
    recipient.blocked_reason = None
    session.add(submission)
    await session.flush()
    return submission


async def get_student_submission_feedback(
    session: AsyncSession,
    *,
    submission_id: UUID,
    actor_user_id: UUID,
) -> tuple[Submission, AssignmentRecipient, list[tuple[Feedback, User]]]:
    """Return feedback only when the requester owns the submitted assignment.

    An empty feedback list is a valid result when the teacher has not reviewed
    the submission yet. Ownership failures intentionally share the same domain
    error as missing submissions so callers cannot enumerate other students' work.
    """
    result = await session.execute(
        select(Submission, AssignmentRecipient)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.id == Submission.assignment_recipient_id,
        )
        .where(Submission.id == submission_id)
    )
    row = result.one_or_none()
    if row is None:
        raise DomainRuleViolation("Submission not found.")

    submission, recipient = row
    if recipient.student_id != actor_user_id:
        raise DomainRuleViolation("Submission not found.")

    feedback_result = await session.execute(
        select(Feedback, User)
        .join(User, User.id == Feedback.author_id)
        .where(Feedback.submission_id == submission.id)
        .order_by(Feedback.created_at.asc(), Feedback.id)
    )
    return submission, recipient, list(feedback_result.all())
