"""Authenticated assignment creation and student progress endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssignmentRecipient, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.assignments import (
    DomainRuleViolation,
    create_assignment,
    transition_recipient_status,
)
from app.schemas.assignment import (
    AssignmentCreateRequest,
    AssignmentResponse,
    RecipientProgressRequest,
    RecipientProgressResponse,
)

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment_endpoint(
    request: AssignmentCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Create an assignment and resolve its student recipients atomically."""
    try:
        assignment = await create_assignment(
            db,
            actor_user_id=current_user.id,
            classroom_id=request.classroom_id,
            title=request.title,
            instructions=request.instructions,
            target_type=request.target_type,
            timezone_name=request.timezone,
            due_at=request.due_at,
            student_ids=request.student_ids,
            group_ids=request.group_ids,
        )
        recipient_result = await db.execute(
            select(AssignmentRecipient.id).where(
                AssignmentRecipient.assignment_id == assignment.id
            )
        )
        recipient_ids = list(recipient_result.scalars().all())
        await db.commit()
        await db.refresh(assignment)
    except DomainRuleViolation as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The assignment could not be created because of a data conflict.",
        ) from None

    return AssignmentResponse(
        id=assignment.id,
        classroom_id=assignment.classroom_id,
        created_by_id=assignment.created_by_id,
        title=assignment.title,
        instructions=assignment.instructions,
        target_type=assignment.target_type,
        status=assignment.status.value,
        due_at=assignment.due_at,
        timezone=assignment.timezone,
        recipient_ids=recipient_ids,
    )


@router.patch(
    "/recipients/{recipient_id}/progress",
    response_model=RecipientProgressResponse,
)
async def update_assignment_progress(
    recipient_id: UUID,
    request: RecipientProgressRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecipientProgressResponse:
    """Allow a student to update only their own assignment progress."""
    try:
        recipient = await transition_recipient_status(
            db,
            recipient_id=recipient_id,
            actor_user_id=current_user.id,
            new_status=request.status,
            blocked_reason=request.blocked_reason,
        )
        await db.commit()
        await db.refresh(recipient)
    except DomainRuleViolation as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The progress update could not be saved.",
        ) from None

    return RecipientProgressResponse(
        id=recipient.id,
        assignment_id=recipient.assignment_id,
        student_id=recipient.student_id,
        status=recipient.status,
        blocked_reason=recipient.blocked_reason,
    )
