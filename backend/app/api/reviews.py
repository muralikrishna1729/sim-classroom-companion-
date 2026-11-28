"""Teacher-authorized submission review endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RecipientStatus, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.assignments import DomainRuleViolation
from app.domains.reviews import review_submission
from app.schemas.review import (
    ReviewSubmissionRequest,
    ReviewSubmissionResponse,
)

router = APIRouter(prefix="/reviews", tags=["Teacher Reviews"])


@router.post(
    "/submissions/{submission_id}",
    response_model=ReviewSubmissionResponse,
)
async def review_submission_endpoint(
    submission_id: UUID,
    request: ReviewSubmissionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewSubmissionResponse:
    """Save teacher feedback and mark work completed or needing revision."""
    try:
        submission, feedback, recipient = await review_submission(
            db,
            submission_id=submission_id,
            actor_user_id=current_user.id,
            feedback_text=request.feedback_text,
            decision=RecipientStatus(request.decision),
        )
        await db.commit()
        await db.refresh(feedback)
        await db.refresh(recipient)
    except DomainRuleViolation as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The review could not be saved.",
        ) from None

    return ReviewSubmissionResponse(
        submission_id=submission.id,
        feedback_id=feedback.id,
        author_id=feedback.author_id,
        feedback_text=feedback.feedback_text,
        recipient_id=recipient.id,
        recipient_status=recipient.status,
        completed_at=recipient.completed_at,
    )
