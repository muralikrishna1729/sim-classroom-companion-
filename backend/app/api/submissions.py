from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.assignments import DomainRuleViolation
from app.domains.submissions import (\n    create_submission,\n    get_student_submission_feedback,\n    get_student_assignment_history,\n)
from app.schemas.assignment import SubmissionResponse
from app.schemas.review import (\n    StudentFeedbackItem,\n    StudentSubmissionFeedbackResponse,\n    StudentAssignmentHistoryResponse,\n    StudentAssignmentHistoryAttempt,\n    StudentAssignmentHistoryFeedback,\n)
from app.storage.local import save_submission_file, delete_submission_file

router = APIRouter(prefix="/assignments", tags=["Submissions"])
feedback_router = APIRouter(prefix="/submissions", tags=["Student Feedback"])


@router.post(
    "/recipients/{recipient_id}/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_assignment(
    recipient_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    text_content: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> SubmissionResponse:
    """Submit text, a file, or both for the authenticated student's assignment."""

    stored_file = None
    committed = False

    try:
        if file is not None:
            stored_file = await save_submission_file(file)

        submission = await create_submission(
            db,
            recipient_id=recipient_id,
            actor_user_id=current_user.id,
            text_content=text_content,
            file_path=stored_file.storage_key if stored_file else None,
            file_name=stored_file.file_name if stored_file else None,
            mime_type=stored_file.mime_type if stored_file else None,
            file_size_bytes=stored_file.file_size_bytes if stored_file else None,
        )

        await db.commit()
        committed = True
        await db.refresh(submission)

    except DomainRuleViolation as exc:
        if committed:
            raise

        await db.rollback()
        if stored_file:
            delete_submission_file(stored_file.storage_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None
    except ValueError as exc:
        if committed:
            raise

        await db.rollback()
        if stored_file:
            delete_submission_file(stored_file.storage_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    except IntegrityError:
        if committed:
            raise

        await db.rollback()
        if stored_file:
            delete_submission_file(stored_file.storage_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The submission could not be saved.",
        ) from None

    except Exception:
        if not committed:
            await db.rollback()
            if stored_file:
                delete_submission_file(stored_file.storage_key)
        raise

    finally:
        if file is not None:
            await file.close()

    return SubmissionResponse(
        id=submission.id,
        assignment_recipient_id=submission.assignment_recipient_id,
        text_content=submission.text_content,
        file_name=submission.file_name,
        mime_type=submission.mime_type,
        file_size_bytes=submission.file_size_bytes,
    )

@feedback_router.get(
    "/{submission_id}/feedback",
    response_model=StudentSubmissionFeedbackResponse,
)
async def get_submission_feedback(
    submission_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentSubmissionFeedbackResponse:
    """Let a student view feedback on their own submission only."""
    try:
        submission, recipient, feedback_rows = await get_student_submission_feedback(
            db,
            submission_id=submission_id,
            actor_user_id=current_user.id,
        )
    except DomainRuleViolation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found.",
        ) from None

    return StudentSubmissionFeedbackResponse(
        submission_id=submission.id,
        recipient_status=recipient.status,
        feedback=[
            StudentFeedbackItem(
                feedback_id=feedback.id,
                author_id=feedback.author_id,
                author_name=author.full_name,
                feedback_text=feedback.feedback_text,
                created_at=feedback.created_at,
            )
            for feedback, author in feedback_rows
        ],
    )


@feedback_router.get(
    "/recipients/{recipient_id}/history",
    response_model=StudentAssignmentHistoryResponse,
)
async def get_assignment_history(
    recipient_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentAssignmentHistoryResponse:
    """Return assignment details and the student's complete submission/review history."""
    try:
        assignment, recipient, history = await get_student_assignment_history(
            db,
            recipient_id=recipient_id,
            actor_user_id=current_user.id,
        )
    except DomainRuleViolation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment history not found.",
        ) from None

    attempts = []
    for submission, feedback_rows in history:
        attempts.append(
            StudentAssignmentHistoryAttempt(
                submission_id=submission.id,
                submitted_at=submission.created_at,
                text_content=submission.text_content,
                file_name=submission.file_name,
                mime_type=submission.mime_type,
                file_size_bytes=submission.file_size_bytes,
                feedback=[
                    StudentAssignmentHistoryFeedback(
                        feedback_id=feedback.id,
                        author_id=feedback.author_id,
                        author_name=author.full_name,
                        feedback_text=feedback.feedback_text,
                        created_at=feedback.created_at,
                    )
                    for feedback, author in feedback_rows
                ],
            )
        )

    return StudentAssignmentHistoryResponse(
        assignment_id=assignment.id,
        assignment_title=assignment.title,
        assignment_instructions=assignment.instructions,
        assignment_status=assignment.status.value,
        due_at=assignment.due_at,
        timezone=assignment.timezone,
        recipient_id=recipient.id,
        recipient_status=recipient.status,
        blocked_reason=recipient.blocked_reason,
        attempts=attempts,
    )
