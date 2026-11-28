"""HTTP endpoints for classroom management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClassRole, User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.classrooms import (
    ClassroomRuleViolation,
    add_classroom_member,
    create_classroom,
    list_user_classrooms,
)
from app.schemas.classroom import (
    ClassroomCreateRequest,
    ClassroomMemberRequest,
    ClassroomMembershipResponse,
    ClassroomResponse,
)

router = APIRouter(prefix="/classrooms", tags=["Classrooms"])


@router.post(
    "",
    response_model=ClassroomResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_classroom_endpoint(
    request: ClassroomCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassroomResponse:
    """Create a classroom as an authorized school coordinator."""

    try:
        classroom = await create_classroom(
            db,
            actor_user_id=current_user.id,
            school_id=request.school_id,
            name=request.name,
            grade_label=request.grade_label,
        )
        await db.commit()
        await db.refresh(classroom)

    except ClassroomRuleViolation as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A classroom with this name may already exist in this school.",
        ) from None

    return ClassroomResponse.model_validate(classroom)


@router.get(
    "",
    response_model=list[ClassroomResponse],
)
async def get_classrooms(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ClassroomResponse]:
    """List classrooms accessible to the authenticated user."""

    classrooms = await list_user_classrooms(
        db,
        user_id=current_user.id,
    )

    return [
        ClassroomResponse.model_validate(classroom)
        for classroom in classrooms
    ]


async def _add_member(
    *,
    classroom_id: UUID,
    request: ClassroomMemberRequest,
    role: ClassRole,
    current_user: User,
    db: AsyncSession,
) -> ClassroomMembershipResponse:
    try:
        membership = await add_classroom_member(
            db,
            actor_user_id=current_user.id,
            classroom_id=classroom_id,
            user_id=request.user_id,
            role=role,
        )

        await db.commit()
        await db.refresh(membership)

    except ClassroomRuleViolation as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from None

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create the classroom membership.",
        ) from None

    return ClassroomMembershipResponse(
        classroom_id=membership.classroom_id,
        user_id=membership.user_id,
        role=membership.role.value,
        status=membership.status.value,
    )


@router.post(
    "/{classroom_id}/teachers",
    response_model=ClassroomMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_teacher(
    classroom_id: UUID,
    request: ClassroomMemberRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassroomMembershipResponse:
    """Add a registered user as a classroom teacher."""

    return await _add_member(
        classroom_id=classroom_id,
        request=request,
        role=ClassRole.TEACHER,
        current_user=current_user,
        db=db,
    )


@router.post(
    "/{classroom_id}/students",
    response_model=ClassroomMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_student(
    classroom_id: UUID,
    request: ClassroomMemberRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClassroomMembershipResponse:
    """Add a registered user as a classroom student."""

    return await _add_member(
        classroom_id=classroom_id,
        request=request,
        role=ClassRole.STUDENT,
        current_user=current_user,
        db=db,
    )
