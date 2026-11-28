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
    list_user_assignments,
    transition_recipient_status,
    get_teacher_assignment_progress,
    cancel_assignment,
)
from app.schemas.assignment import (
    AssignmentCreateRequest,
    AssignmentListItem,
    AssignmentResponse,
    RecipientProgressRequest,
    RecipientProgressResponse,
    TeacherAssignmentProgressResponse,
    TeacherAssignmentRecipientProgress,
    AssignmentCancellationResponse,
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


@router.get("", response_model=list[AssignmentListItem])
async def get_assignments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    classroom_id: UUID | None = None,
) -> list[AssignmentListItem]:
    """List assignments visible to the user, optionally scoped to a classroom."""
    rows = await list_user_assignments(
        db,
        user_id=current_user.id,
        classroom_id=classroom_id,
    )
    items: list[AssignmentListItem] = []
    for assignment, recipient in rows:
        items.append(
            AssignmentListItem(
                id=assignment.id,
                classroom_id=assignment.classroom_id,
                created_by_id=assignment.created_by_id,
                title=assignment.title,
                instructions=assignment.instructions,
                target_type=assignment.target_type,
                status=assignment.status.value,
                due_at=assignment.due_at,
                timezone=assignment.timezone,
                recipient_id=recipient.id if recipient is not None else None,
                my_status=recipient.status if recipient is not None else None,
                my_blocked_reason=recipient.blocked_reason if recipient is not None else None,
            )
        )
    return items


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


@router.get("/{assignment_id}/progress", response_model=TeacherAssignmentProgressResponse)
async def get_assignment_progress(
    assignment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeacherAssignmentProgressResponse:
    """Return recipient-by-recipient progress to an active classroom teacher."""
    try:
        assignment, recipients, names = await get_teacher_assignment_progress(
            db,
            assignment_id=assignment_id,
            actor_user_id=current_user.id,
        )
    except DomainRuleViolation as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None

    counts: dict[str, int] = {}
    items = []
    for recipient in recipients:
        key = recipient.status.value
        counts[key] = counts.get(key, 0) + 1
        items.append(
            TeacherAssignmentRecipientProgress(
                recipient_id=recipient.id,
                student_id=recipient.student_id,
                student_name=names[recipient.id],
                status=recipient.status,
                blocked_reason=recipient.blocked_reason,
                acknowledged_at=recipient.acknowledged_at,
                submitted_at=recipient.submitted_at,
                completed_at=recipient.completed_at,
            )
        )
    return TeacherAssignmentProgressResponse(
        assignment_id=assignment.id,
        assignment_status=assignment.status.value,
        total_recipients=len(recipients),
        status_counts=counts,
        recipients=items,
    )


@router.post("/{assignment_id}/cancel", response_model=AssignmentCancellationResponse)
async def cancel_assignment_endpoint(
    assignment_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentCancellationResponse:
    """Cancel an assignment while retaining all recipient and submission history."""
    try:
        assignment = await cancel_assignment(
            db,
            assignment_id=assignment_id,
            actor_user_id=current_user.id,
        )
        await db.commit()
        await db.refresh(assignment)
    except DomainRuleViolation as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The assignment could not be cancelled.",
        ) from None

    return AssignmentCancellationResponse(
        assignment_id=assignment.id,
        status=assignment.status.value,
    )
