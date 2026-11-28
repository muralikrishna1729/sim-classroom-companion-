"""HTTP endpoints for school operations."""
from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.schools import create_school, list_user_schools
from app.schemas.school import SchoolCreateRequest, SchoolResponse

router = APIRouter(prefix="/schools", tags=["Schools"])

@router.post("", response_model=SchoolResponse, status_code=status.HTTP_201_CREATED)
async def create_school_endpoint(request: SchoolCreateRequest, current_user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> SchoolResponse:
    school = await create_school(db, actor_user_id=current_user.id, name=request.name, timezone=request.timezone)
    await db.commit()
    await db.refresh(school)
    return SchoolResponse.model_validate(school)

@router.get("/me", response_model=list[SchoolResponse])
async def get_my_schools(current_user: Annotated[User, Depends(get_current_user)], db: Annotated[AsyncSession, Depends(get_db)]) -> list[SchoolResponse]:
    schools = await list_user_schools(db, user_id=current_user.id)
    return [SchoolResponse.model_validate(school) for school in schools]
